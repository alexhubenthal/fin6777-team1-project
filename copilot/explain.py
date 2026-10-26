"""Plain-English explanations.

The explanation is assembled from the engine's findings by fixed templates,
so the text always matches the numbers the engine used. A language model
can rewrite the wording (see ``Rewriter``) but never changes the decision,
the rule named, or the figures. In this build the rewriter is a no-op, so
the prototype runs with no API key and no network call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .rules import Decision, Position

WHY_IT_MATTERS = {
    "Position size": "Concentration turns one bad call into a bad month. The limit keeps any single name survivable.",
    "Daily loss limit": "Losses cluster late in a bad day. A daily cap is the rule most traders say they want and least often keep.",
    "Premium at risk": "Long options can go to zero. Capping open premium bounds the worst case before it happens.",
    "Margin use": "Borrowed money adds the broker's rules to yours. A cap on borrowing keeps the decision yours.",
    "Minimum holding period": "Selling a few days after buying, below cost, is usually a change of mind rather than a plan. The rule makes you wait unless your stop says otherwise.",
    "Losing-streak cooldown": "After several losses in a row, the next trade is usually about the last one. A short break resets that.",
    "Plan required": "An order with a stated exit is a plan. An order without one is a hope.",
    "Trades per day": "Trading more has been associated with earning less for twenty-five years of retail studies.",
}

OUTCOME_LABEL = {
    "PASS": "Clear to route",
    "REVIEW": "Review before routing",
    "BLOCK": "Held by your rules",
}


class Rewriter(Protocol):
    def rewrite(self, text: str) -> str: ...


class NullRewriter:
    """Default: returns the template text unchanged."""

    def rewrite(self, text: str) -> str:
        return text


def describe_order(decision: Decision) -> str:
    o = decision.order
    unit = "contract" if o.asset_type == "option" else "share"
    what = o.contract if o.asset_type == "option" else o.symbol
    qty = f"{o.qty:g} {unit}{'s' if o.qty != 1 else ''}"
    return f"{o.side.capitalize()} {qty} of {what} at ${o.price:,.2f} (${o.notional:,.0f})."


def explain_decision(decision: Decision, rewriter: Rewriter | None = None) -> str:
    """One short paragraph a user can read in the time it takes to confirm."""
    rewriter = rewriter or NullRewriter()
    lines = [describe_order(decision)]
    if decision.outcome == "BLOCK":
        f = decision.blocking[0]
        lines.append(f"Held. {f.message}")
        if decision.passing_qty is not None and decision.passing_qty > 0:
            unit = "contract" if decision.order.asset_type == "option" else "share"
            lines.append(f"A quantity of {decision.passing_qty} {unit}{'s' if decision.passing_qty != 1 else ''} or fewer would clear this rule.")
        if len(decision.blocking) > 1:
            others = ", ".join(x.rule.lower() for x in decision.blocking[1:])
            lines.append(f"It would also trip: {others}.")
    elif decision.outcome == "REVIEW":
        f = decision.warnings[0]
        lines.append(f"Nothing is breached, but this is close to a limit. {f.message}")
        lines.append("Confirm only if you still want it after reading that sentence.")
    else:
        lines.append("Every rule you set is satisfied. Confirm and it goes to the broker.")
    return rewriter.rewrite(" ".join(lines))


def explain_position(pos: Position, now: datetime, min_holding_days: int) -> str:
    held = pos.days_held(now)
    direction = "up" if pos.unrealized_pnl >= 0 else "down"
    unit = "contract" if pos.asset_type == "option" else "share"
    sign = "-" if pos.unrealized_pnl < 0 else "+"
    s = (f"{pos.qty:g} {unit}{'s' if pos.qty != 1 else ''} at ${pos.avg_cost:,.2f}, now ${pos.last_price:,.2f}, "
         f"{direction} {abs(pos.unrealized_pct):.1%} ({sign}${abs(pos.unrealized_pnl):,.0f}). Held {held} day{'s' if held != 1 else ''}.")
    if pos.stop_price is not None:
        if pos.stop_hit:
            s += f" Your stop at ${pos.stop_price:,.2f} has been hit: the plan says exit."
        else:
            dist = (pos.last_price - pos.stop_price) / pos.last_price
            s += f" Stop at ${pos.stop_price:,.2f}, {dist:.1%} below the last price."
    else:
        s += " No stop on file."
    if held < min_holding_days and not pos.stop_hit:
        s += f" Inside your {min_holding_days}-day minimum hold."
    return s


def status_of_position(pos: Position, now: datetime, min_holding_days: int) -> str:
    if pos.stop_hit:
        return "Exit due"
    if pos.days_held(now) < min_holding_days:
        return "Holding"
    return "Within plan"
