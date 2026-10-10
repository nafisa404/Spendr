from datetime import date, time

import pytest

from meeting_assistant.dates import find_date_phrase, find_vague_phrase, parse_date, parse_time

MON = date(2026, 10, 5)   # Monday
THU = date(2026, 10, 8)   # Thursday


@pytest.mark.parametrize("phrase,ref,expected", [
    ("Wednesday", MON, date(2026, 10, 7)),
    ("Friday", MON, date(2026, 10, 9)),
    ("Monday", MON, date(2026, 10, 12)),          # same weekday -> next week, not today
    ("this Friday", MON, date(2026, 10, 9)),
    ("next Monday", MON, date(2026, 10, 12)),
    ("next Thursday", MON, date(2026, 10, 15)),   # 'next' = the following calendar week
    ("next Thursday", THU, date(2026, 10, 15)),
    ("end of week", date(2026, 10, 7), date(2026, 10, 9)),
    ("EOW", date(2026, 10, 10), date(2026, 10, 16)),   # Saturday -> following Friday
    ("end of the month", MON, date(2026, 10, 31)),
    ("EOD", MON, MON),
    ("tomorrow", MON, date(2026, 10, 6)),
    ("10/30", MON, date(2026, 10, 30)),
    ("1/15", MON, date(2027, 1, 15)),             # past month/day rolls to next year
    ("12/1/26", MON, date(2026, 12, 1)),
    ("2026-11-03", MON, date(2026, 11, 3)),
    ("Oct 14", MON, date(2026, 10, 14)),
    ("October 16", MON, date(2026, 10, 16)),
    ("November 3rd", MON, date(2026, 11, 3)),
    ("3 November 2026", MON, date(2026, 11, 3)),
])
def test_parse_date(phrase, ref, expected):
    assert parse_date(phrase, ref) == expected


@pytest.mark.parametrize("phrase", [None, "", "ASAP", "soon", "next quarter", "at some point",
                                    "13/45", "Funday", "the code freeze"])
def test_vague_or_invalid_dates_are_none(phrase):
    assert parse_date(phrase, MON) is None


@pytest.mark.parametrize("text,phrase", [
    ("I'll share the designs by Wednesday.", "Wednesday"),
    ("add alerting - due Oct 14", "Oct 14"),
    ("schedule a load test before 10/30", "10/30"),
    ("update the runbook by end of week", "end of week"),
    ("pull the report by next Thursday.", "next Thursday"),
    ("confirm before code freeze", None),
    ("we moved v3.1 to 12% of users", None),
    ("they may 5x the budget", None),
])
def test_find_date_phrase(text, phrase):
    assert find_date_phrase(text) == phrase


def test_find_vague_phrase():
    assert find_vague_phrase("write the summary ASAP") == "ASAP"
    assert find_vague_phrase("revisit the contract soon.") == "soon"
    assert find_vague_phrase("by Friday") is None


@pytest.mark.parametrize("text,expected", [
    ("next Monday at 10am", time(10, 0)),
    ("Oct 21, 2pm", time(14, 0)),
    ("at 12:30 PM", time(12, 30)),
    ("12am", time(0, 0)),
    ("at 3 pm sharp", time(15, 0)),
    ("in 30 minutes", None),
    ("13pm", None),
])
def test_parse_time(text, expected):
    assert parse_time(text) == expected
