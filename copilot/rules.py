"""Deterministic rule engine.

Design notes
------------
* The engine is a pure function: ``evaluate(order, account, rules, now)``
  returns a ``Decision``. No database, no network, no model call. That is
  deliberate. When a user or a regulator asks why an order was held, the
  answer has to be a line in this file, not a model's opinion.
* Every rule is user-set. The defaults below are the values of the demo
  account; the product never imposes a limit the user did not write.
* Three outcomes. PASS routes on the user's confirmation. REVIEW routes only
  after the user acknowledges a warning (the order is within reach of a
  limit). BLOCK never routes. Nothing in the engine can be overridden from
  the user interface; a user who wants the trade anyway can place it at the
  broker, and the journal will count it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional

Side = Literal["buy", "sell"]
AssetType = Literal["stock", "option"]
Outcome = Literal["PASS", "REVIEW", "BLOCK"]

OPTION_MULTIPLIER = 100
REVIEW_BAND = 0.80  # using 80 percent or more of a loss budget triggers REVIEW rather than PASS


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


@dataclass
class TradePlan:
    """What the user commits to before the order goes out.

    This replaced the strategy-template requirement after the Sep 30 class.
    The professor asked how users would know which template to apply. The
    answer the team settled on: they do not have to. They state an exit.
    """

    stop_pct: Optional[float] = None       # e.g. 0.07 means exit if down 7 percent
    target_pct: Optional[float] = None     # optional take-profit
    max_hold_days: Optional[int] = None    # optional time stop
    template: str = "discretionary"        # label only: moving-average pullback, MACD cross, earnings hold, discretionary
    note: str = ""

    @property
    def has_exit(self) -> bool:
        return self.stop_pct is not None and self.stop_pct > 0


@dataclass
class Position:
    symbol: str
    qty: float
    avg_cost: float               # per share, or per contract premium for options
    last_price: float
    opened_at: datetime
    asset_type: AssetType = "stock"
    plan: TradePlan = field(default_factory=TradePlan)

    @property
    def multiplier(self) -> int:
        return OPTION_MULTIPLIER if self.asset_type == "option" else 1

    @property
    def market_value(self) -> float:
        return self.qty * self.last_price * self.multiplier

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_cost * self.multiplier

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pct(self) -> float:
        return 0.0 if self.cost_basis == 0 else self.unrealized_pnl / self.cost_basis

    @property
    def stop_price(self) -> Optional[float]:
        if self.plan.stop_pct is None:
            return None
        return round(self.avg_cost * (1 - self.plan.stop_pct), 2)

    @property
    def stop_hit(self) -> bool:
        return self.stop_price is not None and self.last_price <= self.stop_price

    def days_held(self, now: datetime) -> int:
        return max(0, (now - self.opened_at).days)


@dataclass
class AccountState:
    equity: float
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl_today: float = 0.0
    consecutive_losses: int = 0
    last_loss_at: Optional[datetime] = None
    trades_today: int = 0

    @property
    def open_premium_at_risk(self) -> float:
        return sum(p.cost_basis for p in self.positions.values() if p.asset_type == "option")

    @property
    def borrowed(self) -> float:
        return max(0.0, -self.cash)


@dataclass
class Order:
    symbol: str
    side: Side
    qty: float
    price: float                      # limit price, or the quote used for the check
    asset_type: AssetType = "stock"
    plan: TradePlan = field(default_factory=TradePlan)
    source: str = "copilot"           # "copilot" or "broker_import"
    contract: str = ""                # options only, e.g. "SPY 2026-11-20 575 C"

    @property
    def multiplier(self) -> int:
        return OPTION_MULTIPLIER if self.asset_type == "option" else 1

    @property
    def key(self) -> str:
        """Positions are keyed by symbol for stock and by contract for options."""
        return self.contract if self.asset_type == "option" and self.contract else self.symbol

    @property
    def notional(self) -> float:
        return self.qty * self.price * self.multiplier

    @property
    def is_opening(self) -> bool:
        # The prototype supports long positions only, so a buy opens or adds
        # and a sell closes or reduces.
        return self.side == "buy"

    @property
    def planned_risk(self) -> float:
        """Dollars at risk if the plan's stop is hit. Options: the premium."""
        if self.asset_type == "option":
            return self.notional
        if self.plan.stop_pct:
            return self.notional * self.plan.stop_pct
        return 0.0


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


@dataclass
class RuleSet:
    """Account-level limits. All user-set; these are the demo defaults."""

    max_position_pct: float = 0.10       # one position may not exceed 10 percent of equity
    daily_loss_limit: float = 500.0      # realized today plus this order's planned risk
    max_premium_at_risk: float = 750.0   # open long-option premium plus this order's premium
    max_margin_pct: float = 0.20         # borrowing may not exceed 20 percent of equity (0 = no margin)
    min_holding_days: int = 3            # from the Sep 30 class discussion
    loss_streak_trigger: int = 3         # from the Sep 30 class discussion
    cooldown_minutes: int = 30           # "a 30-minute break"
    plan_required: bool = True           # every opening order carries an exit
    max_trades_per_day: int = 8          # overtrading guard (Barber and Odean)

    def as_rows(self) -> list[tuple[str, str, str]]:
        """Human-readable table rows: (rule, your setting, where it came from)."""
        return [
            ("Position size", f"No position above {self.max_position_pct:.0%} of equity", "Canvas, version 1.0"),
            ("Daily loss limit", f"Stop opening new risk once today's realized loss plus planned risk reaches ${self.daily_loss_limit:,.0f}", "Canvas, version 1.0"),
            ("Premium at risk", f"Open option premium capped at ${self.max_premium_at_risk:,.0f}", "Canvas, version 1.0"),
            ("Margin use", f"Borrowing capped at {self.max_margin_pct:.0%} of equity", "Canvas, version 1.0"),
            ("Minimum holding period", f"No sale inside {self.min_holding_days} days unless the plan's stop is hit", "Class discussion, Sep 30"),
            ("Losing-streak cooldown", f"After {self.loss_streak_trigger} consecutive losing closes, no new entries for {self.cooldown_minutes} minutes", "Class discussion, Sep 30"),
            ("Plan required", "Every opening order states a stop before it is checked" if self.plan_required else "Off", "Professor's question, Sep 30"),
            ("Trades per day", f"At most {self.max_trades_per_day} orders routed per day", "Research on overtrading"),
        ]


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


@dataclass
class Finding:
    rule: str
    outcome: Outcome
    message: str
    used: Optional[float] = None       # share of the limit used after this order, when meaningful
    passing_qty: Optional[int] = None  # largest quantity that would pass this rule, when meaningful


@dataclass
class Decision:
    outcome: Outcome
    findings: list[Finding]
    order: Order

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.outcome == "BLOCK"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.outcome == "REVIEW"]

    @property
    def headline_rule(self) -> Optional[str]:
        if self.blocking:
            return self.blocking[0].rule
        if self.warnings:
            return self.warnings[0].rule
        return None

    @property
    def passing_qty(self) -> Optional[int]:
        """Largest quantity that would clear every blocking rule, if any rule offers one."""
        qtys = [f.passing_qty for f in self.blocking if f.passing_qty is not None]
        if not qtys:
            return None
        return max(0, min(qtys))


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------


def _usd(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def _band(used: float) -> Outcome:
    """Budget rules (daily loss, premium at risk, trades per day): warn near the limit."""
    if used > 1.0:
        return "BLOCK"
    if used >= REVIEW_BAND:
        return "REVIEW"
    return "PASS"


def _hard(used: float) -> Outcome:
    """Structural limits (position size, margin): within the limit is simply within it."""
    return "BLOCK" if used > 1.0 else "PASS"


def check_plan_required(order: Order, rules: RuleSet) -> Optional[Finding]:
    if not rules.plan_required or not order.is_opening:
        return None
    if order.plan.has_exit:
        return Finding("Plan required", "PASS",
                       f"Plan attached: {order.plan.template}, stop {order.plan.stop_pct:.0%}.")
    return Finding("Plan required", "BLOCK",
                   "No exit stated. Your rule is that every opening order carries a stop before it is checked.")


def check_position_size(order: Order, account: AccountState, rules: RuleSet) -> Optional[Finding]:
    if not order.is_opening:
        return None
    limit = rules.max_position_pct * account.equity
    existing = account.positions.get(order.key)
    existing_value = existing.market_value if existing else 0.0
    after = existing_value + order.notional
    used = after / limit if limit > 0 else float("inf")
    outcome = _hard(used)
    room = limit - existing_value
    per_unit = order.price * order.multiplier
    passing = int(room // per_unit) if per_unit > 0 else 0
    name = order.key
    if outcome == "BLOCK":
        msg = (f"{name} would be ${after:,.0f}, or {after / account.equity:.0%} of equity. "
               f"Your limit is {rules.max_position_pct:.0%} (${limit:,.0f}).")
        if existing:
            msg += f" You already hold ${existing_value:,.0f}."
    else:
        msg = f"{name} would be {after / account.equity:.1%} of equity, within your {rules.max_position_pct:.0%} limit."
    return Finding("Position size", outcome, msg, used=used, passing_qty=max(0, passing))


def check_daily_loss(order: Order, account: AccountState, rules: RuleSet) -> Optional[Finding]:
    if not order.is_opening:
        return None
    realized_loss = max(0.0, -account.realized_pnl_today)
    projected = realized_loss + order.planned_risk
    used = projected / rules.daily_loss_limit if rules.daily_loss_limit > 0 else float("inf")
    outcome = _band(used)
    room = rules.daily_loss_limit - realized_loss
    risk_per_unit = order.planned_risk / order.qty if order.qty else 0.0
    passing = int(room // risk_per_unit) if risk_per_unit > 0 else None
    if realized_loss >= rules.daily_loss_limit:
        return Finding("Daily loss limit", "BLOCK",
                       f"Today's realized loss is ${realized_loss:,.0f}, at or past your ${rules.daily_loss_limit:,.0f} limit. "
                       "No new risk today.", used=used, passing_qty=0)
    if outcome == "BLOCK":
        msg = (f"Realized today {_usd(-realized_loss)}; this order risks ${order.planned_risk:,.0f} at your stop. "
               f"Together ${projected:,.0f}, past your ${rules.daily_loss_limit:,.0f} limit.")
    elif outcome == "REVIEW":
        msg = (f"Realized today {_usd(-realized_loss)}; this order risks ${order.planned_risk:,.0f} at your stop, "
               f"which uses {used:.0%} of your ${rules.daily_loss_limit:,.0f} daily limit.")
    else:
        msg = (f"Realized today {_usd(-realized_loss)}; this order risks ${order.planned_risk:,.0f} at your stop "
               f"({used:.0%} of your daily limit).")
    return Finding("Daily loss limit", outcome, msg, used=used, passing_qty=passing)


def check_premium_at_risk(order: Order, account: AccountState, rules: RuleSet) -> Optional[Finding]:
    if order.asset_type != "option" or not order.is_opening:
        return None
    after = account.open_premium_at_risk + order.notional
    used = after / rules.max_premium_at_risk if rules.max_premium_at_risk > 0 else float("inf")
    outcome = _band(used)
    room = rules.max_premium_at_risk - account.open_premium_at_risk
    per_contract = order.price * OPTION_MULTIPLIER
    passing = int(room // per_contract) if per_contract > 0 else 0
    if outcome == "BLOCK":
        msg = (f"Open premium ${account.open_premium_at_risk:,.0f} plus this order's ${order.notional:,.0f} "
               f"is ${after:,.0f}, past your ${rules.max_premium_at_risk:,.0f} cap.")
    elif outcome == "REVIEW":
        msg = f"Open premium would reach ${after:,.0f}, {used:.0%} of your ${rules.max_premium_at_risk:,.0f} cap."
    else:
        msg = f"Open premium would be ${after:,.0f}, within your ${rules.max_premium_at_risk:,.0f} cap."
    return Finding("Premium at risk", outcome, msg, used=used, passing_qty=max(0, passing))


def check_margin(order: Order, account: AccountState, rules: RuleSet) -> Optional[Finding]:
    if not order.is_opening:
        return None
    cash_after = account.cash - order.notional
    borrowed_after = max(0.0, -cash_after)
    if borrowed_after == 0:
        return Finding("Margin use", "PASS", f"Paid from cash; ${cash_after:,.0f} remains.", used=0.0)
    limit = rules.max_margin_pct * account.equity
    if limit <= 0:
        return Finding("Margin use", "BLOCK",
                       f"This order would borrow ${borrowed_after:,.0f}. Your rule allows no margin.",
                       used=float("inf"), passing_qty=int(max(0.0, account.cash) // (order.price * order.multiplier)))
    used = borrowed_after / limit
    outcome = _hard(used)
    per_unit = order.price * order.multiplier
    passing = int((account.cash + limit) // per_unit) if per_unit > 0 else 0
    if outcome == "BLOCK":
        msg = (f"This order would borrow ${borrowed_after:,.0f}, or {borrowed_after / account.equity:.0%} of equity. "
               f"Your cap is {rules.max_margin_pct:.0%} (${limit:,.0f}).")
    else:
        msg = f"This order would borrow ${borrowed_after:,.0f}, within your {rules.max_margin_pct:.0%} cap."
    return Finding("Margin use", outcome, msg, used=used, passing_qty=max(0, passing))


def check_min_hold(order: Order, account: AccountState, rules: RuleSet, now: datetime) -> Optional[Finding]:
    if order.is_opening:
        return None
    pos = account.positions.get(order.key)
    if pos is None:
        return Finding("Minimum holding period", "BLOCK",
                       f"No open position in {order.key}. The prototype supports long positions only.")
    held = pos.days_held(now)
    if held >= rules.min_holding_days:
        return Finding("Minimum holding period", "PASS",
                       f"Held {held} days, past your {rules.min_holding_days}-day minimum.")
    if pos.stop_hit:
        return Finding("Minimum holding period", "PASS",
                       f"Held {held} days, but the stop you set (${pos.stop_price:,.2f}) has been hit at ${pos.last_price:,.2f}. "
                       "Exiting on your plan is allowed.")
    if pos.plan.target_pct and pos.unrealized_pct >= pos.plan.target_pct:
        return Finding("Minimum holding period", "PASS",
                       f"Held {held} days, but your target of {pos.plan.target_pct:.0%} is reached. Exiting on your plan is allowed.")
    stop_txt = f"${pos.stop_price:,.2f}" if pos.stop_price else "not set"
    return Finding("Minimum holding period", "BLOCK",
                   f"Opened {held} day{'s' if held != 1 else ''} ago; your minimum is {rules.min_holding_days} days. "
                   f"The stop you set ({stop_txt}) has not been hit at ${pos.last_price:,.2f}, so this is a change of mind, not an exit on plan.")


def check_cooldown(order: Order, account: AccountState, rules: RuleSet, now: datetime) -> Optional[Finding]:
    if not order.is_opening:
        return None
    if account.consecutive_losses < rules.loss_streak_trigger or account.last_loss_at is None:
        streak = account.consecutive_losses
        msg = (f"{streak} consecutive losing close{'s' if streak != 1 else ''}; the cooldown starts at {rules.loss_streak_trigger}."
               if streak else "No losing streak.")
        return Finding("Losing-streak cooldown", "PASS", msg)
    ends = account.last_loss_at + timedelta(minutes=rules.cooldown_minutes)
    if now >= ends:
        return Finding("Losing-streak cooldown", "PASS",
                       f"{account.consecutive_losses} consecutive losing closes, but the {rules.cooldown_minutes}-minute cooldown has ended.")
    remaining = math.ceil((ends - now).total_seconds() / 60)
    return Finding("Losing-streak cooldown", "BLOCK",
                   f"{account.consecutive_losses} consecutive losing closes. Your rule is a {rules.cooldown_minutes}-minute break; "
                   f"{remaining} minute{'s' if remaining != 1 else ''} remain.", passing_qty=0)


def check_add_below_stop(order: Order, account: AccountState) -> Optional[Finding]:
    """Adding to a position that is already past its own stop is averaging down past the plan."""
    if not order.is_opening:
        return None
    pos = account.positions.get(order.key)
    if pos is None or not pos.stop_hit:
        return None
    return Finding("Plan required", "BLOCK",
                   f"{order.key} is at ${pos.last_price:,.2f}, past the stop you set at ${pos.stop_price:,.2f}. "
                   "Your plan calls for an exit, not an addition.", passing_qty=0)


def check_trade_count(order: Order, account: AccountState, rules: RuleSet) -> Optional[Finding]:
    after = account.trades_today + 1
    used = after / rules.max_trades_per_day if rules.max_trades_per_day > 0 else float("inf")
    outcome = _band(used)
    if outcome == "BLOCK":
        return Finding("Trades per day", "BLOCK",
                       f"{account.trades_today} orders routed today; your limit is {rules.max_trades_per_day}.", used=used, passing_qty=0)
    if outcome == "REVIEW":
        return Finding("Trades per day", "REVIEW",
                       f"This would be order {after} of your {rules.max_trades_per_day} for the day.", used=used)
    return Finding("Trades per day", "PASS", f"Order {after} of {rules.max_trades_per_day} for the day.", used=used)


def evaluate(order: Order, account: AccountState, rules: RuleSet, now: Optional[datetime] = None) -> Decision:
    """Run every rule and combine. BLOCK beats REVIEW beats PASS."""
    now = now or datetime.now()
    if order.qty <= 0 or order.price <= 0:
        return Decision("BLOCK", [Finding("Order", "BLOCK", "Quantity and price must be positive.")], order)

    checks = [
        check_plan_required(order, rules),
        check_add_below_stop(order, account),
        check_position_size(order, account, rules),
        check_premium_at_risk(order, account, rules),
        check_daily_loss(order, account, rules),
        check_margin(order, account, rules),
        check_min_hold(order, account, rules, now),
        check_cooldown(order, account, rules, now),
        check_trade_count(order, account, rules),
    ]
    findings = [f for f in checks if f is not None]
    if any(f.outcome == "BLOCK" for f in findings):
        outcome: Outcome = "BLOCK"
    elif any(f.outcome == "REVIEW" for f in findings):
        outcome = "REVIEW"
    else:
        outcome = "PASS"
    # Blocking findings first, then warnings, then passes, so the headline is the reason.
    rank = {"BLOCK": 0, "REVIEW": 1, "PASS": 2}
    findings.sort(key=lambda f: rank[f.outcome])
    return Decision(outcome, findings, order)
