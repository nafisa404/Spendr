"""Parse the notes header (title, date, attendees) and resolve names to attendees."""
import re
from datetime import date

from .dates import parse_date
from .schema import Meeting

_HEADER = re.compile(r"^(meeting|title|date|attendees|participants|present)\s*:\s*(.*)$", re.IGNORECASE)


def parse_notes(text: str, today: date | None = None) -> tuple[Meeting, list[str]]:
    """Split notes into a Meeting header and the remaining body lines."""
    fields, body = {}, []
    for line in text.splitlines():
        m = _HEADER.match(line.strip())
        if m and m.group(1).lower() not in fields:
            fields[m.group(1).lower()] = m.group(2).strip()
        else:
            body.append(line)

    title = fields.get("meeting") or fields.get("title") or "Meeting"
    raw_date = fields.get("date", "")
    meeting_date = parse_date(raw_date, today or date.today()) if raw_date else None
    people = fields.get("attendees") or fields.get("participants") or fields.get("present") or ""
    attendees = [re.sub(r"\(.*?\)", "", p).strip() for p in people.split(",")]
    return Meeting(title=title, date=meeting_date, attendees=[a for a in attendees if a]), body


def resolve_name(name: str | None, attendees: list[str]) -> str | None:
    """Map 'Tom' or 'tom becker' to the attendee's full name; None if not an attendee."""
    if not name:
        return None
    n = name.strip().lower()
    for a in attendees:
        if n == a.lower() or n == a.split()[0].lower():
            return a
    return None


def name_pattern(attendees: list[str]) -> str:
    """Regex alternation of attendee full and first names, longest first."""
    names = {a for a in attendees} | {a.split()[0] for a in attendees}
    return "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) or r"(?!x)x"
