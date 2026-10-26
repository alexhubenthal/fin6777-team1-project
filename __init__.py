"""AI-enabled trading copilot, early prototype (FIN 6777, Group 1).

The package is organised around one idea: every proposed order is checked
against the account-level rules the user wrote before it reaches a broker.

    rules.py    the deterministic rule engine and the rule definitions
    explain.py  plain-English explanations of each decision and position
    broker.py   broker adapters (simulated by default, Alpaca paper optional)
    journal.py  the journal and the adherence score
    models.py   SQLAlchemy tables (SQLite locally, Postgres/Supabase later)
    seed.py     the demo account used in class
"""

__version__ = "0.1.0"
