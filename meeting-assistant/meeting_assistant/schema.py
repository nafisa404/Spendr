"""Validated item types. Anything without an owner or date needs confirmation; nothing is filled in."""
from datetime import date as Date, time as Time

from pydantic import BaseModel, ConfigDict, Field, field_validator

UNSURE_BELOW = 0.6


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


class _Item(_Base):
    confidence: float = Field(ge=0, le=1)
    source: str = ""
    issues: list[str] = []

    @property
    def unsure(self) -> bool:
        return self.confidence < UNSURE_BELOW


class Decision(_Item):
    text: str = Field(min_length=1)


class Question(_Item):
    text: str = Field(min_length=1)


class ActionItem(_Item):
    task: str = Field(min_length=1)
    owner: str | None = None
    due: Date | None = None
    due_text: str | None = None      # the words used in the notes, kept for review

    @field_validator("owner", "due_text", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return None if v is None or (isinstance(v, str) and not v.strip()) else v

    @property
    def missing(self) -> list[str]:
        return [name for name, v in (("owner", self.owner), ("due date", self.due)) if v is None]

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.missing)


class FollowUp(_Item):
    title: str = Field(min_length=1)
    date: Date | None = None
    time: Time | None = None
    duration_minutes: int = Field(default=30, gt=0, le=480)

    @property
    def needs_confirmation(self) -> bool:
        return self.date is None


class Meeting(_Base):
    title: str = "Meeting"
    date: Date | None = None
    attendees: list[str] = []


class Extraction(_Base):
    meeting: Meeting
    decisions: list[Decision] = []
    action_items: list[ActionItem] = []
    open_questions: list[Question] = []
    follow_ups: list[FollowUp] = []
    backend: str = "rules"
    note: str = ""


# --- raw LLM output: validated, then grounded against the notes before use ---------

class LLMAction(_Base):
    task: str = Field(min_length=1)
    owner: str | None = None
    due_text: str | None = None
    confidence: float = Field(ge=0, le=1)


class LLMFollowUp(_Base):
    title: str = Field(min_length=1)
    when_text: str | None = None


class LLMOutput(_Base):
    decisions: list[str] = []
    action_items: list[LLMAction] = []
    open_questions: list[str] = []
    follow_ups: list[LLMFollowUp] = []
