"""Smoke test: extract a sample, review flags, approval gating, edits withdraw approval."""
import pandas as pd
from streamlit.testing.v1 import AppTest

from conftest import ROOT


def downloads_disabled(at):
    return [d.proto.disabled for d in at.get("download_button")]


def started(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_MODEL", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.selectbox(key="sample").select("01_launch_sync").run()
    at.button[0].click().run()
    assert not at.exception
    return at


def test_extract_and_flag(monkeypatch):
    at = started(monkeypatch)
    ex = at.session_state.extraction
    assert ex.backend == "rules" and len(ex.action_items) == 5
    assert "No model configured" in at.info[0].value
    assert any("3 item(s) flagged" in m.value for m in at.markdown)
    assert "3 action item(s) still lack an owner or date" in at.warning[0].value


def test_exports_disabled_until_approved(monkeypatch):
    at = started(monkeypatch)
    assert downloads_disabled(at) == [True, True, True]
    at.checkbox(key="approved").check().run()
    assert downloads_disabled(at) == [False, False, False]


def test_reextract_withdraws_approval(monkeypatch):
    at = started(monkeypatch)
    at.checkbox(key="approved").check().run()
    at.button[0].click().run()
    assert not at.session_state.approved
    assert downloads_disabled(at) == [True, True, True]
