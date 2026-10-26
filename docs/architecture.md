# Architecture notes

## Stack alignment with the Week 6 project plan

The project plan named Python on Streamlit and Supabase for the working prototype, Alpaca paper trading for the order checks, SnapTrade for read-only connections to real accounts, and a small hosted model for explanations. This build keeps every one of those choices and defers the parts that need keys or a live account.

| Plan (October 10) | This build (October 28) |
|---|---|
| Python on Streamlit | Streamlit 1.66, Python 3.11 or later |
| Supabase | SQLAlchemy models on SQLite; `DATABASE_URL` switches to Postgres with no code change |
| Alpaca paper trading | `AlpacaPaperBroker` adapter behind the same interface as the simulator; first live run pending keys |
| SnapTrade read-only | Not yet. The journal's outside-fill import stands in for it |
| Small hosted model for explanations | `Rewriter` interface; `NullRewriter` in this build. The engine, not the model, decides |

## Order path

```
user writes rules ──▶ proposes an order with an exit
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
                             fill ──▶ positions, cash, journal, adherence
```

Design rules the team adopted from the speaker sessions:

- The decision is deterministic and traceable to a line of code (Krishnamoorthy, Week 2: models inform the inputs, a deterministic engine makes the decision, and anyone can ask why).
- Anything uncertain goes to the user, not to the broker (Cannon, Week 8: route low-confidence decisions to a person). REVIEW is that path.
- The five requirements of a payment apply to the order path (Subramanian, Week 4): the broker account is the identity, the order message parses the same on both sides, buying power is checked before routing, the fill is finality, the journal is recourse.

## Data model

| Table | Holds |
|---|---|
| `accounts` | name, cash |
| `rule_sets` | one row per account: the eight limits and their last update |
| `positions` | symbol or contract, quantity, average cost, opened_at, the plan (stop, target, time stop, template) |
| `journal` | one row per evaluated order: order, source (copilot or broker import), outcome, headline rule, explanation, plan, planned risk, routed flag, fill id, broker, rule_break flag |
| `closed_trades` | realized P&L per close, used for the daily loss total and the losing streak |

Account state for a check is computed from these tables at the time of the check: equity, cash, positions with current prices, realized P&L today, the trailing streak of losing closes and when the last one happened, and the count of orders routed today.

## Rule engine

`copilot/rules.py`. `evaluate(order, account_state, rules, now)` runs nine checks and returns a `Decision` with every finding, sorted so the reason is first:

1. Plan required (opening orders carry a stop)
2. Adding to a position past its own stop
3. Position size after the order, against a share of equity
4. Premium at risk after the order (options)
5. Daily loss limit: realized today plus the order's planned risk
6. Margin use after the order
7. Minimum holding period (sales), with exits on plan allowed
8. Losing-streak cooldown (opening orders)
9. Trades per day

Budget rules (daily loss, premium at risk, trades per day) warn at 80 percent of the limit. Structural limits (position size, margin) are pass or hold. Where a rule holds an order, the engine computes the largest quantity that would pass, and the explanation says so.

## Adherence score

Share of fills in the trailing 30 days that complied with the rules. Fills routed by the copilot always comply, since the engine would have held them otherwise. Fills imported from a broker statement are checked after the fact and count as breaks when they would have been held. Held orders do not count against the score; they are reported separately with the planned risk that never went out.

Known simplification: an imported fill is checked against the account state at import time, not at the fill's timestamp. The product will snapshot state per fill.

## Tests

`pytest -q` runs 43 scenarios: every rule at its boundary, the review band, exits on plan inside the minimum hold, the cooldown clock, combined breaches and their ordering, booking a fill, realized P&L and the streak, adherence with outside fills, the broker adapters, and the explanation text matching the engine's numbers. One more test compiles `app.py` and renders its default page, so a broken app script fails the suite.

## Security and regulation, as built

- No credentials stored. The Alpaca adapter reads keys from the environment and the prototype never asks the user for broker passwords.
- The copilot routes only on the user's confirmation and never holds customer money. Nothing in the order path recommends a security; the rules and the plan are the user's own.
- Every held order is journaled with the rule and the numbers, which is the audit trail a broker or a regulator would ask for.
