import pandas as pd
import pytest

from initiative_tracker.data import load_initiatives
from initiative_tracker.metrics import (
    compute_health, default_as_of, portfolio_summary, rollup, top_risks,
)
from conftest import AS_OF, SAMPLE_CSV


def one(make, **kw):
    return compute_health(make(kw), AS_OF).iloc[0]


# --- expected progress -------------------------------------------------------

def test_expected_pct_is_linear_elapsed_share(make):
    r = one(make)
    assert r["expected_pct"] == 50.0
    assert r["schedule_gap"] == 0.0


def test_expected_pct_zero_before_start_and_capped_at_100(make):
    assert one(make, start="2026-11-01", due="2026-12-01", percent_complete=0)["expected_pct"] == 0.0
    assert one(make, start="2026-01-01", due="2026-02-01")["expected_pct"] == 100.0


# --- overdue -----------------------------------------------------------------

def test_overdue_when_due_before_as_of(make):
    r = one(make, start="2026-09-01", due="2026-10-08")
    assert r["overdue"] and r["days_overdue"] == 1 and r["health"] == "Red"


def test_not_overdue_on_due_date(make):
    r = one(make, start="2026-09-01", due="2026-10-09", percent_complete=100)
    assert not r["overdue"] and r["days_overdue"] == 0


def test_done_past_due_is_not_overdue(make):
    r = one(make, start="2026-08-01", due="2026-09-01", status="Done", percent_complete=100,
            last_update="2026-08-01")
    assert not r["overdue"] and not r["stale"] and r["days_overdue"] == 0
    assert r["health"] == "Done" and r["flags"] == ""


# --- slipping ----------------------------------------------------------------

def test_slipping_threshold_is_strictly_more_than_15_points(make):
    assert not one(make, percent_complete=35)["slipping"]   # gap -15
    r = one(make, percent_complete=34)                        # gap -16
    assert r["slipping"] and r["health"] == "Amber"
    assert "Slipping 16 pts behind plan" in r["flags"]


def test_overdue_item_is_not_also_slipping(make):
    r = one(make, start="2026-09-01", due="2026-10-01", percent_complete=10)
    assert r["overdue"] and not r["slipping"]


# --- stale -------------------------------------------------------------------

def test_stale_boundary(make):
    assert not one(make, last_update="2026-09-25")["stale"]   # 14 days
    r = one(make, last_update="2026-09-24")                    # 15 days
    assert r["stale"] and r["days_since_update"] == 15 and r["health"] == "Amber"


# --- health precedence & flags ----------------------------------------------

@pytest.mark.parametrize("kw,health", [
    ({}, "Green"),
    ({"status": "At risk"}, "Amber"),
    ({"status": "Blocked"}, "Red"),
    ({"status": "Blocked", "last_update": "2026-09-01"}, "Red"),
    ({"status": "Done", "percent_complete": 100}, "Done"),
])
def test_health(make, kw, health):
    assert one(make, **kw)["health"] == health


def test_status_mismatch_flag(make):
    r = one(make, start="2026-09-01", due="2026-10-01", status="On track", percent_complete=90)
    assert r["status_mismatch"]
    assert r["flags"] == "Overdue 8d; Status 'On track' contradicts schedule"


def test_self_reported_at_risk_is_not_a_mismatch(make):
    assert not one(make, status="At risk", percent_complete=0)["status_mismatch"]


# --- rollups -----------------------------------------------------------------

@pytest.fixture
def portfolio(make):
    return compute_health(make(
        {"initiative": "a", "workstream": "Ops", "owner": "Ann", "percent_complete": 50},
        {"initiative": "b", "workstream": "Ops", "owner": "Ann", "status": "Blocked", "percent_complete": 50},
        {"initiative": "c", "workstream": "Ops", "owner": "Bo", "status": "Done", "percent_complete": 100},
        {"initiative": "d", "workstream": "Growth", "owner": "Bo", "percent_complete": 10},   # slipping
        {"initiative": "e", "workstream": "Growth", "owner": "Bo", "start": "2026-09-01",
         "due": "2026-10-01", "percent_complete": 90, "last_update": "2026-09-01"},          # overdue + stale
    ), AS_OF)


def test_rollup_by_workstream(portfolio):
    r = rollup(portfolio, "workstream").set_index("workstream")
    assert r.loc["Ops"].to_dict() == {
        "initiatives": 3, "done": 1, "red": 1, "amber": 0, "green": 1, "overdue": 0,
        "slipping": 0, "stale": 0, "blocked": 1, "avg_pct_complete": pytest.approx(66.7),
    }
    assert r.loc["Growth", "red"] == 1 and r.loc["Growth", "amber"] == 1
    assert r.loc["Growth", "avg_pct_complete"] == 50.0


def test_rollup_by_owner_sorted_worst_first(portfolio):
    r = rollup(portfolio, "owner")
    assert list(r["owner"]) == ["Bo", "Ann"]          # Bo: 1 red 1 amber; Ann: 1 red 0 amber
    assert r["initiatives"].sum() == len(portfolio)


def test_portfolio_summary(portfolio):
    s = portfolio_summary(portfolio)
    assert s == {
        "total": 5, "open": 4, "done": 1, "red": 2, "amber": 1, "green": 1,
        "overdue": 1, "slipping": 1, "stale": 1, "blocked": 1, "at_risk": 0,
        "status_mismatch": 2, "avg_pct_open": 50.0,
    }


def test_top_risks_order(portfolio):
    t = top_risks(portfolio)
    assert list(t["initiative"]) == ["e", "b", "d"]   # most overdue red, other red, then amber
    assert list(t["health"]) == ["Red", "Red", "Amber"]


# --- sample data invariants ----------------------------------------------------

def test_sample_invariants():
    df = load_initiatives(SAMPLE_CSV)
    as_of = default_as_of(df)
    assert as_of == df["last_update"].max()
    h = compute_health(df, as_of)
    s = portfolio_summary(h)
    assert s["red"] + s["amber"] + s["green"] + s["done"] == s["total"] == 40
    assert s["open"] + s["done"] == 40
    by_ws = rollup(h, "workstream")
    assert by_ws["initiatives"].sum() == 40
    assert by_ws["red"].sum() == s["red"]
    assert pd.Series(h["flags"].ne("")).sum() == s["red"] + s["amber"]
