"""Demo account used in class.

Everything here is sample data. The account is set up so that the live
demo can show each outcome in under two minutes: a passing order, an order
held on position size, a sale held by the minimum holding period, an
options order held on premium at risk, and a review on the daily loss
limit. Two of the fills in the journal were "placed at the broker's app"
to show how outside trades count against the adherence score.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Account, ClosedTradeRow, JournalRow, PositionRow, RuleRow

DEMO_NAME = "Demo trader"


def _d(now: datetime, days: float, hour: int | None = None, minute: int = 0) -> datetime:
    t = now - timedelta(days=days)
    if hour is not None:
        t = t.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return t


def seed_demo(session: Session, now: datetime | None = None) -> Account:
    now = now or datetime.now()
    existing = session.scalar(select(Account).where(Account.name == DEMO_NAME))
    if existing:
        session.delete(existing)
        session.flush()

    acct = Account(name=DEMO_NAME, cash=18_186.80, created_at=_d(now, 30))
    session.add(acct)
    session.flush()
    session.add(RuleRow(account_id=acct.id))

    # Open positions: equity works out to $25,000.00 at the sample quotes.
    session.add_all([
        PositionRow(account_id=acct.id, symbol="AAPL", qty=20, avg_cost=228.00, opened_at=_d(now, 12, 10, 12),
                    stop_pct=0.07, template="earnings hold"),
        PositionRow(account_id=acct.id, symbol="NVDA", qty=8, avg_cost=191.00, opened_at=_d(now, 1, 14, 5),
                    stop_pct=0.06, template="moving-average pullback"),
        PositionRow(account_id=acct.id, symbol="SPY", asset_type="option", contract="SPY 2026-11-20 575 C",
                    qty=2, avg_cost=3.40, opened_at=_d(now, 4, 9, 48), template="discretionary"),
    ])

    # Closed trades, oldest first. The last two are today's losses.
    session.add_all([
        ClosedTradeRow(account_id=acct.id, closed_at=_d(now, 24, 11, 20), symbol="SOFI", qty=25, entry_price=20.10, exit_price=21.30, realized_pnl=30.00),
        ClosedTradeRow(account_id=acct.id, closed_at=_d(now, 20, 15, 42), symbol="HOOD", qty=6, entry_price=112.00, exit_price=109.50, realized_pnl=-15.00),
        ClosedTradeRow(account_id=acct.id, closed_at=_d(now, 18, 10, 2), symbol="PLTR", qty=10, entry_price=139.00, exit_price=145.60, realized_pnl=66.00),
        ClosedTradeRow(account_id=acct.id, closed_at=_d(now, 9, 13, 30), symbol="QQQ", qty=10, entry_price=482.00, exit_price=489.60, realized_pnl=76.00),
        ClosedTradeRow(account_id=acct.id, closed_at=_d(now, 0, 10, 5), symbol="TSLA", qty=10, entry_price=272.30, exit_price=258.30, realized_pnl=-140.00),
        ClosedTradeRow(account_id=acct.id, closed_at=_d(now, 0, 10, 40), symbol="AMD", qty=15, entry_price=170.50, exit_price=164.20, realized_pnl=-94.50),
    ])

    def j(days, hour, minute, symbol, side, qty, price, outcome, rule=None, text="", template="discretionary",
          stop=None, risk=0.0, routed=True, source="copilot", asset_type="stock", contract="", rule_break=False):
        return JournalRow(
            account_id=acct.id, ts=_d(now, days, hour, minute), symbol=symbol, side=side, qty=qty, price=price,
            asset_type=asset_type, contract=contract, source=source, outcome=outcome, headline_rule=rule,
            explanation=text, plan_template=template, plan_stop_pct=stop, planned_risk=risk, routed=routed,
            fill_id=(f"SIM-{abs(hash((symbol, days, side))) % 10**8:08d}" if routed and source == "copilot" else
                     (f"EXT-{symbol}-{int(days)}" if routed else None)),
            broker=("Simulated broker (paper)" if routed and source == "copilot" else
                    ("Imported from broker statement" if routed else None)),
            rule_break=rule_break,
        )

    session.add_all([
        j(27, 10, 14, "SOFI", "buy", 25, 20.10, "PASS", template="MACD cross", stop=0.08, risk=40.20,
          text="Buy 25 shares of SOFI at $20.10 ($503). Every rule you set is satisfied."),
        j(24, 11, 20, "SOFI", "sell", 25, 21.30, "PASS", text="Sell 25 shares of SOFI at $21.30 ($533). Held 3 days, past your 3-day minimum."),
        j(22, 9, 41, "PLTR", "buy", 10, 139.00, "PASS", template="swing (3 to 10 days)", stop=0.08, risk=111.20,
          text="Buy 10 shares of PLTR at $139.00 ($1,390). Every rule you set is satisfied."),
        j(21, 13, 7, "HOOD", "buy", 6, 112.00, "BLOCK", rule="Plan required", source="broker_import", rule_break=True,
          text="Placed outside the copilot. Buy 6 shares of HOOD at $112.00 ($672). It would have been held: no exit stated. Your rule is that every opening order carries a stop before it is checked."),
        j(19, 14, 50, "TSLA", "buy", 3, 11.80, "BLOCK", rule="Premium at risk", asset_type="option", contract="TSLA 2026-11-20 260 C",
          risk=3540.0, routed=False,
          text="Buy 3 contracts of TSLA 2026-11-20 260 C at $11.80 ($3,540). Held. Open premium $0 plus this order's $3,540 is $3,540, past your $750 cap."),
        j(20, 15, 42, "HOOD", "sell", 6, 109.50, "BLOCK", rule="Minimum holding period", source="broker_import", rule_break=True,
          text="Placed outside the copilot. Sell 6 shares of HOOD at $109.50 ($657). It would have been held: opened 1 day ago; your minimum is 3 days. The stop you set (not set) has not been hit at $109.50, so this is a change of mind, not an exit on plan."),
        j(18, 10, 2, "PLTR", "sell", 10, 145.60, "PASS", text="Sell 10 shares of PLTR at $145.60 ($1,456). Held 4 days, past your 3-day minimum."),
        j(15, 9, 35, "NVDA", "buy", 40, 183.00, "BLOCK", rule="Position size", template="moving-average pullback", stop=0.06, risk=439.20, routed=False,
          text="Buy 40 shares of NVDA at $183.00 ($7,320). Held. NVDA would be $7,320, or 29% of equity. Your limit is 10% ($2,500). A quantity of 13 shares or fewer would clear this rule."),
        j(14, 10, 22, "QQQ", "buy", 10, 482.00, "PASS", template="moving-average pullback", stop=0.05, risk=241.00,
          text="Buy 10 shares of QQQ at $482.00 ($4,820). Every rule you set is satisfied."),
        j(12, 10, 12, "AAPL", "buy", 20, 228.00, "PASS", template="earnings hold", stop=0.07, risk=319.20,
          text="Buy 20 shares of AAPL at $228.00 ($4,560). Every rule you set is satisfied."),
        j(9, 13, 30, "QQQ", "sell", 10, 489.60, "PASS", text="Sell 10 shares of QQQ at $489.60 ($4,896). Held 5 days, past your 3-day minimum."),
        j(6, 9, 55, "AMD", "buy", 15, 170.50, "PASS", template="MACD cross", stop=0.06, risk=153.45,
          text="Buy 15 shares of AMD at $170.50 ($2,558). Every rule you set is satisfied."),
        j(5, 11, 8, "TSLA", "buy", 10, 272.30, "PASS", template="swing (3 to 10 days)", stop=0.05, risk=136.15,
          text="Buy 10 shares of TSLA at $272.30 ($2,723). Every rule you set is satisfied."),
        j(4, 9, 48, "SPY", "buy", 2, 3.40, "PASS", asset_type="option", contract="SPY 2026-11-20 575 C", risk=680.0,
          text="Buy 2 contracts of SPY 2026-11-20 575 C at $3.40 ($680). Every rule you set is satisfied."),
        j(1, 14, 5, "NVDA", "buy", 8, 191.00, "PASS", template="moving-average pullback", stop=0.06, risk=91.68,
          text="Buy 8 shares of NVDA at $191.00 ($1,528). Every rule you set is satisfied."),
        j(0, 10, 5, "TSLA", "sell", 10, 258.30, "PASS", text="Sell 10 shares of TSLA at $258.30 ($2,583). Held 5 days, but the stop you set ($258.69) has been hit at $258.30. Exiting on your plan is allowed."),
        j(0, 10, 40, "AMD", "sell", 15, 164.20, "PASS", text="Sell 15 shares of AMD at $164.20 ($2,463). Held 6 days, past your 3-day minimum."),
        j(0, 11, 15, "SPY", "buy", 4, 3.40, "BLOCK", rule="Premium at risk", asset_type="option", contract="SPY 2026-11-20 575 C",
          risk=1360.0, routed=False,
          text="Buy 4 contracts of SPY 2026-11-20 575 C at $3.40 ($1,360). Held. Open premium $680 plus this order's $1,360 is $2,040, past your $750 cap."),
    ])
    session.commit()
    session.refresh(acct)
    return acct


def get_or_seed_demo(session: Session, now: datetime | None = None) -> Account:
    acct = session.scalar(select(Account).where(Account.name == DEMO_NAME))
    return acct or seed_demo(session, now)
