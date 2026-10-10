import pandas as pd
import pytest

from initiative_tracker.data import STATUSES, load_initiatives, validate
from conftest import SAMPLE_CSV, _row


def frame(**kw):
    return pd.DataFrame([_row(**kw)])


def test_sample_csv_loads():
    df = load_initiatives(SAMPLE_CSV)
    assert len(df) == 40
    assert set(df["status"]) <= set(STATUSES)
    assert pd.api.types.is_datetime64_any_dtype(df["due"])
    assert df["percent_complete"].between(0, 100).all()


def test_missing_column():
    with pytest.raises(ValueError, match="Missing columns: owner"):
        validate(frame().drop(columns="owner"))


def test_unknown_status():
    with pytest.raises(ValueError, match="Unknown status"):
        validate(frame(status="Green"))


@pytest.mark.parametrize("pct", [-1, 101, "abc"])
def test_bad_percent(pct):
    with pytest.raises(ValueError, match="percent_complete"):
        validate(frame(percent_complete=pct))


def test_bad_date():
    with pytest.raises(ValueError, match="'due'"):
        validate(frame(due="next week"))


def test_due_before_start():
    with pytest.raises(ValueError, match="Due date before start"):
        validate(frame(start="2026-10-01", due="2026-09-01"))


def test_blank_risk_note_becomes_empty_string():
    df = validate(frame(risk_note=None))
    assert df.loc[0, "risk_note"] == ""
