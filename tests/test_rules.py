from datetime import date, time

from meeting_assistant.rules import extract_rules

HEAD = "Meeting: T\nDate: 2026-10-05\nAttendees: Tom Becker, Aisha Khan (Design)\n\n"


def actions(body):
    return extract_rules(HEAD + body).action_items


def test_header_parsed():
    m = extract_rules(HEAD).meeting
    assert (m.title, m.date, m.attendees) == ("T", date(2026, 10, 5), ["Tom Becker", "Aisha Khan"])


def test_ill_assigns_speaker():
    [a] = actions("Aisha: I'll share the designs by Wednesday.")
    assert (a.task, a.owner, a.due) == ("Share the designs", "Aisha Khan", date(2026, 10, 7))


def test_named_and_addressed_owners():
    a, b = actions("Tom will update the doc by Oct 14.\nAisha: Tom, can you check the logs?")
    assert (a.owner, a.due) == ("Tom Becker", date(2026, 10, 14))
    assert (b.task, b.owner, b.due) == ("Check the logs", "Tom Becker", None)


def test_someone_should_is_unowned_and_never_guessed():
    [a] = actions("Tom: The build is slow. Someone should look at this.")
    assert a.owner is None and a.due is None and a.needs_confirmation and a.unsure
    assert "build is slow" in a.task                                  # context kept for 'this'


def test_vague_timing_is_not_a_date():
    [a] = actions("Aisha: I'll write the notes ASAP.")
    assert a.due is None and a.due_text == "ASAP" and a.issues == ["vague timing 'ASAP'"]


def test_non_attendee_name_is_not_an_owner():
    assert actions("Priya will send the deck by Friday.") == []


def test_sections_and_labels():
    ex = extract_rules(HEAD + "Decisions\n- Ship v2 first.\n\nAction items\n- [ ] Add a canary stage (owner TBD)\n"
                       "Open question: who pays?\nTODO: confirm licence count\n")
    assert [d.text for d in ex.decisions] == ["Ship v2 first"]
    assert [(a.task, a.owner) for a in ex.action_items] == [
        ("Add a canary stage", None), ("Confirm licence count", None)]
    assert [q.text for q in ex.open_questions] == ["who pays?"]


def test_follow_up_meeting():
    [f] = extract_rules(HEAD + "Tom: Let's reconvene next Monday at 10am to review.").follow_ups
    assert (f.title, f.date, f.time) == ("Reconvene to review", date(2026, 10, 12), time(10, 0))


def test_follow_up_without_date_needs_confirmation():
    [f] = extract_rules(HEAD + "We should meet again to review.").follow_ups
    assert f.date is None and f.needs_confirmation
