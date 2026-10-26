"""Journal, adherence and broker adapter tests, against an in-memory database."""

from datetime import datetime, timedelta

import pytest

from copilot.broker import SimulatedBroker, broker_from_env
from copilot.db import make_session_factory
from copilot.explain import explain_decision
from copilot.journal import adherence, apply_fill, import_outside_fill, load_state, record, rules_from_row
from copilot.models import Account
from copilot.quotes import SAMPLE_OPTIONS, SAMPLE_QUOTES
from copilot.rules import Order, TradePlan, evaluate
from copilot.seed import seed_demo

NOW = datetime(2026, 10, 28, 18, 30)


@pytest.fixture
def session():
    factory = make_session_factory("sqlite://")
    with factory() as s:
        yield s


@pytest.fixture
def account(session) -> Account:
    return seed_demo(session, NOW)


def test_seeded_equity_is_twenty_five_thousand(session, account):
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    assert state.equity == pytest.approx(25_000.00, abs=0.01)
    assert state.realized_pnl_today == pytest.approx(-234.50)
    assert state.consecutive_losses == 2
    assert state.trades_today == 2


def test_seeded_adherence_counts_outside_breaks_but_not_held_orders(session, account):
    a = adherence(session, account, NOW)
    assert a.fills == 15
    assert a.breaks == 2
    assert a.held == 3
    assert a.outside_fills == 2
    assert a.score == pytest.approx(13 / 15)
    assert a.by_rule["Premium at risk"] == 2


def test_passing_order_routes_books_and_journals(session, account):
    rules = rules_from_row(account.rules)
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    order = Order("MSFT", "buy", 5, 418.55, plan=TradePlan(stop_pct=0.05, template="MACD cross"))
    decision = evaluate(order, state, rules, NOW)
    assert decision.outcome == "PASS"
    fill = SimulatedBroker(SAMPLE_QUOTES).submit(order, NOW)
    record(session, account, decision, explain_decision(decision), NOW, fill=fill)
    apply_fill(session, account, order, fill, NOW)
    session.commit()
    after = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    assert after.cash == pytest.approx(18_186.80 - 2_092.75)
    assert after.positions["MSFT"].qty == 5
    assert after.trades_today == 3
    assert adherence(session, account, NOW).fills == 16


def test_sell_books_realized_pnl_and_extends_streak(session, account):
    rules = rules_from_row(account.rules)
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    order = Order("AAPL", "sell", 20, 232.10)
    decision = evaluate(order, state, rules, NOW)
    assert decision.outcome == "PASS"
    fill = SimulatedBroker().submit(order, NOW)
    record(session, account, decision, explain_decision(decision), NOW, fill=fill)
    closed = apply_fill(session, account, order, fill, NOW)
    session.commit()
    assert closed.realized_pnl == pytest.approx(82.0)   # (232.10 - 228.00) * 20
    after = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    assert after.consecutive_losses == 0               # a winning close resets the streak
    assert "AAPL" not in after.positions


def test_held_order_is_journaled_but_not_booked(session, account):
    rules = rules_from_row(account.rules)
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    order = Order("NVDA", "buy", 40, 186.40, plan=TradePlan(stop_pct=0.06))
    decision = evaluate(order, state, rules, NOW)
    record(session, account, decision, explain_decision(decision), NOW)
    session.commit()
    a = adherence(session, account, NOW)
    assert a.held == 4
    assert a.fills == 15
    assert load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW).positions["NVDA"].qty == 8


def test_outside_fill_that_breaks_a_rule_lowers_the_score(session, account):
    rules = rules_from_row(account.rules)
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    row = import_outside_fill(session, account, Order("HOOD", "buy", 5, 118.60), rules, state, NOW, explain_decision)
    session.commit()
    assert row.rule_break is True
    assert row.explanation.startswith("Placed outside the copilot.")
    a = adherence(session, account, NOW)
    assert a.fills == 16 and a.breaks == 3
    assert a.score == pytest.approx(13 / 16)


def test_outside_fill_that_complies_keeps_the_score(session, account):
    rules = rules_from_row(account.rules)
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    row = import_outside_fill(session, account, Order("HOOD", "buy", 5, 118.60, plan=TradePlan(stop_pct=0.05)),
                              rules, state, NOW, explain_decision)
    session.commit()
    assert row.rule_break is False
    assert adherence(session, account, NOW).score == pytest.approx(14 / 16)


def test_simulated_broker_fills_at_checked_price():
    broker = SimulatedBroker({"MSFT": 418.55})
    fill = broker.submit(Order("MSFT", "buy", 5, 418.55), NOW)
    assert fill.price == 418.55 and fill.qty == 5 and fill.fill_id.startswith("SIM-")
    assert broker.last_price("MSFT") == 418.55


def test_broker_from_env_defaults_to_simulator(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    assert isinstance(broker_from_env(), SimulatedBroker)


def test_explanation_matches_decision_numbers(session, account):
    rules = rules_from_row(account.rules)
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, NOW)
    d = evaluate(Order("NVDA", "buy", 40, 186.40, plan=TradePlan(stop_pct=0.06)), state, rules, NOW)
    text = explain_decision(d)
    assert text.startswith("Buy 40 shares of NVDA at $186.40 ($7,456).")
    assert "Held." in text and "36% of equity" in text
    assert "A quantity of 5 shares or fewer" in text
    assert "daily loss limit" in text


def test_reseed_replaces_the_demo_account(session, account):
    account.cash = 1.0
    session.commit()
    fresh = seed_demo(session, NOW)
    assert fresh.cash == pytest.approx(18_186.80)
