# Copilot, early prototype

An AI-enabled trading copilot for retail options and margin traders. The user writes account-level rules; every proposed order is checked against them before it reaches a broker; the copilot explains each decision and each position in plain English and keeps one journal and one adherence score across brokers.

FIN 6777 FinTech Entrepreneurship, Group 1: Michael Azzi, Alexander Hubenthal, Hubert Antoniewicz. Week 8 checkpoint deliverable (early prototype), presented Week 10.

## What is real and what is simulated

| Layer | This build | The product |
|---|---|---|
| Rules and pre-trade check | Real. A deterministic engine with nine checks and 43 scenario tests | Same engine, more rules from user research |
| Explanations | Real. Fixed templates built from the engine's own numbers | A small model rewrites the wording and never changes the decision |
| Journal and adherence score | Real. Every evaluated order, routed or held, plus fills imported from a broker statement | Same, with statements imported through SnapTrade |
| Quotes | Static sample quotes in `copilot/quotes.py` | Broker or market-data feed |
| Broker | Simulated: fills at the checked price | Alpaca paper trading first (adapter included, not yet exercised), then brokers that sanction access |
| Accounts | One demo account, no login | Supabase auth, one rule set per user |

## Run it

Needs Python 3.11 or later (the test workflow runs 3.12).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1   cmd: .venv\Scripts\activate.bat
pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints a local URL; open http://localhost:8501 in your browser (the app does not open one itself). The demo account is seeded on first run. `Demo controls` in the sidebar resets the data or records a third losing close to trigger the cooldown.

Tests:

```bash
pytest -q        # 43 scenarios across the rule engine, journal, adherence score and broker adapter, plus an app smoke test
```

## The rules in this build

| Rule | Demo setting | Where it came from |
|---|---|---|
| Position size | No position above 10% of equity | Business Model Canvas, v1.0 |
| Daily loss limit | Today's realized loss plus the order's planned risk may not pass $500 | Canvas, v1.0 |
| Premium at risk | Open long-option premium capped at $750 | Canvas, v1.0 |
| Margin use | Borrowing capped at 20% of equity | Canvas, v1.0 |
| Minimum holding period | No sale inside 3 days unless the plan's stop or target is hit | Class discussion, Sep 30 |
| Losing-streak cooldown | After 3 consecutive losing closes, no new entries for 30 minutes | Class discussion, Sep 30 |
| Plan required | Every opening order states a stop before it is checked | Professor's question, Sep 30 |
| Trades per day | At most 8 routed orders a day | Research on overtrading |

Three outcomes. **Clear to route** goes to the broker on the user's confirmation. **Review before routing** means a budget is 80% used or more (the daily loss limit, the premium cap, or the day's order count); the user acknowledges the warning first. **Held by your rules** never routes, and the user interface has no override. A trade placed at the broker's own app can be imported; it is checked after the fact and counts against the adherence score when it would have been held.

## Demo in two minutes

Open `Check an order` and use the example picker:

1. Held on position size: buy 40 NVDA. The copilot names the rule, the numbers, and the largest quantity that would pass.
2. Held on minimum hold: sell 8 NVDA bought yesterday. The stop has not been hit, so this is a change of mind, not an exit on plan.
3. Held on premium at risk: buy 4 SPY calls.
4. Review near the daily loss limit: buy 15 PLTR with an 8% stop. Nothing breached; 81% of the daily budget used.
5. Passing order: buy 5 MSFT with a 5% stop. Confirm, and the fill shows up in the journal and on the Account page.

Then `Journal` for the adherence score, and `Demo controls` to record a third losing close and show the cooldown.

## Configuration

Copy `.env.example`. `DATABASE_URL` switches the data layer from SQLite to Postgres (Supabase) with no code change. `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` select the Alpaca paper-trading adapter (`pip install alpaca-py`); without them the simulated broker is used.

## Layout

```
app.py                 Streamlit app: Account, Rules, Check an order, Journal, About
copilot/rules.py       rule definitions and the engine (pure function)
copilot/db.py          engine and session factory: SQLite under data/, or DATABASE_URL
copilot/quotes.py      static sample quotes and option contracts
copilot/explain.py     plain-English explanations; model rewriter hook (no-op here)
copilot/broker.py      broker adapters: simulated, Alpaca paper
copilot/journal.py     state loading, booking fills, adherence score, outside-fill import
copilot/models.py      SQLAlchemy tables
copilot/seed.py        the demo account
tests/                 scenario tests
docs/                  architecture, demo script, repository setup, peer-test script and log, screenshots
```

## Next two weeks

- First live run of the Alpaca paper adapter on a team member's keys; equities only.
- Snapshot the account state at the fill's timestamp when importing outside fills (the prototype checks against the state at import time).
- Supabase auth and one rule set per user; move the demo database to Postgres.
- Model-rewritten explanations behind the `Rewriter` interface, with the decision and figures fixed by the engine.
- Rules the peer test asks for, in the order the test ranks them.

## Contributions

Antoniewicz: prototype scope, demo. Azzi: peer test and feedback. Hubenthal: stack and feasibility, repository setup.
