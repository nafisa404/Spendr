"""Health metrics, rollups and risk flags. Pure pandas; every reported number comes from here."""
import numpy as np
import pandas as pd

STALE_DAYS = 14          # an open item with no update for more than this many days is stale
SLIP_TOLERANCE = 15      # percentage points behind linear plan before an item is slipping
HEALTH_ORDER = ["Red", "Amber", "Green", "Done"]


def default_as_of(df: pd.DataFrame) -> pd.Timestamp:
    """Most recent update in the data: a stable 'as of' date for a static CSV."""
    return df["last_update"].max().normalize()


def compute_health(df: pd.DataFrame, as_of) -> pd.DataFrame:
    """Add per-initiative metric columns, health and risk flags. Input must be validated."""
    as_of = pd.Timestamp(as_of).normalize()
    out = df.copy()
    is_open = out["status"].ne("Done")

    span = (out["due"] - out["start"]).dt.days.clip(lower=1)
    elapsed = (as_of - out["start"]).dt.days.clip(lower=0)
    expected = (elapsed / span * 100).clip(upper=100)
    gap = out["percent_complete"] - expected

    out["expected_pct"] = expected.round(1)
    out["schedule_gap"] = gap.round(1)
    out["days_since_update"] = (as_of - out["last_update"]).dt.days
    out["days_overdue"] = (as_of - out["due"]).dt.days.clip(lower=0).where(is_open, 0).astype(int)

    out["overdue"] = is_open & (out["due"] < as_of)
    out["slipping"] = is_open & ~out["overdue"] & (gap < -SLIP_TOLERANCE)
    out["stale"] = is_open & (out["days_since_update"] > STALE_DAYS)
    out["blocked"] = out["status"].eq("Blocked")
    out["at_risk"] = out["status"].eq("At risk")
    out["status_mismatch"] = out["status"].isin(["On track", "Not started"]) & (out["overdue"] | out["slipping"])

    out["health"] = np.select(
        [~is_open, out["overdue"] | out["blocked"], out["slipping"] | out["stale"] | out["at_risk"]],
        ["Done", "Red", "Amber"],
        default="Green",
    )
    out["flags"] = out.apply(_flags, axis=1)
    return out


def _flags(r) -> str:
    flags = []
    if r["overdue"]:
        flags.append(f"Overdue {r['days_overdue']}d")
    if r["blocked"]:
        flags.append("Blocked")
    if r["at_risk"]:
        flags.append("At risk")
    if r["slipping"]:
        flags.append(f"Slipping {-r['schedule_gap']:g} pts behind plan")
    if r["stale"]:
        flags.append(f"Stale {r['days_since_update']}d")
    if r["status_mismatch"]:
        flags.append(f"Status '{r['status']}' contradicts schedule")
    return "; ".join(flags)


def rollup(h: pd.DataFrame, by: str) -> pd.DataFrame:
    """Counts and average completion per group (e.g. 'workstream' or 'owner')."""
    ind = h.assign(
        done=h["health"].eq("Done"),
        red=h["health"].eq("Red"),
        amber=h["health"].eq("Amber"),
        green=h["health"].eq("Green"),
    )
    out = ind.groupby(by).agg(
        initiatives=("initiative", "size"),
        done=("done", "sum"),
        red=("red", "sum"),
        amber=("amber", "sum"),
        green=("green", "sum"),
        overdue=("overdue", "sum"),
        slipping=("slipping", "sum"),
        stale=("stale", "sum"),
        blocked=("blocked", "sum"),
        avg_pct_complete=("percent_complete", "mean"),
    )
    out["avg_pct_complete"] = out["avg_pct_complete"].round(1)
    counts = [c for c in out.columns if c != "avg_pct_complete"]
    out[counts] = out[counts].astype(int)
    return out.sort_values(["red", "amber", "initiatives"], ascending=[False, False, False]).reset_index()


def portfolio_summary(h: pd.DataFrame) -> dict:
    is_open = h["status"].ne("Done")
    health = h["health"].value_counts()
    return {
        "total": int(len(h)),
        "open": int(is_open.sum()),
        "done": int((~is_open).sum()),
        **{k.lower(): int(health.get(k, 0)) for k in ["Red", "Amber", "Green"]},
        "overdue": int(h["overdue"].sum()),
        "slipping": int(h["slipping"].sum()),
        "stale": int(h["stale"].sum()),
        "blocked": int(h["blocked"].sum()),
        "at_risk": int(h["at_risk"].sum()),
        "status_mismatch": int(h["status_mismatch"].sum()),
        "avg_pct_open": round(float(h.loc[is_open, "percent_complete"].mean()), 1) if is_open.any() else 0.0,
    }


def top_risks(h: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Red then Amber items, worst first: most overdue, then furthest behind plan."""
    risky = h[h["health"].isin(["Red", "Amber"])].copy()
    risky["_rank"] = risky["health"].map({"Red": 0, "Amber": 1})
    risky = risky.sort_values(["_rank", "days_overdue", "schedule_gap"], ascending=[True, False, True])
    cols = ["initiative", "owner", "workstream", "health", "flags", "risk_note"]
    return risky[cols].head(n).reset_index(drop=True)
