from datetime import date, time

from meeting_assistant.drafts import follow_up_email, status_update
from meeting_assistant.schema import ActionItem, Decision, Extraction, FollowUp, Meeting, Question

EX = Extraction(
    meeting=Meeting(title="Launch sync", date=date(2026, 10, 5)),
    decisions=[Decision(text="Launch Nov 3", confidence=0.8)],
    action_items=[
        ActionItem(task="Update calendar", owner="Marco Silva", due=date(2026, 10, 9), confidence=0.8),
        ActionItem(task="Share designs", owner="Aisha Khan", due=date(2026, 10, 7), confidence=0.8),
        ActionItem(task="Look at crash rate", confidence=0.3),
    ],
    open_questions=[Question(text="Who owns the banner?", confidence=0.7)],
    follow_ups=[FollowUp(title="Reconvene", date=date(2026, 10, 12), time=time(10), confidence=0.8)],
)


def test_email_sections():
    e = follow_up_email(EX)
    assert e.startswith("Subject: Follow-up: Launch sync (2026-10-05)\n")
    assert ("Action items\n- Share designs (Aisha Khan, due Wed Oct 7)\n"
            "- Update calendar (Marco Silva, due Fri Oct 9)\n") in e
    assert "Needs an owner or date (please confirm)\n- Look at crash rate (owner?, due ?)\n" in e
    assert "- Reconvene: Mon Oct 12 at 10:00" in e


def test_email_omits_empty_sections():
    e = follow_up_email(Extraction(meeting=Meeting(title="Empty")))
    assert "Decisions" not in e and "Action items" not in e and "on " not in e.splitlines()[4]


def test_status_update():
    assert status_update(EX) == (
        "Launch sync (2026-10-05). Decisions: 1. Action items: 3 (missing owner or date: 1). Open questions: 1.\n"
        "Decided: Launch Nov 3.\n"
        "Due next: Share designs (Aisha Khan, Wed Oct 7); Update calendar (Marco Silva, Fri Oct 9).\n"
        "Next meeting: Mon Oct 12 10:00.\n"
    )
