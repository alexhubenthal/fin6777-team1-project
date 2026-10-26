# Working notes for this repository

This is the FIN 6777 Group 1 prototype: an AI-enabled trading copilot that checks every proposed order against the user's own account-level rules before a broker sees it. Read `README.md` first, then `docs/architecture.md`. Repository setup and the team workflow are in `docs/repository-setup.md`.

## Conventions

- `pytest -q` must pass before any commit. The suite is fast (a few seconds).
- A new or changed rule needs four things in the same change: the check in `copilot/rules.py` (and a row in `RuleSet.as_rows()` if the user sets it), at least one scenario test in `tests/test_rules.py` with the arithmetic in a comment, a row in the rules table in `README.md`, and an entry in the numbered check list in `docs/architecture.md`.
- The engine stays a pure function with no model call, no database and no network inside `evaluate()`. Explanations are built from the engine's numbers; a model may reword, never redecide.
- The demo seed (`copilot/seed.py`) is what the class sees. Do not change its numbers in the week of a presentation; the deck's screenshots and speaker notes quote them.
- Writing style in docs and the UI: plain sentences, no em dashes, no marketing adjectives. Say what the code does.
- Do not commit `data/*.db`, `.env` or `.streamlit/secrets.toml` (all are ignored). Keys come from the environment only.

## Layout

See the Layout section of `README.md`. The Streamlit app is `app.py`; pages are functions in that file registered with `st.navigation`.

## Useful commands

```bash
pip install -r requirements.txt
pytest -q
streamlit run app.py
```
