import json
from datetime import date

import pytest
from pydantic import ValidationError

from meeting_assistant.extract import extract
from meeting_assistant.llm import ground, parse_json_object
from meeting_assistant.schema import ActionItem, FollowUp, LLMOutput

NOTES = """Meeting: Test
Date: 2026-10-05
Attendees: Tom Becker, Aisha Khan

Aisha: I'll share the designs by Friday.
Someone should look at the crash rate.
"""


# --- validated items ---------------------------------------------------------

def test_action_item_complete():
    a = ActionItem(task="Ship it", owner="Tom", due=date(2026, 10, 9), confidence=0.9)
    assert not a.needs_confirmation and a.missing == [] and not a.unsure


@pytest.mark.parametrize("owner,due,missing", [
    (None, None, ["owner", "due date"]),
    ("  ", date(2026, 10, 9), ["owner"]),          # blank owner is treated as missing
    ("Tom", None, ["due date"]),
])
def test_missing_owner_or_date_needs_confirmation(owner, due, missing):
    a = ActionItem(task="Ship it", owner=owner, due=due, confidence=0.9)
    assert a.missing == missing and a.needs_confirmation


def test_unsure_below_threshold():
    assert ActionItem(task="x", confidence=0.59).unsure
    assert not ActionItem(task="x", confidence=0.6).unsure


@pytest.mark.parametrize("kw", [
    {"task": "", "confidence": 0.5},
    {"task": "   ", "confidence": 0.5},
    {"task": "x", "confidence": 1.5},
    {"task": "x", "confidence": -0.1},
    {"task": "x", "confidence": 0.5, "due": "next week"},
])
def test_invalid_action_items_rejected(kw):
    with pytest.raises(ValidationError):
        ActionItem(**kw)


def test_follow_up_validation():
    assert FollowUp(title="Sync", confidence=0.5).needs_confirmation
    with pytest.raises(ValidationError):
        FollowUp(title="Sync", confidence=0.5, duration_minutes=0)


# --- raw LLM output ------------------------------------------------------------

GOOD = {
    "decisions": ["Launch Nov 3"],
    "action_items": [
        {"task": "Share designs", "owner": "Aisha", "due_text": "by Friday", "confidence": 0.9},
        {"task": "Look at crash rate", "owner": "Priya", "due_text": "Oct 20", "confidence": 0.8},
        {"task": "Ask legal", "owner": None, "due_text": None, "confidence": 0.7, "extra": "ignored"},
    ],
    "open_questions": [],
    "follow_ups": [{"title": "Sync", "when_text": "next Monday 10am"}],
}


def test_llm_output_schema_accepts_good_json():
    out = LLMOutput.model_validate(GOOD)
    assert len(out.action_items) == 3


@pytest.mark.parametrize("bad", [
    {"action_items": [{"task": "x", "owner": None}]},                      # confidence missing
    {"action_items": [{"task": "x", "confidence": "high"}]},               # wrong type
    {"action_items": [{"task": "", "confidence": 0.5}]},                   # empty task
    {"decisions": "Launch Nov 3"},                                         # not a list
])
def test_llm_output_schema_rejects_bad_json(bad):
    with pytest.raises(ValidationError):
        LLMOutput.model_validate(bad)


def test_parse_json_object_tolerates_fences():
    assert parse_json_object('Sure:\n```json\n{"decisions": []}\n```') == {"decisions": []}
    with pytest.raises(ValueError):
        parse_json_object("I could not find anything.")
    with pytest.raises(ValueError):
        parse_json_object('{"decisions": [}')


def test_grounding_keeps_only_owners_and_dates_in_notes():
    ex = ground(LLMOutput.model_validate(GOOD), NOTES)
    share, crash, legal = ex.action_items
    assert share.owner == "Aisha Khan" and share.due == date(2026, 10, 9) and share.issues == []
    assert crash.owner is None and crash.due is None and crash.confidence <= 0.4
    assert crash.issues == ["model owner 'Priya' not found in notes; removed",
                            "model date 'Oct 20' not found in notes; removed"]
    assert legal.needs_confirmation
    assert ex.follow_ups[0].needs_confirmation          # 'next Monday 10am' is not in the notes


# --- fallback --------------------------------------------------------------------

class Fake:
    name = "fake"

    def __init__(self, reply):
        self.reply = reply

    def __call__(self, prompt):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_extract_uses_model_when_output_valid():
    ex = extract(NOTES, Fake(json.dumps(GOOD)))
    assert ex.backend == "fake" and ex.note == "" and len(ex.action_items) == 3


@pytest.mark.parametrize("reply", ["not json", json.dumps({"action_items": [{"task": "x"}]}),
                                   TimeoutError("slow")])
def test_extract_falls_back_to_rules(reply):
    ex = extract(NOTES, Fake(reply))
    assert ex.backend == "rules" and "used rules" in ex.note
    assert [a.owner for a in ex.action_items] == ["Aisha Khan", None]
