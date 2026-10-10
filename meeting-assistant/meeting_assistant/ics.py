"""RFC 5545 calendar files for action-item due dates and follow-up meetings.

Times are floating (no timezone): they show at the same clock time in any calendar.
Items without a date are skipped; they stay in the email under "needs confirmation".
"""
import hashlib
from datetime import date, datetime, timedelta, timezone

from .schema import ActionItem, FollowUp, Meeting

PRODID = "-//meeting-assistant//EN"


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Split lines longer than 75 octets; continuation lines start with a space. Never splits a UTF-8 char."""
    out, cur, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > limit:
            out.append(cur.decode("utf-8"))
            cur, limit = b"", 74          # leading space takes one octet
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _uid(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:20] + "@meeting-assistant"


def _event(uid, summary, start, end, description, stamp) -> list[str]:
    if isinstance(start, datetime):
        when = [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
    else:
        when = [f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end:%Y%m%d}"]
    return ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp:%Y%m%dT%H%M%SZ}", *when,
            f"SUMMARY:{_escape(summary)}", f"DESCRIPTION:{_escape(description)}", "END:VEVENT"]


def _calendar(events: list[list[str]], name: str) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(name)}"]
    for e in events:
        lines += e
    lines.append("END:VCALENDAR")
    return "".join(_fold(l) + "\r\n" for l in lines)


def _stamp(stamp):
    return (stamp or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _origin(meeting: Meeting) -> str:
    return f"From: {meeting.title}" + (f" ({meeting.date:%Y-%m-%d})" if meeting.date else "")


def action_items_ics(items: list[ActionItem], meeting: Meeting, stamp: datetime | None = None) -> str:
    """All-day events on each due date."""
    events = []
    for a in items:
        if a.due is None:
            continue
        who = a.owner or "owner not confirmed"
        events.append(_event(
            _uid(meeting.title, meeting.date, a.task, a.due), f"Due: {a.task} ({who})",
            a.due, a.due + timedelta(days=1), f"Owner: {who}\n{_origin(meeting)}", _stamp(stamp)))
    return _calendar(events, f"{meeting.title}: action items")


def follow_ups_ics(follow_ups: list[FollowUp], meeting: Meeting, stamp: datetime | None = None) -> str:
    """Timed events when a time is known, all-day otherwise."""
    events = []
    for f in follow_ups:
        if f.date is None:
            continue
        if f.time:
            start = datetime.combine(f.date, f.time)
            end = start + timedelta(minutes=f.duration_minutes)
        else:
            start, end = f.date, f.date + timedelta(days=1)
        events.append(_event(_uid(meeting.title, meeting.date, f.title, start), f.title, start, end,
                             _origin(meeting), _stamp(stamp)))
    return _calendar(events, f"{meeting.title}: follow-ups")
