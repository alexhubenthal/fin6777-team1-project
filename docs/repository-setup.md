# Repository setup and team workflow

Repository: https://github.com/alexhubenthal/fin6777-team1-project. Owner: Alex. Collaborators with push access: Hubert, Michael.

## Get the code running on your machine

```bash
git clone https://github.com/alexhubenthal/fin6777-team1-project.git
cd fin6777-team1-project
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1   cmd: .venv\Scripts\activate.bat
pip install -r requirements.txt
pytest -q                        # expect: 44 passed
streamlit run app.py             # then open http://localhost:8501 in your browser
```

Needs Python 3.11 or later. If PowerShell refuses to run `Activate.ps1` ("running scripts is disabled on this system"), run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `activate.bat` from cmd.

The SQLite file is created under `data/` on first run. `Demo controls` in the sidebar resets it.

## How we work in the repository

- Changes to `main` go through a branch and a pull request, and the `tests` workflow must pass before the merge. A ruleset on `main` enforces this while the repository is public; GitHub Free does not enforce rulesets on private repositories, so if the repository is made private the rule holds by agreement.
- Name branches `<your-name>/<short-topic>`, for example `hubert/alpaca-first-run`.
- Run `pytest -q` before every push. A pull request with a red workflow is not reviewed.
- A new or changed rule needs the check, a scenario test, the row in the README rules table and the entry in the architecture check list, all in the same pull request. The conventions are in `CONTRIBUTING.md`.
- Keep commit messages to one plain sentence about what changed.

## What not to commit

- `data/*.db`, `.env`, `.streamlit/secrets.toml`, or any API key. The Alpaca adapter reads keys from the environment. All three paths are in `.gitignore`.
- Do not change `copilot/seed.py` before the October 28 class; the deck quotes its numbers.
- `alpaca-py` stays optional. Install it only when testing the paper adapter.

## Continuous integration

`.github/workflows/tests.yml` installs `requirements.txt` and runs `pytest -q` on Python 3.12 for every push and every pull request. The check is named `pytest` in the pull request's checks list.

## Next assignments

- Hubert: create Alpaca paper-trading keys, export `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`, `pip install alpaca-py`, start the app and route one small equity order; paste the Alpaca order id from the journal into the next deck.
- Michael: run the peer sessions from `docs/peer-test-script.md`, add one row per session to `docs/peer-test-log.csv`, and fill the results table on slide 6 Tuesday night.
- Alex: Supabase project, `DATABASE_URL` in `.env`, and the budget rework for the Week 10 draft.
