"""The journal and the adherence score.

The journal records every order the copilot evaluated, whether it was
routed, held, or imported from a broker statement. The adherence score is
the share of fills that complied with the user's rules. Orders the copilot
held do not count against the score (nothing was traded); fills imported
from outside the copilot are checked after the fact and count when they
would have been held.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .broker import Fill
from .models import Account, ClosedTradeRow, JournalRow, PositionRow, RuleRow
from .rules import AccountState, Decision, Order, Position, RuleSet, TradePlan, evaluate


# --------------------------------------------------------------------------
# Loading state
# --------------------------------------------------------------------------


def rules_from_row(row: RuleRow) -> RuleSet:
    return RuleSet(
        max_position_pct=row.max_position_pct,
        daily_loss_limit=row.daily_loss_limit,
        max_premium_at_risk=row.max_premium_at_risk,
        max_margin_pct=row.max_margin_pct,
        min_holding_days=row.min_holding_days,
        loss_streak_trigger=row.loss_streak_trigger,
        cooldown_minutes=row.cooldown_minutes,
        plan_required=row.plan_required,
        max_trades_per_day=row.max_trades_per_day,
    )


def save_rules(row: RuleRow, rules: RuleSet, now: Optional[datetime] = None) -> None:
    for name in RuleSet.__dataclass_fields__:
        setattr(row, name, getattr(rules, name))
    row.updated_at = now or datetime.now()


def position_from_row(row: PositionRow, last_price: float) -> Position:
    return Position(
        symbol=row.symbol,
        qty=row.qty,
        avg_cost=row.avg_cost,
        last_price=last_price,
        opened_at=row.opened_at,
        asset_type=row.asset_type,
        plan=TradePlan(stop_pct=row.stop_pct, target_pct=row.target_pct,
                       max_hold_days=row.max_hold_days, template=row.template),
    )


def _price_for(row: PositionRow, quotes: dict[str, float], option_quotes: dict[str, tuple[str, float]]) -> float:
    if row.asset_type == "option":
        if row.contract in option_quotes:
            return option_quotes[row.contract][1]
        return row.avg_cost
    return quotes.get(row.symbol, row.avg_cost)


def position_key(row: PositionRow) -> str:
    return row.contract if row.asset_type == "option" else row.symbol


def load_state(session: Session, account: Account, quotes: dict[str, float],
               option_quotes: dict[str, tuple[str, float]], now: datetime) -> AccountState:
    positions: dict[str, Position] = {}
    for row in account.positions:
        if row.qty <= 0:
            continue
        pos = position_from_row(row, _price_for(row, quotes, option_quotes))
        key = position_key(row)
        pos.symbol = key
        positions[key] = pos
    equity = account.cash + sum(p.market_value for p in positions.values())

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    closed = session.scalars(
        select(ClosedTradeRow).where(ClosedTradeRow.account_id == account.id).order_by(ClosedTradeRow.closed_at)
    ).all()
    realized_today = sum(c.realized_pnl for c in closed if c.closed_at >= day_start)
    streak, last_loss_at = 0, None
    for c in reversed(closed):
        if c.realized_pnl < 0:
            streak += 1
            last_loss_at = last_loss_at or c.closed_at
        else:
            break
    trades_today = session.scalars(
        select(JournalRow).where(JournalRow.account_id == account.id, JournalRow.routed.is_(True), JournalRow.ts >= day_start)
    ).all()
    return AccountState(
        equity=equity,
        cash=account.cash,
        positions=positions,
        realized_pnl_today=realized_today,
        consecutive_losses=streak,
        last_loss_at=last_loss_at,
        trades_today=len(trades_today),
    )


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def record(session: Session, account: Account, decision: Decision, explanation: str,
           now: datetime, fill: Optional[Fill] = None, rule_break: bool = False) -> JournalRow:
    o = decision.order
    row = JournalRow(
        account_id=account.id,
        ts=now,
        symbol=o.symbol,
        side=o.side,
        qty=o.qty,
        price=o.price,
        asset_type=o.asset_type,
        contract=o.contract,
        source=o.source,
        outcome=decision.outcome,
        headline_rule=decision.headline_rule,
        explanation=explanation,
        plan_template=o.plan.template,
        plan_stop_pct=o.plan.stop_pct,
        planned_risk=o.planned_risk,
        routed=fill is not None,
        fill_id=fill.fill_id if fill else None,
        broker=fill.broker if fill else None,
        rule_break=rule_break,
    )
    session.add(row)
    return row


def apply_fill(session: Session, account: Account, order: Order, fill: Fill, now: datetime) -> Optional[ClosedTradeRow]:
    """Update cash and positions. Returns the closed-trade row for a sell."""
    key = order.key
    existing = next((p for p in account.positions if position_key(p) == key), None)
    mult = order.multiplier
    if order.side == "buy":
        account.cash -= fill.qty * fill.price * mult
        if existing:
            total_cost = existing.qty * existing.avg_cost + fill.qty * fill.price
            existing.qty += fill.qty
            existing.avg_cost = total_cost / existing.qty
            if order.plan.stop_pct:
                existing.stop_pct = order.plan.stop_pct
        else:
            account.positions.append(PositionRow(
                symbol=order.symbol, asset_type=order.asset_type, contract=order.contract,
                qty=fill.qty, avg_cost=fill.price, opened_at=now,
                stop_pct=order.plan.stop_pct, target_pct=order.plan.target_pct,
                max_hold_days=order.plan.max_hold_days, template=order.plan.template,
            ))
        return None
    # sell
    if existing is None:
        raise ValueError(f"No open position in {key}")
    qty = min(fill.qty, existing.qty)
    account.cash += qty * fill.price * mult
    pnl = (fill.price - existing.avg_cost) * qty * mult
    closed = ClosedTradeRow(
        account_id=account.id, closed_at=now, symbol=key, asset_type=order.asset_type,
        qty=qty, entry_price=existing.avg_cost, exit_price=fill.price, realized_pnl=pnl,
    )
    session.add(closed)
    session.flush()
    existing.qty -= qty
    if existing.qty <= 0:
        account.positions.remove(existing)   # delete-orphan removes the row
    return closed


# --------------------------------------------------------------------------
# Adherence
# --------------------------------------------------------------------------


@dataclass
class Adherence:
    window_days: int
    fills: int
    breaks: int
    held: int
    held_planned_risk: float
    by_rule: dict[str, int] = field(default_factory=dict)
    outside_fills: int = 0

    @property
    def score(self) -> Optional[float]:
        if self.fills == 0:
            return None
        return (self.fills - self.breaks) / self.fills


def adherence(session: Session, account: Account, now: datetime, window_days: int = 30) -> Adherence:
    since = now - timedelta(days=window_days)
    rows = session.scalars(
        select(JournalRow).where(JournalRow.account_id == account.id, JournalRow.ts >= since)
    ).all()
    fills = [r for r in rows if r.routed]
    breaks = [r for r in fills if r.rule_break]
    held = [r for r in rows if r.outcome == "BLOCK" and not r.routed]
    by_rule: dict[str, int] = {}
    for r in held + breaks:
        if r.headline_rule:
            by_rule[r.headline_rule] = by_rule.get(r.headline_rule, 0) + 1
    return Adherence(
        window_days=window_days,
        fills=len(fills),
        breaks=len(breaks),
        held=len(held),
        held_planned_risk=sum(r.planned_risk for r in held),
        by_rule=dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
        outside_fills=len([r for r in fills if r.source == "broker_import"]),
    )


# --------------------------------------------------------------------------
# Outside fills
# --------------------------------------------------------------------------


def import_outside_fill(session: Session, account: Account, order: Order, rules: RuleSet,
                        state: AccountState, now: datetime, explanation_fn) -> JournalRow:
    """Check a fill made at the broker's own app after the fact, then book it.

    The check runs against the account state at import time. The product
    would snapshot the state at the fill's timestamp; the prototype keeps
    the simpler version and says so in the journal.
    """
    order.source = "broker_import"
    decision = evaluate(order, state, rules, now)
    fill = Fill(fill_id=f"EXT-{now.strftime('%H%M%S')}-{order.symbol}", symbol=order.symbol, side=order.side,
                qty=order.qty, price=order.price, asset_type=order.asset_type, filled_at=now,
                broker="Imported from broker statement", contract=order.contract)
    text = explanation_fn(decision)
    if decision.outcome == "BLOCK":
        text = "Placed outside the copilot. " + text.replace("Held.", "It would have been held:")
    row = record(session, account, decision, text, now, fill=fill, rule_break=(decision.outcome == "BLOCK"))
    apply_fill(session, account, order, fill, now)
    return row
