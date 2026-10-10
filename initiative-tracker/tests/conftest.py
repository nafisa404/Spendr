import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from initiative_tracker.data import validate  # noqa: E402

AS_OF = pd.Timestamp("2026-10-09")
SAMPLE_CSV = ROOT / "data" / "initiatives.csv"


def _row(**kw):
    base = {
        "initiative": "X",
        "owner": "Ann",
        "workstream": "Ops",
        "start": "2026-09-09",
        "due": "2026-11-08",       # 60-day span; as of 2026-10-09 expected = 50%
        "status": "On track",
        "percent_complete": 50,
        "risk_note": "",
        "last_update": "2026-10-08",
    }
    base.update(kw)
    return base


@pytest.fixture
def make():
    def _make(*rows):
        return validate(pd.DataFrame([_row(**r) for r in rows]))
    return _make
