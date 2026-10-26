"""Scenario tests for the rule engine.

Each test is one order against the demo account state. The numbers in the
comments are the ones the engine reports, so a reader can check the
arithmetic by hand. Run with ``pytest -q``.
"""

from datetime import datetime, timedelta

import pytest

from copilot.rules import (AccountState, Order, Position, RuleSet, TradePlan, evaluate)

NOW = datetime(2026, 10, 28, 18, 30)


def demo_state(**overrides) -> AccountState:
    """Equity $25,000: cash $18,186.80 plus AAPL, NVDA and one SPY call."""
    positions = {
        "AAPL": Position("AAPL", 20, 228.00, 232.10, NOW - timedelta(days=12), plan=TradePlan(stop_pct=0.07)),
        "NVDA": Position("NVDA", 8, 191.00, 186.40, NOW - timedelta(days=1), plan=TradePlan(stop_pct=0.06)),
        "SPY 2026-11-20 575 C": Position("SPY 2026-11-20 575 C", 2, 3.40, 3.40, NOW - timedelta(days=4), asset_type="option"),
    }
    state = AccountState(equity=25_000.00, cash=18_186.80, positions=positions,
                         realized_pnl_today=-234.50, consecutive_losses=2, last_loss_at=NOW - timedelta(hours=8),
                         trades_today=2)
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


RULES = RuleSet()


def plan(stop=0.05, template="MACD cross") -> TradePlan:
    return TradePlan(stop_pct=stop, template=template)


def rule(decision, name):
    return next(f for f in decision.findings if f.rule == name)


# ---------------------------------------------------------------- passing


def test_small_buy_with_plan_passes():
    d = evaluate(Order("MSFT", "buy", 5, 418.55, plan=plan()), demo_state(), RULES, NOW)
    assert d.outcome == "PASS"
    assert rule(d, "Position size").used == pytest.approx(2092.75 / 2500, rel=1e-3)   # 8.4 percent of equity
    assert rule(d, "Daily loss limit").used == pytest.approx((234.50 + 104.64) / 500, rel=1e-3)  # 68 percent


def test_pass_lists_every_rule_checked():
    d = evaluate(Order("MSFT", "buy", 5, 418.55, plan=plan()), demo_state(), RULES, NOW)
    names = {f.rule for f in d.findings}
    assert names == {"Plan required", "Position size", "Daily loss limit", "Margin use",
                     "Losing-streak cooldown", "Trades per day"}


def test_sell_after_minimum_hold_passes():
    d = evaluate(Order("AAPL", "sell", 20, 232.10), demo_state(), RULES, NOW)
    assert d.outcome == "PASS"
    assert "Held 12 days" in rule(d, "Minimum holding period").message


# ---------------------------------------------------------------- position size


def test_oversized_buy_is_held_and_names_passing_quantity():
    d = evaluate(Order("NVDA", "buy", 40, 186.40, plan=plan(0.06)), demo_state(), RULES, NOW)
    assert d.outcome == "BLOCK"
    assert d.headline_rule == "Position size"
    # room = 2,500 - 1,491.20 = 1,008.80; 1,008.80 / 186.40 = 5.41 -> 5 shares
    assert rule(d, "Position size").passing_qty == 5
    assert d.passing_qty == 5   # the daily-loss rule allows 23, the tighter rule wins


def test_position_size_counts_the_existing_holding():
    d = evaluate(Order("AAPL", "buy", 1, 232.10, plan=plan()), demo_state(), RULES, NOW)
    # 4,642 + 232.10 = 4,874 against a 2,500 limit: already over before this order
    assert rule(d, "Position size").outcome == "BLOCK"
    assert rule(d, "Position size").passing_qty == 0


def test_position_size_is_a_hard_limit_with_no_review_band():
    # 2,100 / 2,500 = 84 percent of the limit: within the rule is within the rule
    d = evaluate(Order("MSFT", "buy", 5, 420.00, plan=plan(0.02)), demo_state(realized_pnl_today=0.0), RULES, NOW)
    assert rule(d, "Position size").outcome == "PASS"
    assert d.outcome == "PASS"


# ---------------------------------------------------------------- daily loss


def test_daily_loss_limit_blocks_when_projected_loss_exceeds_limit():
    d = evaluate(Order("PLTR", "buy", 40, 142.75, plan=plan(0.08)), demo_state(), RULES, NOW)
    # planned risk 40 * 142.75 * 0.08 = 456.80; with 234.50 already realized = 691.30 > 500
    assert rule(d, "Daily loss limit").outcome == "BLOCK"
    assert rule(d, "Daily loss limit").passing_qty == 23   # (500 - 234.50) / 11.42 = 23.2


def test_daily_loss_review_band():
    d = evaluate(Order("PLTR", "buy", 15, 142.75, plan=plan(0.08)), demo_state(), RULES, NOW)
    # risk 171.30; total 405.80 = 81 percent of 500
    assert d.outcome == "REVIEW"
    assert d.headline_rule == "Daily loss limit"


def test_daily_loss_limit_already_reached_blocks_all_new_risk():
    d = evaluate(Order("MSFT", "buy", 1, 418.55, plan=plan()), demo_state(realized_pnl_today=-500.0), RULES, NOW)
    assert rule(d, "Daily loss limit").outcome == "BLOCK"
    assert "No new risk today" in rule(d, "Daily loss limit").message


def test_daily_loss_does_not_apply_to_sells():
    d = evaluate(Order("AAPL", "sell", 20, 232.10), demo_state(realized_pnl_today=-900.0), RULES, NOW)
    assert all(f.rule != "Daily loss limit" for f in d.findings)
    assert d.outcome == "PASS"


# ---------------------------------------------------------------- premium at risk


def test_options_order_past_premium_cap_is_held():
    d = evaluate(Order("SPY", "buy", 4, 3.40, asset_type="option", contract="SPY 2026-11-20 575 C", plan=plan()),
                 demo_state(), RULES, NOW)
    assert d.outcome == "BLOCK"
    assert d.headline_rule == "Premium at risk"     # 680 + 1,360 = 2,040 against 750


def test_options_order_within_cap_passes():
    state = demo_state(positions={})
    d = evaluate(Order("AAPL", "buy", 1, 4.25, asset_type="option", contract="AAPL 2026-12-18 240 C", plan=plan()),
                 state, RULES, NOW)
    # premium 425 against a 750 cap: 57 percent; daily loss 234.50 + 425 = 659.50 -> that rule blocks instead
    assert rule(d, "Premium at risk").outcome == "PASS"
    assert rule(d, "Daily loss limit").outcome == "BLOCK"


def test_option_premium_counts_in_full_as_planned_risk():
    o = Order("SPY", "buy", 2, 3.40, asset_type="option", contract="SPY 2026-11-20 575 C", plan=plan())
    assert o.planned_risk == pytest.approx(680.0)


# ---------------------------------------------------------------- margin


def test_margin_cap_blocks_borrowing_past_twenty_percent():
    # cash 18,186.80; order 60 * 418.55 = 25,113 -> borrow 6,926 = 27.7 percent of equity
    state = demo_state()
    rules = RuleSet(max_position_pct=1.0, daily_loss_limit=10_000)
    d = evaluate(Order("MSFT", "buy", 60, 418.55, plan=plan(0.01)), state, rules, NOW)
    assert rule(d, "Margin use").outcome == "BLOCK"
    assert rule(d, "Margin use").passing_qty == 55   # (18,186.80 + 5,000) / 418.55 = 55.4


def test_no_margin_rule_blocks_any_borrowing():
    rules = RuleSet(max_margin_pct=0.0, max_position_pct=1.0, daily_loss_limit=10_000)
    d = evaluate(Order("MSFT", "buy", 50, 418.55, plan=plan(0.01)), demo_state(), rules, NOW)
    assert rule(d, "Margin use").outcome == "BLOCK"
    assert "allows no margin" in rule(d, "Margin use").message


def test_cash_purchase_reports_remaining_cash():
    d = evaluate(Order("MSFT", "buy", 5, 418.55, plan=plan()), demo_state(), RULES, NOW)
    assert rule(d, "Margin use").outcome == "PASS"
    assert "$16,094 remains" in rule(d, "Margin use").message


# ---------------------------------------------------------------- minimum hold


def test_sale_inside_minimum_hold_is_held():
    d = evaluate(Order("NVDA", "sell", 8, 186.40), demo_state(), RULES, NOW)
    assert d.outcome == "BLOCK"
    assert d.headline_rule == "Minimum holding period"
    assert "$179.54" in rule(d, "Minimum holding period").message   # 191 * 0.94


def test_sale_inside_minimum_hold_passes_when_stop_is_hit():
    state = demo_state()
    state.positions["NVDA"].last_price = 179.00
    d = evaluate(Order("NVDA", "sell", 8, 179.00), state, RULES, NOW)
    assert d.outcome == "PASS"
    assert "Exiting on your plan" in rule(d, "Minimum holding period").message


def test_sale_inside_minimum_hold_passes_when_target_is_reached():
    state = demo_state()
    state.positions["NVDA"].plan.target_pct = 0.03
    state.positions["NVDA"].last_price = 197.00
    d = evaluate(Order("NVDA", "sell", 8, 197.00), state, RULES, NOW)
    assert d.outcome == "PASS"


def test_sale_of_unknown_symbol_is_held():
    d = evaluate(Order("TSLA", "sell", 1, 258.30), demo_state(), RULES, NOW)
    assert d.outcome == "BLOCK"


# ---------------------------------------------------------------- cooldown


def test_third_losing_close_starts_cooldown():
    state = demo_state(consecutive_losses=3, last_loss_at=NOW - timedelta(minutes=10))
    d = evaluate(Order("MSFT", "buy", 1, 418.55, plan=plan()), state, RULES, NOW)
    assert d.outcome == "BLOCK"
    assert d.headline_rule == "Losing-streak cooldown"
    assert "20 minutes remain" in rule(d, "Losing-streak cooldown").message   # 30 minus 10


def test_cooldown_ends_after_thirty_minutes():
    state = demo_state(consecutive_losses=3, last_loss_at=NOW - timedelta(minutes=31))
    d = evaluate(Order("MSFT", "buy", 1, 418.55, plan=plan()), state, RULES, NOW)
    assert rule(d, "Losing-streak cooldown").outcome == "PASS"


def test_two_losses_do_not_trigger_cooldown():
    d = evaluate(Order("MSFT", "buy", 1, 418.55, plan=plan()), demo_state(), RULES, NOW)
    assert rule(d, "Losing-streak cooldown").outcome == "PASS"
    assert "2 consecutive losing closes" in rule(d, "Losing-streak cooldown").message


def test_cooldown_does_not_stop_a_sale():
    state = demo_state(consecutive_losses=3, last_loss_at=NOW - timedelta(minutes=5))
    d = evaluate(Order("AAPL", "sell", 20, 232.10), state, RULES, NOW)
    assert d.outcome == "PASS"


# ---------------------------------------------------------------- plan required


def test_opening_order_without_exit_is_held():
    d = evaluate(Order("MSFT", "buy", 5, 418.55), demo_state(), RULES, NOW)
    assert d.outcome == "BLOCK"
    assert d.headline_rule == "Plan required"


def test_plan_rule_can_be_switched_off():
    d = evaluate(Order("MSFT", "buy", 5, 418.55), demo_state(), RuleSet(plan_required=False), NOW)
    assert d.outcome == "PASS"


def test_adding_to_a_position_past_its_stop_is_held():
    state = demo_state()
    state.positions["NVDA"].last_price = 178.00   # stop 179.54 hit
    d = evaluate(Order("NVDA", "buy", 1, 178.00, plan=plan()), state, RULES, NOW)
    assert d.outcome == "BLOCK"
    assert "past the stop you set" in d.blocking[0].message


# ---------------------------------------------------------------- trade count


def test_ninth_order_of_the_day_is_held():
    d = evaluate(Order("MSFT", "buy", 1, 418.55, plan=plan()), demo_state(trades_today=8), RULES, NOW)
    assert rule(d, "Trades per day").outcome == "BLOCK"


def test_seventh_order_of_the_day_is_a_review():
    d = evaluate(Order("MSFT", "buy", 1, 418.55, plan=plan()), demo_state(trades_today=6), RULES, NOW)
    assert rule(d, "Trades per day").outcome == "REVIEW"   # 7 of 8 = 88 percent


# ---------------------------------------------------------------- combination and ordering


def test_block_beats_review_and_blocking_findings_come_first():
    d = evaluate(Order("NVDA", "buy", 40, 186.40, plan=plan(0.06)), demo_state(), RULES, NOW)
    assert d.outcome == "BLOCK"
    assert [f.outcome for f in d.findings] == sorted([f.outcome for f in d.findings], key={"BLOCK": 0, "REVIEW": 1, "PASS": 2}.get)
    assert len(d.blocking) == 2   # position size and daily loss


def test_invalid_quantity_is_rejected():
    d = evaluate(Order("MSFT", "buy", 0, 418.55, plan=plan()), demo_state(), RULES, NOW)
    assert d.outcome == "BLOCK"


def test_engine_is_deterministic():
    o = Order("MSFT", "buy", 5, 418.55, plan=plan())
    a = evaluate(o, demo_state(), RULES, NOW)
    b = evaluate(o, demo_state(), RULES, NOW)
    assert [(f.rule, f.outcome, f.message) for f in a.findings] == [(f.rule, f.outcome, f.message) for f in b.findings]
