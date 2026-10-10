"""Smoke test: the app renders on sample data and the generate -> approve -> export flow works."""
from streamlit.testing.v1 import AppTest

from conftest import ROOT


def run_app(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_MODEL", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    return at.run()


def test_renders_with_sample_data(monkeypatch):
    at = run_app(monkeypatch)
    assert not at.exception
    assert [m.label for m in at.metric] == ["Open", "Red", "Amber", "Overdue", "Slipping", "Stale"]
    assert at.metric[0].value == "30"


def test_report_requires_approval(monkeypatch):
    at = run_app(monkeypatch)
    at.button[0].click().run()
    assert not at.exception
    assert at.text_area[0].value.startswith("# Weekly initiative status: 2026-10-07")
    assert "No model configured" in at.info[0].value
    assert not at.checkbox[0].value

    at.checkbox[0].check().run()
    assert at.session_state.approved

    at.text_area[0].input("# Edited").run()      # editing withdraws approval
    assert not at.session_state.approved
