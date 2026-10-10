"""Follow-up email and status update, built only from reviewed items (no model involved)."""
from datetime import date

from .schema import Extraction


def fmt_date(d: date | None) -> str:
    return f"{d:%a %b} {d.day}" if d else "no date"


def _action_line(a) -> str:
    return f"- {a.task} ({a.owner or 'owner?'}, due {fmt_date(a.due) if a.due else '?'})"


def follow_up_email(ex: Extraction) -> str:
    m = ex.meeting
    when = f" on {fmt_date(m.date)}" if m.date else ""
    confirmed = [a for a in ex.action_items if not a.needs_confirmation]
    unconfirmed = [a for a in ex.action_items if a.needs_confirmation]
    parts = [
        f"Subject: Follow-up: {m.title}" + (f" ({m.date:%Y-%m-%d})" if m.date else ""),
        "",
        "Hi all,",
        "",
        f"Thanks for joining {m.title}{when}. Summary below; reply if anything is wrong or missing.",
    ]

    def section(title, lines):
        if lines:
            parts.extend(["", title, *lines])

    section("Decisions", [f"- {d.text}" for d in ex.decisions])
    section("Action items", [_action_line(a) for a in sorted(confirmed, key=lambda a: a.due)])
    section("Needs an owner or date (please confirm)", [_action_line(a) for a in unconfirmed])
    section("Open questions", [f"- {q.text}" for q in ex.open_questions])
    section("Next meeting", [
        f"- {f.title}: {fmt_date(f.date)}" + (f" at {f.time:%H:%M}" if f.time else "")
        for f in ex.follow_ups])
    parts += ["", "Thanks"]
    return "\n".join(parts) + "\n"


def status_update(ex: Extraction) -> str:
    m = ex.meeting
    n_conf = sum(a.needs_confirmation for a in ex.action_items)
    head = (f"{m.title}" + (f" ({m.date:%Y-%m-%d})" if m.date else "") +
            f". Decisions: {len(ex.decisions)}. Action items: {len(ex.action_items)} "
            f"(missing owner or date: {n_conf}). Open questions: {len(ex.open_questions)}.")
    lines = [head]
    if ex.decisions:
        lines.append("Decided: " + "; ".join(d.text for d in ex.decisions) + ".")
    dated = sorted((a for a in ex.action_items if a.due), key=lambda a: a.due)[:3]
    if dated:
        lines.append("Due next: " + "; ".join(
            f"{a.task} ({a.owner or 'owner?'}, {fmt_date(a.due)})" for a in dated) + ".")
    nxt = [f for f in ex.follow_ups if f.date]
    if nxt:
        f = min(nxt, key=lambda f: f.date)
        lines.append(f"Next meeting: {fmt_date(f.date)}" + (f" {f.time:%H:%M}" if f.time else "") + ".")
    return "\n".join(lines) + "\n"
