"""Find and parse date/time phrases relative to the meeting date.

Anything vague ("ASAP", "soon", "next quarter") parses to None: dates are never guessed.
"""
import calendar
import re
from datetime import date, datetime, time, timedelta

import dateparser

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")

DATE_PATTERNS = [
    rf"\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}(?:\s+\d{{4}})?\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    r"\b(?:end of (?:the )?(?:day|week|month)|eod|eow|eom)\b",
    r"\b(?:next |this )?(?:mon|tues|wednes|thurs|fri|satur|sun)day\b",
    r"\b(?:today|tomorrow)\b",
]
_DATE_RE = re.compile("|".join(f"(?:{p})" for p in DATE_PATTERNS), re.IGNORECASE)
_VAGUE_RE = re.compile(
    r"\b(asap|as soon as possible|soon|at some point|sometime|later|eventually|when possible|"
    r"next (?:week|month|quarter)|this (?:week|month|quarter)|in q[1-4])\b", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)


def find_date_phrase(text: str) -> str | None:
    """First explicit date phrase in text, or None."""
    m = _DATE_RE.search(text)
    return m.group(0) if m else None


def find_vague_phrase(text: str) -> str | None:
    m = _VAGUE_RE.search(text)
    return m.group(0) if m else None


def parse_date(phrase: str | None, ref: date) -> date | None:
    """Resolve a date phrase against the meeting date. None if missing or not explicit."""
    if not phrase:
        return None
    p = re.sub(r"\s+", " ", phrase.strip().lower().rstrip("."))
    if _VAGUE_RE.fullmatch(p):
        return None
    if p in ("today", "eod", "end of day", "end of the day"):
        return ref
    if p == "tomorrow":
        return ref + timedelta(days=1)
    if p in ("eow", "end of week", "end of the week"):
        return ref + timedelta(days=(4 - ref.weekday()) % 7)          # Friday of this week
    if p in ("eom", "end of month", "end of the month"):
        return ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])

    if m := re.fullmatch(r"(next |this )?(\w+day)", p):
        if m.group(2) not in WEEKDAYS:
            return None
        target = WEEKDAYS.index(m.group(2))
        if m.group(1) == "next ":                                       # that weekday in the following week
            return ref - timedelta(days=ref.weekday()) + timedelta(days=7 + target)
        return ref + timedelta(days=(target - ref.weekday()) % 7 or 7)  # next occurrence after today

    if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", p):  # US month/day
        month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)
        try:
            if year:
                return date(int(year) + (2000 if len(year) == 2 else 0), month, day)
            d = date(ref.year, month, day)
            return d if d >= ref else date(ref.year + 1, month, day)
        except ValueError:
            return None

    parsed = dateparser.parse(
        p, languages=["en"],
        settings={"RELATIVE_BASE": datetime.combine(ref, time()), "PREFER_DATES_FROM": "future",
                  "DATE_ORDER": "MDY", "REQUIRE_PARTS": ["day", "month"]},
    )
    return parsed.date() if parsed else None


def parse_time(text: str) -> time | None:
    """First explicit clock time like '10am' or '2:30 pm'."""
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if not (1 <= hour <= 12 and minute < 60):
        return None
    return time(hour % 12 + (12 if ampm == "pm" else 0), minute)
