import pytest

from initiative_tracker.data import load_initiatives
from initiative_tracker.metrics import compute_health, default_as_of, portfolio_summary
from initiative_tracker.report import (
    _md_table, build_report, get_rephraser, number_problems, summary_facts,
)
from conftest import AS_OF, SAMPLE_CSV


@pytest.fixture
def h(make):
    return compute_health(make(
        {"initiative": "Alpha", "workstream": "Ops", "percent_complete": 50},
        {"initiative": "Beta", "workstream": "Ops", "status": "Blocked", "risk_note": "Legal | pending"},
        {"initiative": "Gamma", "workstream": "Growth", "status": "Done", "percent_complete": 100},
        {"initiative": "Delta", "workstream": "Growth", "percent_complete": 10, "last_update": "2026-09-01"},
    ), AS_OF)


class Fake:
    name = "fake-llm"

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, facts):
        return self.fn(facts)


# --- facts -------------------------------------------------------------------

def test_facts_use_computed_numbers(h):
    s = portfolio_summary(h)
    facts = summary_facts(h)
    assert f"{s['open']} of {s['total']} initiatives are open and {s['done']} are done." in facts
    assert f"{s['red']} red, {s['amber']} amber, {s['green']} green" in facts
    assert "Ops has the most red items (1)." in facts


def test_facts_on_sample_match_summary():
    df = load_initiatives(SAMPLE_CSV)
    h = compute_health(df, default_as_of(df))
    s = portfolio_summary(h)
    assert f"{s['overdue']} are overdue, {s['slipping']} are slipping" in summary_facts(h)


# --- number guard ------------------------------------------------------------

SRC = "3 of 10 initiatives are open. Average completion is 52.5%. No update in over 14 days."


def test_guard_accepts_faithful_rephrase():
    assert number_problems("Over 14 days, 3 of 10 stayed open; average 52.5 percent.", SRC) == []


def test_guard_treats_50_and_50_point_0_as_equal():
    assert number_problems("50%", "50.0%") == []


def test_guard_rejects_added_number():
    assert number_problems("3 of 10 open, 52.5%, 14 days, 30% overall.", SRC) == ["added numbers ['30']"]


def test_guard_rejects_dropped_number():
    assert number_problems("3 of 10 open; average 52.5%.", SRC) == ["dropped numbers ['14']"]


def test_guard_rejects_number_words():
    probs = number_problems("3 of 10 open, a majority stalled, 52.5%, 14 days, two blocked.", SRC)
    assert probs == ["number words ['majority', 'two']"]


# --- build_report ------------------------------------------------------------

def test_template_report_without_model(h):
    r = build_report(h, AS_OF, scope="Ops, Growth")
    assert r.backend == "template" and r.note == ""
    assert summary_facts(h) in r.markdown
    assert "# Weekly initiative status: 2026-10-09" in r.markdown
    assert "Scope: Ops, Growth" in r.markdown
    assert "| 1 | 1 | 1 | 1 | 4 |" in r.markdown                # red amber green done total
    assert "Legal \\| pending" in r.markdown                     # pipes escaped
    assert "| Ann | Delta | 38 |" in r.markdown                  # stale table


def test_llm_rephrase_accepted(h):
    facts = summary_facts(h)
    r = build_report(h, AS_OF, rephraser=Fake(lambda f: "Reworded: " + f))
    assert r.backend == "fake-llm" and r.note == ""
    assert "Reworded: " + facts in r.markdown


def test_llm_invented_number_falls_back(h):
    r = build_report(h, AS_OF, rephraser=Fake(lambda f: f + " Velocity rose 12%."))
    assert r.backend == "template"
    assert "added numbers ['12']" in r.note
    assert "Velocity" not in r.markdown


def test_llm_exception_falls_back(h):
    def boom(_):
        raise TimeoutError("slow")
    r = build_report(h, AS_OF, rephraser=Fake(boom))
    assert r.backend == "template" and "TimeoutError" in r.note


def test_get_rephraser_without_config():
    rephraser, note = get_rephraser({})
    assert rephraser is None and "No model configured" in note


def test_get_rephraser_reports_load_failure(monkeypatch):
    import initiative_tracker.report as rep

    class Broken:
        def __init__(self, *a):
            raise ImportError("no transformers")
    monkeypatch.setattr(rep, "LocalRephraser", Broken)
    rephraser, note = rep.get_rephraser({"LOCAL_MODEL": "x"})
    assert rephraser is None and "ImportError" in note


def test_md_table_empty():
    import pandas as pd
    assert _md_table(pd.DataFrame()) == "_None._"
