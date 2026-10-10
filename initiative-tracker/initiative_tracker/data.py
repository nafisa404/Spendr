"""Load and validate initiative CSVs."""
import pandas as pd

COLUMNS = [
    "initiative", "owner", "workstream", "start", "due",
    "status", "percent_complete", "risk_note", "last_update",
]
DATE_COLUMNS = ["start", "due", "last_update"]
STATUSES = ["Not started", "On track", "At risk", "Blocked", "Done"]


def load_initiatives(source) -> pd.DataFrame:
    """Read a CSV path or file-like object and return a validated frame."""
    return validate(pd.read_csv(source))


def validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    df = df[COLUMNS].copy()

    for col in DATE_COLUMNS:
        try:
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d").dt.normalize()
        except (ValueError, TypeError) as e:
            raise ValueError(f"Column '{col}' must contain YYYY-MM-DD dates: {e}") from e

    unknown = sorted(set(df["status"]) - set(STATUSES))
    if unknown:
        raise ValueError(f"Unknown status values: {unknown}. Allowed: {STATUSES}")

    df["percent_complete"] = pd.to_numeric(df["percent_complete"], errors="coerce")
    if df["percent_complete"].isna().any() or not df["percent_complete"].between(0, 100).all():
        raise ValueError("percent_complete must be a number between 0 and 100")

    if (df["due"] < df["start"]).any():
        bad = df.loc[df["due"] < df["start"], "initiative"].tolist()
        raise ValueError(f"Due date before start date: {bad}")

    df["risk_note"] = df["risk_note"].fillna("").astype(str)
    return df
