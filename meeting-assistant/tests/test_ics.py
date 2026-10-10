from datetime import date, datetime, time, timezone

import pytest
from icalendar import Calendar

from meeting_assistant.ics import _fold, action_items_ics, follow_ups_ics
from meeting_assistant.schema import ActionItem, FollowUp, Meeting

MEETING = Meeting(title="Launch sync", date=date(2026, 10, 5), attendees=["Tom Becker"])
STAMP = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
ITEMS = [
    ActionItem(task="Move embargo, update calendar; notify PR", owner="Marco Silva",
               due=date(2026, 10, 9), confidence=0.8),
    ActionItem(task="Look at crash rate", owner=None, due=None, confidence=0.3),
    ActionItem(task="Confirm push readiness", owner=None, due=date(2026, 10, 20), confidence=0.6),
]
FOLLOW = [
    FollowUp(title="Reconvene", date=date(2026, 10, 12), time=time(10, 0), duration_minutes=45, confidence=0.8),
    FollowUp(title="Retro review", date=date(2026, 10, 21), confidence=0.8),
    FollowUp(title="Sometime", confidence=0.4),
]


def events(ics: str):
    return [c for c in Calendar.from_ical(ics).walk() if c.name == "VEVENT"]


def test_action_items_are_all_day_on_due_date():
    evs = events(action_items_ics(ITEMS, MEETING, STAMP))
    assert len(evs) == 2                                          # undated item skipped
    e = evs[0]
    assert e["DTSTART"].dt == date(2026, 10, 9) and e["DTEND"].dt == date(2026, 10, 10)
    assert str(e["SUMMARY"]) == "Due: Move embargo, update calendar; notify PR (Marco Silva)"
    assert str(evs[1]["SUMMARY"]) == "Due: Confirm push readiness (owner not confirmed)"
    assert "From: Launch sync (2026-10-05)" in str(e["DESCRIPTION"])


def test_follow_ups_timed_and_all_day():
    evs = events(follow_ups_ics(FOLLOW, MEETING, STAMP))
    assert len(evs) == 2
    assert evs[0]["DTSTART"].dt == datetime(2026, 10, 12, 10, 0)
    assert evs[0]["DTEND"].dt == datetime(2026, 10, 12, 10, 45)
    assert evs[1]["DTSTART"].dt == date(2026, 10, 21)


def test_structure_crlf_and_escaping():
    ics = action_items_ics(ITEMS, MEETING, STAMP)
    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "\n" not in ics.replace("\r\n", "")
    assert "SUMMARY:Due: Move embargo\\, update calendar\\; notify PR (Marco Silva)" in ics
    assert "DESCRIPTION:Owner: Marco Silva\\nFrom: Launch sync (2026-10-05)" in ics
    assert "DTSTAMP:20261005T120000Z" in ics


def test_uids_unique_and_stable():
    a = action_items_ics(ITEMS, MEETING, STAMP)
    b = action_items_ics(ITEMS, MEETING, datetime(2027, 1, 1, tzinfo=timezone.utc))
    uids = [str(e["UID"]) for e in events(a)]
    assert len(set(uids)) == 2 and uids == [str(e["UID"]) for e in events(b)]


@pytest.mark.parametrize("text", ["x" * 200, "é" * 100, "Review the 🚀 launch plan " * 10])
def test_long_lines_folded_to_75_octets(text):
    folded = _fold("SUMMARY:" + text)
    assert all(len(line.encode()) <= 75 for line in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == "SUMMARY:" + text


def test_long_summary_round_trips():
    task = "Write the customer-facing incident summary, including timeline, impact and remediation " * 2
    ics = action_items_ics([ActionItem(task=task.strip(), owner="Sam", due=date(2026, 10, 9), confidence=1)],
                           MEETING, STAMP)
    assert str(events(ics)[0]["SUMMARY"]) == f"Due: {task.strip()} (Sam)"


def test_empty_calendar_is_valid():
    cal = Calendar.from_ical(follow_ups_ics([], MEETING, STAMP))
    assert cal["VERSION"] == "2.0" and events(follow_ups_ics([], MEETING, STAMP)) == []
