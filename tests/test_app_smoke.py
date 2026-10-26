"""Smoke test: app.py compiles and its default page renders without raising.

The scenario tests cover the engine, journal and broker; none of them loads
app.py, so a syntax error or a missing name there would not fail the suite.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent / "app.py"


def test_app_script_compiles_and_renders():
    compile(APP.read_text(), str(APP), "exec")
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.title, "the app rendered no page title"
