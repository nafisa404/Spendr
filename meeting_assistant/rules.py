"""Rule-based extraction: section headers, labels and phrasing cues. No model needed."""
import re
from datetime import date

from .dates import find_date_phrase, find_vague_phrase, parse_date, parse_time
from .notes import name_pattern, parse_notes, resolve_name
from .schema import ActionItem, Decision, Extraction, FollowUp, Question

SECTIONS = {
    "decisions": "decision", "decision": "decision", "decisions made": "decision",
    "action items": "action", "actions": "action", "next steps": "action", "todo": "action", "to do": "action",
    "open questions": "question", "questions": "question", "open issues": "question",
    "notes": None, "summary": None, "discussion": None, "agenda": None,
}
LABELS = {
    "decision": "decision", "decided": "decision",
    "action": "action", "action item": "action", "ai": "action", "todo": "action", "to do": "action",
    "open question": "question", "question": "question",
    "follow-up": "follow_up", "follow up": "follow_up",
}
_LABEL = re.compile(r"^(" + "|".join(sorted(LABELS, key=len, reverse=True)) + r")\s*:\s*", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:(?:[-*•]|\d{1,2}[.)])\s*)?(\[[ xX]?\]\s*)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")

DECISION_CUE = re.compile(
    r"\b(decided|decision|we agreed|agreed to|agreed that|we will keep|we'll keep|go with|going forward)\b", re.I)
FOLLOW_UP_CUE = re.compile(
    r"\b(reconvene|follow[- ]up (?:meeting|call|sync)|meet again|next (?:sync|meeting|retro|review|check-?in|retro review))\b",
    re.I)
SELF_CUE = re.compile(r"^(?:also,?\s+)?(?:I'll|I will|I can|I'm going to)\s+", re.I)
UNOWNED_CUE = re.compile(
    r"^(?:also,?\s+)?(?:someone|somebody)\s+(?:should|needs to|has to|must)\s+|^we\s+(?:should|need to|must)(?:\s+probably)?\s+",
    re.I)
REQUEST = re.compile(r"\b(?:can|could|would) you\b", re.I)
HEDGE = re.compile(r"\b(probably|maybe|might|perhaps|someone|somebody|at some point|soon|should)\b", re.I)
_DEMONSTRATIVE_END = re.compile(r"\b(this|that|it)[.!?]?$", re.I)
_FALLBACK_NAME = (r"(?!(?:We|I|It|This|That|They|Someone|Somebody|Nobody|Everyone|Team|Let|Also|Then|And|But|"
                  r"Add|Write|Update|Confirm|Check|Review)\b)[A-Z][a-z]+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


def _strip_phrase(text: str, phrase: str | None) -> str:
    if not phrase:
        return text
    pre = r"(?:[\s,;.]*[-–]?\s*(?:due|by|before|on|until|at|for)?:?\s*)"
    return re.sub(pre + re.escape(phrase), "", text, count=1, flags=re.I)


def _tidy(text: str) -> str:
    text = re.sub(r"\(owner\s*(?:tbd|tbc|\?)\)", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,;:-–.!?")
    return text[:1].upper() + text[1:]


class _Ctx:
    def __init__(self, attendees, ref):
        self.attendees, self.ref = attendees, ref
        n = name_pattern(attendees) if attendees else _FALLBACK_NAME
        self.named = re.compile(rf"^(?:also,?\s+)?({n})\s+(?:will|to|is going to|should|can|needs to|must)\s+")
        self.addressed = re.compile(rf"^({n}),?\s+(?:can|could|would) you\s+")
        self.labelled = re.compile(rf"^({n})\s*[:\-–]\s+")
        self.speaker = re.compile(rf"^({n})\s*:\s+(.*)$")

    def owner(self, raw):
        return resolve_name(raw, self.attendees) or (None if self.attendees else raw)


def _action(s: str, ctx: _Ctx, speaker: str | None, explicit: bool, prev: str | None) -> ActionItem:
    owner, task = None, s
    if m := SELF_CUE.match(s):
        owner, task = speaker, s[m.end():]
    elif m := ctx.addressed.match(s) or ctx.labelled.match(s) or ctx.named.match(s):
        owner, task = ctx.owner(m.group(1)), s[m.end():]
    elif m := UNOWNED_CUE.match(s):
        task = s[m.end():]

    phrase, vague = find_date_phrase(task), find_vague_phrase(task)
    due = parse_date(phrase, ctx.ref)
    task = _tidy(_strip_phrase(_strip_phrase(task, phrase if due else None), vague))
    source = s
    if prev and owner is None and _DEMONSTRATIVE_END.search(s):
        task, source = f"{task} (re: {_tidy(prev)})", f"{prev} {s}"

    conf = 0.5 + 0.2 * explicit + 0.15 * (owner is not None) + 0.1 * (due is not None)
    conf -= 0.2 * bool(HEDGE.search(s))
    issues = []
    if vague:
        issues.append(f"vague timing '{vague}'")
    if phrase and not due:
        issues.append(f"could not parse date '{phrase}'")
    return ActionItem(task=task, owner=owner, due=due, due_text=(phrase if due else vague),
                      confidence=round(min(max(conf, 0.1), 0.95), 2), source=source, issues=issues)


def _follow_up(s: str, ref: date) -> FollowUp:
    phrase = find_date_phrase(s)
    d = parse_date(phrase, ref)
    t = parse_time(s)
    title = _strip_phrase(s, phrase)
    if t:
        title = re.sub(r"[\s,]*(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", "", title, flags=re.I)
    title = _tidy(re.sub(r"^let's\s+", "", title, flags=re.I))
    return FollowUp(title=title or "Follow-up", date=d, time=t, confidence=0.8 if d else 0.5, source=s,
                    issues=[] if d else ["no date found"])


def extract_rules(text: str, today: date | None = None) -> Extraction:
    meeting, body = parse_notes(text, today)
    ref = meeting.date or today or date.today()
    ctx = _Ctx(meeting.attendees, ref)
    out = Extraction(meeting=meeting, backend="rules")
    section = None

    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if line.rstrip(":").strip().lower() in SECTIONS:
            section = SECTIONS[line.rstrip(":").strip().lower()]
            continue
        checkbox = bool(_BULLET.match(line).group(1))
        line = _BULLET.sub("", line, count=1)

        speaker = None
        if m := ctx.speaker.match(line):
            if section == "action" or checkbox:
                line = f"{m.group(1)} - {m.group(2)}"           # 'Luis: add alerting' = owner label
            else:
                speaker, line = ctx.owner(m.group(1)), m.group(2)

        prev = None
        # a line in an action list is one item, even with several sentences ("... Due: Oct 30")
        for s in ([line] if section == "action" or checkbox else _sentences(line)):
            kind, explicit = None, False
            if m := _LABEL.match(s):
                kind, explicit, s = LABELS[m.group(1).lower()], True, s[m.end():]
            elif checkbox:
                kind, explicit = "action", True

            if kind is None:
                if FOLLOW_UP_CUE.search(s):
                    kind = "follow_up"
                elif s.endswith("?"):
                    kind = "action" if REQUEST.search(s) else "question"
                elif DECISION_CUE.search(s):
                    kind = "decision"
                elif SELF_CUE.match(s) or ctx.named.match(s) or UNOWNED_CUE.match(s):
                    kind = "action"
                elif section:
                    kind, explicit = section, True

            if kind == "decision":
                out.decisions.append(Decision(text=_tidy(s), confidence=0.8 if explicit else 0.65, source=s))
            elif kind == "question":
                out.open_questions.append(Question(text=s.strip(), confidence=0.8 if explicit else 0.65, source=s))
            elif kind == "action":
                out.action_items.append(_action(s, ctx, speaker, explicit, prev))
            elif kind == "follow_up":
                out.follow_ups.append(_follow_up(s, ref))
            prev = s
    return out
