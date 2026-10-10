"""LLM extraction via a free Hugging Face model, validated and grounded against the notes.

The model returns JSON matching LLMOutput. It never supplies dates: it quotes the date words
(due_text) and code parses them. Owners and date words not found in the notes are dropped.
"""
import json
import os
import re
from datetime import date

from .dates import find_date_phrase, parse_date, parse_time
from .notes import parse_notes, resolve_name
from .schema import ActionItem, Decision, Extraction, FollowUp, LLMOutput, Question

DEFAULT_HF_MODEL = "Qwen/Qwen2.5-7B-Instruct"

PROMPT = """Extract structured items from the meeting notes below.
Return ONLY one JSON object that matches this JSON schema, with no commentary:
{schema}

Rules:
- decisions: things the group decided or agreed, one short sentence each.
- action_items: concrete tasks someone must do.
  - owner: the person's name exactly as written, ONLY if the notes name who will do it. "Someone should", "we should", "TBD" -> null. Never guess.
  - due_text: the exact date words copied from the notes (e.g. "by Friday", "Oct 14"). null if there is no date or only vague words such as "soon" or "ASAP". Do not convert or compute dates.
  - confidence: 0 to 1, how sure you are this is a real task with that owner and date.
- open_questions: questions left unresolved.
- follow_ups: future meetings; when_text = the exact date and time words from the notes.

Meeting notes:
\"\"\"
{notes}
\"\"\""""


def parse_json_object(raw: str) -> dict:
    """Take the outermost {...} from model output (tolerates code fences and chatter)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(raw[start:end + 1])


def _in_notes(phrase: str | None, notes: str) -> bool:
    return bool(phrase) and re.sub(r"\s+", " ", phrase.lower()) in re.sub(r"\s+", " ", notes.lower())


def ground(out: LLMOutput, text: str, today: date | None = None) -> Extraction:
    """Turn validated model output into items, keeping only owners and dates found in the notes."""
    meeting, _ = parse_notes(text, today)
    ref = meeting.date or today or date.today()
    ex = Extraction(meeting=meeting)
    ex.decisions = [Decision(text=d, confidence=0.7) for d in out.decisions if d.strip()]
    ex.open_questions = [Question(text=q, confidence=0.7) for q in out.open_questions if q.strip()]

    for a in out.action_items:
        issues, conf = [], a.confidence
        owner = resolve_name(a.owner, meeting.attendees)
        if a.owner and owner is None:
            if not meeting.attendees and _in_notes(a.owner, text):
                owner = a.owner
            else:
                issues.append(f"model owner '{a.owner}' not found in notes; removed")
                conf = min(conf, 0.4)
        due, due_text = None, None
        if a.due_text:
            if _in_notes(a.due_text, text):
                due_text = a.due_text
                due = parse_date(find_date_phrase(a.due_text) or a.due_text, ref)
                if due is None:
                    issues.append(f"could not parse date '{a.due_text}'")
            else:
                issues.append(f"model date '{a.due_text}' not found in notes; removed")
                conf = min(conf, 0.4)
        ex.action_items.append(ActionItem(task=a.task, owner=owner, due=due, due_text=due_text,
                                          confidence=conf, issues=issues))

    for f in out.follow_ups:
        when = f.when_text if _in_notes(f.when_text, text) else None
        d = parse_date(find_date_phrase(when), ref) if when else None
        ex.follow_ups.append(FollowUp(title=f.title, date=d, time=parse_time(when) if when else None,
                                      confidence=0.75 if d else 0.4, issues=[] if d else ["no date found"]))
    return ex


def extract_llm(text: str, generate, today: date | None = None) -> Extraction:
    """generate(prompt) -> str. Raises ValueError / pydantic.ValidationError on bad output."""
    prompt = PROMPT.format(schema=json.dumps(LLMOutput.model_json_schema()), notes=text)
    out = LLMOutput.model_validate(parse_json_object(generate(prompt)))
    ex = ground(out, text, today)
    ex.backend = getattr(generate, "name", "llm")
    return ex


# --- generators ------------------------------------------------------------------

class HFApiGenerator:
    def __init__(self, model: str, token: str):
        from huggingface_hub import InferenceClient
        self.client = InferenceClient(model=model, token=token, timeout=90)
        self.name = f"HF Inference API ({model})"

    def __call__(self, prompt: str) -> str:
        r = self.client.chat_completion(messages=[{"role": "user", "content": prompt}],
                                        max_tokens=1500, temperature=0.1, seed=0)
        return r.choices[0].message.content


class LocalGenerator:
    def __init__(self, model: str):
        from transformers import pipeline
        self.pipe = pipeline("text-generation", model=model)
        self.name = f"local transformers ({model})"

    def __call__(self, prompt: str) -> str:
        out = self.pipe([{"role": "user", "content": prompt}], max_new_tokens=1500, do_sample=False)
        return out[0]["generated_text"][-1]["content"]


def get_generator(env=None):
    """HF_TOKEN -> Inference API; LOCAL_MODEL -> transformers; otherwise (None, reason)."""
    env = os.environ if env is None else env
    try:
        if env.get("HF_TOKEN"):
            return HFApiGenerator(env.get("HF_MODEL", DEFAULT_HF_MODEL), env["HF_TOKEN"]), ""
        if env.get("LOCAL_MODEL"):
            return LocalGenerator(env["LOCAL_MODEL"]), ""
    except Exception as e:
        return None, f"Model unavailable ({type(e).__name__}: {e}); used rules."
    return None, "No model configured (set HF_TOKEN or LOCAL_MODEL); used rules."
