"""AI-enabled trading copilot, early prototype. Run: streamlit run app.py"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy import select

from copilot import __version__
from copilot.broker import broker_from_env
from copilot.db import make_session_factory
from copilot.explain import OUTCOME_LABEL, WHY_IT_MATTERS, explain_decision, explain_position, status_of_position
from copilot.journal import (adherence, apply_fill, import_outside_fill, load_state, record, rules_from_row, save_rules)
from copilot.models import ClosedTradeRow, JournalRow
from copilot.quotes import SAMPLE_OPTIONS, SAMPLE_QUOTES, TEMPLATES
from copilot.rules import Decision, Order, RuleSet, TradePlan, evaluate
from copilot.seed import get_or_seed_demo, seed_demo

st.set_page_config(page_title="Copilot prototype", page_icon=None, layout="wide",
                   initial_sidebar_state="expanded")

NAVY, BLUE, AMBER, TEAL, SLATE, MIST = "#132643", "#285CC2", "#BF7B0F", "#008F7D", "#586474", "#EDF2F9"
OUTCOME_COLOR = {"PASS": TEAL, "REVIEW": AMBER, "BLOCK": NAVY}

st.markdown(
    f"""
    <style>
      .block-container {{ padding-top: 3.6rem; max-width: 1180px; }}
      h1, h2, h3 {{ color: {NAVY}; font-weight: 600; letter-spacing: -0.01em; }}
      .kicker {{ color: {SLATE}; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.2rem; }}
      .outcome {{ border-left: 6px solid; padding: 0.9rem 1.1rem; background: {MIST}; border-radius: 4px; margin: 0.6rem 0 1rem 0; }}
      .outcome .label {{ font-weight: 600; font-size: 1.15rem; margin-bottom: 0.25rem; }}
      .outcome p {{ margin: 0.2rem 0; color: {NAVY}; }}
      .why {{ color: {SLATE}; font-size: 0.9rem; font-style: normal; }}
      .muted {{ color: {SLATE}; font-size: 0.85rem; }}
      div[data-testid="stMetricValue"] {{ color: {NAVY}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Shared resources
# --------------------------------------------------------------------------


@st.cache_resource
def session_factory():
    return make_session_factory()


@st.cache_resource
def broker():
    return broker_from_env(SAMPLE_QUOTES)


def now() -> datetime:
    return datetime.now()


def ctx():
    """Open a session and load the demo account, rules and state for this run."""
    session = session_factory()()
    account = get_or_seed_demo(session, now())
    rules = rules_from_row(account.rules)
    state = load_state(session, account, SAMPLE_QUOTES, SAMPLE_OPTIONS, now())
    return session, account, rules, state


def money(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def md(text: str) -> str:
    """Escape dollar signs so Streamlit's markdown does not read them as LaTeX."""
    return text.replace("$", "\\$")


def outcome_card(decision: Decision, text: str) -> None:
    color = OUTCOME_COLOR[decision.outcome]
    label = OUTCOME_LABEL[decision.outcome]
        why_html = f'<p class="why">{why}</p>' if why else ""
    st.markdown(
        f'<div class="outcome" style="border-color:{color}">'
        f'<div class="label" style="color:{color}">{label}</div>'
        f"<p>{text}</p>{why_html}</div>",
        unsafe_allow_html=True,
    )


def findings_table(decision: Decision) -> None:
    rows = [{"Rule": f.rule, "Result": OUTCOME_LABEL[f.outcome], "Detail": f.message} for f in decision.findings]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Rule": st.column_config.TextColumn(width="small"),
                                "Result": st.column_config.TextColumn(width="small"),
                                "Detail": st.column_config.TextColumn(width="large")})


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


def page_overview():
    session, account, rules, state = ctx()
    st.markdown('<div class="kicker">Account</div>', unsafe_allow_html=True)
    st.title(account.name)
    st.markdown('<p class="muted">Sample data. Quotes are static and the broker is simulated; the rule engine, journal and adherence score are the real code paths.</p>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Equity", money(state.equity))
    c2.metric("Cash", money(state.cash))
    c3.metric("Realized today", money(state.realized_pnl_today))
    c4.metric("Losing streak", f"{state.consecutive_losses} close{'s' if state.consecutive_losses != 1 else ''}")
    c5.metric("Orders routed today", f"{state.trades_today} of {rules.max_trades_per_day}")

    st.subheader("Positions, explained")
    if not state.positions:
        st.write("No open positions.")
    for key, pos in state.positions.items():
        status = status_of_position(pos, now(), rules.min_holding_days)
        color = {"Exit due": AMBER, "Holding": SLATE, "Within plan": TEAL}[status]
        left, right = st.columns([1, 4])
        left.markdown(f"**{key}**  \n<span style='color:{color}'>{status}</span>  \n<span class='muted'>{pos.plan.template}</span>", unsafe_allow_html=True)
        right.markdown(md(explain_position(pos, now(), rules.min_holding_days)))

    st.subheader("Budgets used today")
    loss_used = max(0.0, -state.realized_pnl_today) / rules.daily_loss_limit if rules.daily_loss_limit else 0
    prem_used = state.open_premium_at_risk / rules.max_premium_at_risk if rules.max_premium_at_risk else 0
    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown(md(f"Daily loss limit: {money(max(0.0, -state.realized_pnl_today))} of {money(rules.daily_loss_limit)}"))
        st.progress(min(1.0, loss_used))
    with b2:
        st.markdown(md(f"Premium at risk: {money(state.open_premium_at_risk)} of {money(rules.max_premium_at_risk)}"))
        st.progress(min(1.0, prem_used))
    with b3:
        st.write(f"Orders today: {state.trades_today} of {rules.max_trades_per_day}")
        st.progress(min(1.0, state.trades_today / rules.max_trades_per_day))
    session.close()


def page_rules():
    session, account, rules, state = ctx()
    st.markdown('<div class="kicker">Rules</div>', unsafe_allow_html=True)
    st.title("Your rules")
    st.write("Every limit here is yours. The copilot checks each proposed order against them before it reaches a broker, "
             "and it names the rule when it holds an order. Nothing in this table was set by us.")
    st.dataframe(pd.DataFrame(rules.as_rows(), columns=["Rule", "Your setting", "Where it came from"]),
                 hide_index=True, use_container_width=True,
                 column_config={"Rule": st.column_config.TextColumn(width="small"),
                                "Your setting": st.column_config.TextColumn(width="large"),
                                "Where it came from": st.column_config.TextColumn(width="medium")})

    with st.form("rules_form"):
        st.subheader("Change a rule")
        a, b, c = st.columns(3)
        max_position_pct = a.number_input("Position size, % of equity", 1, 100, int(rules.max_position_pct * 100)) / 100
        daily_loss_limit = b.number_input("Daily loss limit, $", 50, 100_000, int(rules.daily_loss_limit), step=50)
        max_premium_at_risk = c.number_input("Premium at risk, $", 0, 100_000, int(rules.max_premium_at_risk), step=50)
        d, e, f = st.columns(3)
        max_margin_pct = d.number_input("Margin use, % of equity (0 = none)", 0, 100, int(rules.max_margin_pct * 100)) / 100
        min_holding_days = e.number_input("Minimum holding period, days", 0, 90, int(rules.min_holding_days))
        max_trades_per_day = f.number_input("Orders per day", 1, 100, int(rules.max_trades_per_day))
        g, h, i = st.columns(3)
        loss_streak_trigger = g.number_input("Cooldown after N losing closes", 1, 20, int(rules.loss_streak_trigger))
        cooldown_minutes = h.number_input("Cooldown length, minutes", 5, 24 * 60, int(rules.cooldown_minutes), step=5)
        plan_required = i.checkbox("Every opening order needs a stop", value=rules.plan_required)
        if st.form_submit_button("Save rules"):
            save_rules(account.rules, RuleSet(
                max_position_pct=max_position_pct, daily_loss_limit=float(daily_loss_limit),
                max_premium_at_risk=float(max_premium_at_risk), max_margin_pct=max_margin_pct,
                min_holding_days=int(min_holding_days), loss_streak_trigger=int(loss_streak_trigger),
                cooldown_minutes=int(cooldown_minutes), plan_required=plan_required,
                max_trades_per_day=int(max_trades_per_day)), now())
            session.commit()
            st.success("Saved. The next order is checked against the new limits.")
            st.rerun()
    session.close()


EXAMPLES = {
    "Passing order: buy 5 MSFT with a 5% stop": dict(asset="stock", symbol="MSFT", side="buy", qty=5, template="MACD cross", stop=5),
    "Held on position size: buy 40 NVDA": dict(asset="stock", symbol="NVDA", side="buy", qty=40, template="moving-average pullback", stop=6),
    "Held on minimum hold: sell 8 NVDA bought yesterday": dict(asset="stock", symbol="NVDA", side="sell", qty=8, template="discretionary", stop=0),
    "Held on premium at risk: buy 4 SPY calls": dict(asset="option", contract="SPY 2026-11-20 575 C", side="buy", qty=4, template="discretionary", stop=0),
    "Review near the daily loss limit: buy 15 PLTR with an 8% stop": dict(asset="stock", symbol="PLTR", side="buy", qty=15, template="swing (3 to 10 days)", stop=8),
    "Held on plan required: buy 5 MSFT with no stop": dict(asset="stock", symbol="MSFT", side="buy", qty=5, template="discretionary", stop=0),
}


def page_check():
    session, account, rules, state = ctx()
    st.markdown('<div class="kicker">Pre-trade check</div>', unsafe_allow_html=True)
    st.title("Check an order")
    st.write("Describe the order the way you would at the broker, add the exit you are committing to, and the copilot "
             "checks it against your rules. It routes only on your confirmation, and only if your rules allow it.")

    if "flash" in st.session_state:
        st.success(md(st.session_state.pop("flash")))

    example = st.selectbox("Load an example for the demo", ["(none)"] + list(EXAMPLES), index=0)
    ex = EXAMPLES.get(example, {})

    asset = st.radio("Instrument", ["stock", "option"], index=0 if ex.get("asset", "stock") == "stock" else 1,
                     horizontal=True, key=f"asset_{example}")
    symbols = list(SAMPLE_QUOTES)
    contracts = list(SAMPLE_OPTIONS)
    with st.form("order_form"):
        b, c, d = st.columns([2, 1, 1])
        if asset == "option":
            contract = b.selectbox("Option contract (sample premium shown on check)", contracts,
                                   index=contracts.index(ex["contract"]) if ex.get("contract") in contracts else 0)
            symbol = SAMPLE_OPTIONS[contract][0]
        else:
            symbol = b.selectbox("Symbol (sample quote used for the check)", symbols,
                                 index=symbols.index(ex.get("symbol", "MSFT")) if ex.get("symbol") in symbols else 0)
            contract = ""
        side = c.radio("Side", ["buy", "sell"], index=0 if ex.get("side", "buy") == "buy" else 1, horizontal=True)
        qty = d.number_input("Quantity", min_value=1, value=int(ex.get("qty", 5)), step=1)
        st.markdown("**Your plan for this trade**")
        e, f, g, h = st.columns(4)
        templates = TEMPLATES
        template = e.selectbox("Entry reason (label only)", templates, index=templates.index(ex.get("template", "discretionary")))
        stop = f.number_input("Stop, % below cost (0 = none)", 0, 50, int(ex.get("stop", 5)))
        target = g.number_input("Target, % above cost (0 = none)", 0, 200, 0)
        max_hold = h.number_input("Time stop, days (0 = none)", 0, 365, 0)
        submitted = st.form_submit_button("Check against my rules")

    if submitted:
        if asset == "option":
            underlying, premium = SAMPLE_OPTIONS[contract]
            order = Order(underlying, side, qty, premium, asset_type="option", contract=contract,
                          plan=TradePlan(stop_pct=stop / 100 or None, target_pct=target / 100 or None,
                                         max_hold_days=max_hold or None, template=template))
        else:
            order = Order(symbol, side, qty, SAMPLE_QUOTES[symbol],
                          plan=TradePlan(stop_pct=stop / 100 or None, target_pct=target / 100 or None,
                                         max_hold_days=max_hold or None, template=template))
        decision = evaluate(order, state, rules, now())
        st.session_state["pending"] = (order, decision, explain_decision(decision))
        st.session_state["ack"] = False

    if "pending" in st.session_state:
        order, decision, text = st.session_state["pending"]
        outcome_card(decision, text)
        findings_table(decision)

        if decision.outcome == "BLOCK":
            st.write("This order will not be routed. The rule that held it is yours to change on the Rules page; "
                     "the copilot does not override it here. If you place the trade at the broker instead, "
                     "the journal will count it against your adherence score.")
            if st.button("Record this held order in the journal"):
                record(session, account, decision, text, now())
                session.commit()
                del st.session_state["pending"]
                st.session_state["flash"] = "Recorded in the journal as held. Nothing was sent to the broker."
                st.rerun()
        else:
            if decision.outcome == "REVIEW":
                st.session_state["ack"] = st.checkbox("I have read the warning and still want this order.", value=st.session_state.get("ack", False))
            ready = decision.outcome == "PASS" or st.session_state.get("ack", False)
            if st.button(f"Confirm and route to {broker().name}", disabled=not ready, type="primary"):
                fill = broker().submit(order, now())
                record(session, account, decision, text, now(), fill=fill)
                apply_fill(session, account, order, fill, now())
                session.commit()
                del st.session_state["pending"]
                st.session_state["flash"] = (f"Routed to {broker().name}. Fill {fill.fill_id}: {fill.side} {fill.qty:g} "
                                             f"{order.contract or order.symbol} at {money(fill.price)}. "
                                             "The journal has the entry and the position is on the Account page.")
                st.rerun()
    session.close()


def page_journal():
    session, account, rules, state = ctx()
    st.markdown('<div class="kicker">Journal</div>', unsafe_allow_html=True)
    st.title("Journal and adherence")
    if "flash" in st.session_state:
        st.info(md(st.session_state.pop("flash")))
    a = adherence(session, account, now())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Adherence, 30 days", f"{a.score:.0%}" if a.score is not None else "n/a",
              help="Share of fills that complied with your rules. Orders the copilot held do not count; trades placed at the broker are checked after the fact.")
    c2.metric("Fills checked", f"{a.fills}", help=f"{a.outside_fills} of them placed outside the copilot and imported")
    c3.metric("Rule breaks", f"{a.breaks}")
    c4.metric("Orders held", f"{a.held}", help=f"Planned risk on held orders: {money(a.held_planned_risk)}")

    left, right = st.columns([1, 2])
    with left:
        st.subheader("Held or broken, by rule")
        if a.by_rule:
            st.dataframe(pd.DataFrame([{"Rule": k, "Count": v} for k, v in a.by_rule.items()]),
                         hide_index=True, use_container_width=True)
        else:
            st.write("Nothing held or broken in the window.")
    with right:
        st.subheader("Import a fill placed at the broker")
        st.write("Trades made in the broker's own app are checked after the fact and count against the score when they would have been held.")
        with st.form("import_form"):
            x, y, z, w = st.columns(4)
            sym = x.selectbox("Symbol", list(SAMPLE_QUOTES), index=list(SAMPLE_QUOTES).index("HOOD"))
            side = y.radio("Side", ["buy", "sell"], horizontal=True)
            qty = z.number_input("Quantity", 1, 10_000, 5)
            stop = w.number_input("Stop stated, %", 0, 50, 0)
            if st.form_submit_button("Import and check"):
                order = Order(sym, side, qty, SAMPLE_QUOTES[sym], plan=TradePlan(stop_pct=stop / 100 or None))
                try:
                    row = import_outside_fill(session, account, order, rules, state, now(), explain_decision)
                    session.commit()
                    st.session_state["flash"] = row.explanation
                    st.rerun()
                except ValueError as err:
                    st.warning(str(err))

    st.subheader("Entries")
    rows = session.scalars(select(JournalRow).where(JournalRow.account_id == account.id).order_by(JournalRow.ts.desc())).all()
    df = pd.DataFrame([{
        "When": r.ts.strftime("%b %d %H:%M"),
        "Order": f"{r.side} {r.qty:g} {r.contract or r.symbol} @ {money(r.price)}",
        "Source": "copilot" if r.source == "copilot" else "broker app",
        "Outcome": OUTCOME_LABEL[r.outcome] + (" (routed)" if r.routed and r.outcome != "BLOCK" else ""),
        "Rule": r.headline_rule or "",
        "Plan": f"{r.plan_template}, stop {r.plan_stop_pct:.0%}" if r.plan_stop_pct else r.plan_template,
        "Explanation": r.explanation,
    } for r in rows])
    st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                 column_config={"When": st.column_config.TextColumn(width="small"),
                                "Source": st.column_config.TextColumn(width="small"),
                                "Rule": st.column_config.TextColumn(width="medium"),
                                "Explanation": st.column_config.TextColumn(width="large")})
    session.close()


def page_about():
    st.markdown('<div class="kicker">About this build</div>', unsafe_allow_html=True)
    st.title("What is real and what is simulated")
    st.write(f"Version {__version__}. Python, Streamlit and SQLAlchemy. The data layer is SQLite on this machine and the same "
             "schema runs on Postgres (Supabase) by changing one connection string. The broker is simulated; the Alpaca "
             "paper-trading adapter uses the same interface and is selected when API keys are present.")
    st.markdown("""
| Layer | In this build | In the product |
|---|---|---|
| Rules and pre-trade check | Real. Deterministic engine, nine checks, 43 scenario tests | Same engine, more rules from user research |
| Explanations | Real. Fixed templates built from the engine's own numbers | A small model rewrites the wording; it never changes the decision |
| Journal and adherence score | Real. Every evaluated order, routed or held, plus imported outside fills | Same, with broker statements imported automatically through SnapTrade |
| Quotes | Static sample quotes | Broker or market-data feed |
| Broker | Simulated fills at the checked price | Alpaca paper first, then live brokers that sanction access |
| Accounts | One demo account, no login | Supabase auth, one rule set per user, read-only broker links |
""")
    st.subheader("Order path")
    st.code("""user writes rules ──▶ proposes an order with an exit
                               │
                               ▼
                  rule engine (pure function, no model)
                     PASS / REVIEW / BLOCK + the rule + the numbers
                               │
              ┌────────────────┼──────────────────┐
              ▼                ▼                   ▼
        BLOCK: journal   REVIEW: user         PASS: user
        as held          acknowledges         confirms
                               └──────────┬────────┘
                                          ▼
                             broker adapter (simulated | Alpaca paper)
                                          ▼
                             fill ──▶ positions, cash, journal, adherence""", language="text")
    st.subheader("Where the rules came from")
    st.write("Four limits come from the Business Model Canvas the team wrote in September: position size, daily loss, "
             "premium at risk and margin use. Three were added after the September 30 class: the minimum holding period "
             "and the losing-streak cooldown came from the room when we asked which rule people would want enforced, and "
             "the plan requirement replaced the strategy-template requirement after the professor asked how a user would "
             "know which template to apply. The trades-per-day guard comes from the research on overtrading.")


# --------------------------------------------------------------------------
# Sidebar and navigation
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown(f"<div style='font-weight:600;font-size:1.1rem;color:{NAVY}'>Copilot</div>"
                f"<div class='muted'>AI-enabled trading copilot, early prototype</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='muted' style='margin-top:0.6rem'>Broker: {broker().name}</div>", unsafe_allow_html=True)
    st.divider()

pages = [
    st.Page(page_overview, title="Account", url_path="account", default=True),
    st.Page(page_rules, title="Rules", url_path="rules"),
    st.Page(page_check, title="Check an order", url_path="check"),
    st.Page(page_journal, title="Journal", url_path="journal"),
    st.Page(page_about, title="About this build", url_path="about"),
]
nav = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.divider()
    with st.expander("Demo controls"):
        if st.button("Reset demo data"):
            s = session_factory()()
            seed_demo(s, now())
            s.close()
            st.session_state.pop("pending", None)
            st.success("Demo account reset.")
            st.rerun()
        if st.button("Simulate a third losing close"):
            s = session_factory()()
            acct = get_or_seed_demo(s, now())
            s.add(ClosedTradeRow(account_id=acct.id, closed_at=now(), symbol="SOFI", qty=20,
                                 entry_price=22.00, exit_price=21.84, realized_pnl=-3.20))
            s.commit()
            s.close()
            st.session_state.pop("pending", None)
            st.success("Third losing close recorded. New entries are on cooldown.")
            st.rerun()
    st.markdown("<div class='muted'>FIN 6777, Group 1. Michael Azzi, Alexander Hubenthal, Hubert Antoniewicz.</div>",
                unsafe_allow_html=True)

nav.run()
