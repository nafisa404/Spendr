"""Streamlit UI: paste notes -> extract -> review/edit every item -> approve -> export."""
import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from meeting_assistant.drafts import follow_up_email, status_update
from meeting_assistant.extract import extract
from meeting_assistant.ics import action_items_ics, follow_ups_ics
from meeting_assistant.llm import get_generator
from meeting_assistant.schema import ActionItem, Decision, Extraction, FollowUp, Question

SAMPLES = {p.stem: p for p in sorted((Path(__file__).parent / "samples").glob("*.txt"))}
COLS = {
    "actions": ["review", "task", "owner", "due", "confidence", "as written", "issues", "source"],
    "decisions": ["review", "text", "confidence"],
    "questions": ["review", "text", "confidence"],
    "follow_ups": ["review", "title", "date", "time", "duration_minutes", "issues"],
}

st.set_page_config(page_title="Meeting Assistant", layout="wide")
state = st.session_state
state.setdefault("version", 0)
state.setdefault("approved", False)


@st.cache_resource
def generator():
    return get_generator()


def review_flag(item) -> str:
    parts = []
    if isinstance(item, ActionItem) and item.needs_confirmation:
        parts.append("needs " + " & ".join(item.missing))
    if isinstance(item, FollowUp) and item.needs_confirmation:
        parts.append("needs date")
    if item.unsure:
        parts.append(f"unsure ({item.confidence:.2f})")
    return "⚠ " + ", ".join(parts) if parts else "ok"


def to_frames(ex: Extraction) -> dict[str, pd.DataFrame]:
    frames = {
        "actions": pd.DataFrame([{
            "review": review_flag(a), "task": a.task, "owner": a.owner or "", "due": a.due,
            "confidence": a.confidence, "as written": a.due_text or "", "issues": "; ".join(a.issues),
            "source": a.source} for a in ex.action_items], columns=COLS["actions"]),
        "decisions": pd.DataFrame([{"review": review_flag(d), "text": d.text, "confidence": d.confidence}
                                   for d in ex.decisions], columns=COLS["decisions"]),
        "questions": pd.DataFrame([{"review": review_flag(q), "text": q.text, "confidence": q.confidence}
                                   for q in ex.open_questions], columns=COLS["questions"]),
        "follow_ups": pd.DataFrame([{
            "review": review_flag(f), "title": f.title, "date": f.date, "time": f.time,
            "duration_minutes": f.duration_minutes, "issues": "; ".join(f.issues)} for f in ex.follow_ups],
            columns=COLS["follow_ups"]),
    }
    for name, col in (("actions", "due"), ("follow_ups", "date")):
        frames[name][col] = pd.to_datetime(frames[name][col])
    return frames


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT or (isinstance(v, str) and not v.strip())


def _date(v):
    return None if _blank(v) else pd.Timestamp(v).date()


def _conf(v):
    return 1.0 if _blank(v) else float(v)      # rows added by the reviewer are certain


def from_frames(frames, base: Extraction) -> tuple[Extraction, list[str]]:
    """Validate the edited tables back into schema objects; collect row errors."""
    errors, out = [], base.model_copy(update={"decisions": [], "action_items": [], "open_questions": [],
                                              "follow_ups": []})

    def add(target, label, i, build):
        try:
            target.append(build())
        except ValidationError as e:
            errors.append(f"{label} row {i + 1}: {e.errors()[0]['loc'][0]}: {e.errors()[0]['msg']}")

    for i, r in frames["actions"].reset_index(drop=True).iterrows():
        if all(_blank(r[c]) for c in ("task", "owner", "due")):
            continue
        add(out.action_items, "Action item", i, lambda: ActionItem(
            task=r["task"] or "", owner=None if _blank(r["owner"]) else r["owner"], due=_date(r["due"]),
            due_text=None if _blank(r["as written"]) else r["as written"], confidence=_conf(r["confidence"]),
            source="" if _blank(r["source"]) else r["source"]))
    for key, target, label, cls in (("decisions", out.decisions, "Decision", Decision),
                                    ("questions", out.open_questions, "Question", Question)):
        for i, r in frames[key].reset_index(drop=True).iterrows():
            if not _blank(r["text"]):
                add(target, label, i, lambda: cls(text=r["text"], confidence=_conf(r["confidence"])))
    for i, r in frames["follow_ups"].reset_index(drop=True).iterrows():
        if all(_blank(r[c]) for c in ("title", "date")):
            continue
        add(out.follow_ups, "Follow-up", i, lambda: FollowUp(
            title=r["title"] or "", date=_date(r["date"]), time=None if _blank(r["time"]) else r["time"],
            duration_minutes=30 if _blank(r["duration_minutes"]) else int(r["duration_minutes"]),
            confidence=_conf(None)))
    return out, errors


def run_extract():
    model, note = generator()
    ex = extract(state.notes, model, today=state.meeting_date, note=note)
    if ex.meeting.date is None:
        ex.meeting.date = state.meeting_date
    state.extraction = ex
    state.version += 1
    state.approved = False


def unapprove():
    state.approved = False


def load_sample():
    if state.sample != "(paste your own)":
        state.notes = SAMPLES[state.sample].read_text(encoding="utf-8")


# --- input ---------------------------------------------------------------------------

st.title("Meeting Assistant")
st.caption("Extract decisions, action items, questions and follow-ups. Nothing is exported until you approve it.")

st.sidebar.selectbox("Sample", ["(paste your own)", *SAMPLES], key="sample", on_change=load_sample)
st.sidebar.date_input("Meeting date (if notes have no 'Date:' line)", value=date.today(), key="meeting_date")
model, model_note = generator()
st.sidebar.caption(f"Extractor: {model.name if model else 'rules (no model configured)'}")

st.text_area("Meeting notes or transcript", key="notes", height=260,
             placeholder="Meeting: ...\nDate: 2026-10-05\nAttendees: Name One, Name Two\n\nNotes...")
st.button("Extract", type="primary", on_click=run_extract, disabled=not state.get("notes", "").strip())

if "extraction" not in state:
    st.stop()

ex: Extraction = state.extraction
st.caption(f"Extracted with: {ex.backend}. Meeting: {ex.meeting.title}, "
           f"{ex.meeting.date or 'no date'}; attendees: {', '.join(ex.meeting.attendees) or 'none listed'}.")
if ex.note:
    st.info(ex.note)

# --- review ----------------------------------------------------------------------------

st.subheader("Review and edit")
st.caption("⚠ marks items missing an owner or date, or that the extractor was unsure about (confidence < 0.6). "
           "Owners and dates are never filled in for you. Add or delete rows as needed.")
frames = to_frames(ex)
v = state.version
ro = {"review": st.column_config.TextColumn("review", disabled=True),
      "confidence": st.column_config.NumberColumn("confidence", format="%.2f", disabled=True),
      "issues": st.column_config.TextColumn("issues", disabled=True)}

flagged = sum(f["review"].ne("ok").sum() for f in frames.values())
st.markdown(f"**{flagged} item(s) flagged for attention.**")

edited = {}
st.markdown("**Action items**")
edited["actions"] = st.data_editor(
    frames["actions"], key=f"actions_{v}", on_change=unapprove, num_rows="dynamic", hide_index=True, width="stretch",
    column_config={**ro, "due": st.column_config.DateColumn("due", format="YYYY-MM-DD"),
                   "as written": st.column_config.TextColumn("as written", disabled=True),
                   "source": st.column_config.TextColumn("source", disabled=True)})
a, b = st.columns(2)
with a:
    st.markdown("**Decisions**")
    edited["decisions"] = st.data_editor(frames["decisions"], key=f"decisions_{v}", on_change=unapprove,
                                         num_rows="dynamic", hide_index=True, width="stretch", column_config=ro)
with b:
    st.markdown("**Open questions**")
    edited["questions"] = st.data_editor(frames["questions"], key=f"questions_{v}", on_change=unapprove,
                                         num_rows="dynamic", hide_index=True, width="stretch", column_config=ro)
st.markdown("**Follow-up meetings**")
edited["follow_ups"] = st.data_editor(
    frames["follow_ups"], key=f"follow_ups_{v}", on_change=unapprove, num_rows="dynamic", hide_index=True,
    width="stretch", column_config={**ro, "date": st.column_config.DateColumn("date", format="YYYY-MM-DD"),
                                    "time": st.column_config.TimeColumn("time", format="HH:mm"),
                                    "duration_minutes": st.column_config.NumberColumn("minutes", min_value=5,
                                                                                      max_value=480)})

reviewed, errors = from_frames(edited, ex)
for e in errors:
    st.error(e)
pending = [a for a in reviewed.action_items if a.needs_confirmation]
if pending:
    st.warning(f"{len(pending)} action item(s) still lack an owner or date. They will be listed under "
               "'please confirm' in the email and left out of the calendar file.")

# --- preview & export ------------------------------------------------------------------

st.subheader("Preview")
email, status = follow_up_email(reviewed), status_update(reviewed)
ics_actions = action_items_ics(reviewed.action_items, reviewed.meeting)
ics_follow = follow_ups_ics(reviewed.follow_ups, reviewed.meeting)
t1, t2, t3 = st.tabs(["Follow-up email", "Status update", "Calendar"])
t1.code(email, language=None)
t2.code(status, language=None)
with t3:
    n_due = sum(a.due is not None for a in reviewed.action_items)
    n_fu = sum(f.date is not None for f in reviewed.follow_ups)
    st.write(f"{n_due} due-date event(s) and {n_fu} follow-up meeting(s). Times are floating (no timezone).")

st.subheader("Approve and export")
st.checkbox("I have reviewed every item above and approve export", key="approved", disabled=bool(errors))
ok = state.approved and not errors

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("follow_up_email.txt", email)
    z.writestr("status_update.txt", status)
    z.writestr("action_items.ics", ics_actions)
    z.writestr("follow_ups.ics", ics_follow)
    z.writestr("items.json", reviewed.model_dump_json(indent=2))
stem = f"{reviewed.meeting.date or 'meeting'}"
c1, c2, c3 = st.columns(3)
c1.download_button("Download all (.zip)", buf.getvalue(), f"meeting-{stem}.zip", "application/zip", disabled=not ok)
c2.download_button("Action items (.ics)", ics_actions, f"action-items-{stem}.ics", "text/calendar", disabled=not ok)
c3.download_button("Follow-ups (.ics)", ics_follow, f"follow-ups-{stem}.ics", "text/calendar", disabled=not ok)
if not ok:
    st.caption("Exports are disabled until the items are valid and approved.")
