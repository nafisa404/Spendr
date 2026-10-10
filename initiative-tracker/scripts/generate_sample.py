"""Generate data/initiatives.csv: 40 sample initiatives, deterministic (seeded).

Dates are relative to ANCHOR so the sample has a realistic mix of on-time,
slipping, overdue, stale and done work when evaluated as of ANCHOR.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

ANCHOR = date(2026, 10, 9)
SEED = 42
OUT = Path(__file__).resolve().parent.parent / "data" / "initiatives.csv"

WORKSTREAMS = {
    "Customer Experience": ["Priya Raman", "Tom Becker"],
    "Data Platform": ["Aisha Khan", "Luis Ortega"],
    "Operations": ["Grace Liu", "Tom Becker"],
    "Growth": ["Marco Silva", "Priya Raman"],
    "Security & Compliance": ["Dana Wright", "Luis Ortega"],
    "People": ["Grace Liu", "Sam Okafor"],
}

INITIATIVES = {
    "Customer Experience": [
        "Self-service returns portal", "Unified support inbox", "NPS survey redesign",
        "Chatbot tier-1 deflection", "Onboarding email journey", "Help center rewrite",
        "Customer health scoring",
    ],
    "Data Platform": [
        "Warehouse migration to cloud", "Event tracking standard", "Data quality monitors",
        "Self-serve BI rollout", "Customer 360 model", "PII tagging in lake",
        "Retire legacy ETL jobs",
    ],
    "Operations": [
        "Vendor consolidation", "Procurement workflow automation", "Warehouse slotting optimisation",
        "Carrier rate renegotiation", "Inventory forecasting v2", "Returns processing SLA",
    ],
    "Growth": [
        "Pricing page experiment", "Referral program relaunch", "Partner marketplace listing",
        "SEO content hub", "Trial-to-paid nurture", "EMEA market entry", "Annual plan discount test",
    ],
    "Security & Compliance": [
        "SOC 2 Type II audit", "SSO for all internal apps", "Quarterly access review",
        "Vendor risk assessments", "Endpoint encryption rollout", "Incident response drill",
    ],
    "People": [
        "Manager training program", "Career ladder refresh", "HRIS replacement",
        "Engagement survey action plan", "Hiring funnel analytics", "Hybrid office policy",
        "Benefits renewal",
    ],
}

RISK_NOTES = {
    "Blocked": [
        "Waiting on legal sign-off", "Vendor contract not signed", "Dependency on platform team API",
        "Budget approval pending", "Key engineer on leave",
    ],
    "At risk": [
        "Scope grew after discovery", "Two open hires delaying work", "Data quality issues upstream",
        "Stakeholder alignment incomplete", "Integration testing behind plan",
    ],
}


def _row(rng, workstream, name):
    owner = rng.choice(WORKSTREAMS[workstream])
    start = ANCHOR - timedelta(days=rng.randint(20, 200))
    due = start + timedelta(days=rng.randint(45, 260))
    span = (due - start).days
    elapsed = min(max((ANCHOR - start).days / span, 0), 1)
    expected = round(elapsed * 100)

    roll = rng.random()
    if due < ANCHOR and roll < 0.55:
        status, pct = "Done", 100
    elif roll < 0.12:
        status, pct = "Blocked", max(0, expected - rng.randint(15, 45))
    elif roll < 0.30:
        status, pct = "At risk", max(0, expected - rng.randint(10, 35))
    elif roll < 0.60 and (ANCHOR - start).days < 45:
        status, pct = "Not started", 0
    else:
        status, pct = "On track", min(99, max(5, expected + rng.randint(-25, 10)))
    pct = int(round(pct / 5) * 5)

    if status == "Done":
        last_update = min(due + timedelta(days=rng.randint(-10, 5)), ANCHOR)
    else:
        last_update = ANCHOR - timedelta(days=rng.choice([1, 2, 3, 5, 7, 9, 12, 16, 21, 30, 45]))
    last_update = max(last_update, start)

    risk_note = rng.choice(RISK_NOTES[status]) if status in RISK_NOTES else ""
    return {
        "initiative": name,
        "owner": owner,
        "workstream": workstream,
        "start": start.isoformat(),
        "due": due.isoformat(),
        "status": status,
        "percent_complete": pct,
        "risk_note": risk_note,
        "last_update": last_update.isoformat(),
    }


def main():
    rng = random.Random(SEED)
    rows = [_row(rng, ws, name) for ws, names in INITIATIVES.items() for name in names]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
