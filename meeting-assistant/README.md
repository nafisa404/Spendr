---
title: Meeting Assistant
emoji: 📝
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 8501
pinned: false
---

# meeting-assistant

Turns meeting notes or a transcript into decisions, action items (task, owner, due date, confidence), open questions and follow-up meetings. A person reviews and edits every item. After approval it exports a follow-up email, a status update and `.ics` calendar files.

## What it does

1. **Extract.** With a Hugging Face model configured, the model returns JSON. The JSON is validated against a pydantic schema (`meeting_assistant/schema.py`). Without a model, or if the model's output is invalid, a rule-based extractor runs instead (`rules.py`). It uses section headers, labels such as `ACTION:` and `Decision:`, and phrasing cues ("I'll", "Grace will", "Tom, can you", "someone should").
2. **Never guess.** Owners are kept only if they match an attendee or appear in the notes. Dates are parsed by code (`dates.py`, using `dateparser`) from the date words in the notes. The model never supplies a date. If the model names an owner or a date phrase that isn't in the notes, it's removed and recorded as an issue on the item. Anything without an owner or date is flagged **needs confirmation**. Vague timing ("ASAP", "soon", "at some point") is kept as text but never becomes a date.
3. **Review.** In the Streamlit UI every item is an editable table row. Rows are flagged ⚠ when they need confirmation or have confidence below 0.6. Edited rows are re-validated against the schema.
4. **Export.** Once the reviewer approves, the export is a zip containing `follow_up_email.txt`, `status_update.txt`, `action_items.ics` (all-day events on due dates), `follow_ups.ics` (timed meetings) and `items.json`. Export buttons stay disabled until there are no validation errors and the approval box is ticked. Any edit or re-extraction withdraws approval.

The email and status update are templates filled from the reviewed items. No model writes them.

## Run

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # Windows: .venv\Scripts\pip
.venv/bin/streamlit run app.py
.venv/bin/pytest -q
.venv/bin/python scripts/evaluate.py               # --set holdout | all, --backend model
```

Model selection:

| variable | effect |
|---|---|
| `HF_TOKEN` | HF Inference API with `HF_MODEL` (default `Qwen/Qwen2.5-7B-Instruct`) |
| `LOCAL_MODEL` | if no token, run this model locally via `transformers` (`pip install transformers torch`) |
| neither | rule-based extractor |

Notes work best with a header like this, because the date anchors relative dates ("by Friday") and the attendee list is how owners are recognised:

```
Meeting: Launch sync
Date: 2026-10-05
Attendees: Priya Raman, Tom Becker
```

Without a `Date:` line the sidebar date is used. Without attendees, the rules accept any capitalised name before "will" or "to".

## Evaluation

`scripts/evaluate.py` compares extracted items with hand-labelled ones (`samples/*.expected.json`). Items are paired one-to-one by content-word overlap (Dice ≥ 0.4), and follow-ups also pair when their dates match. Owner and due accuracy are measured on matched action items. **Guessed** means a value was filled in where the label has none, which must never happen. **Missed** means the notes had the value but the item was flagged for confirmation instead.

Labelling rule: a date that is only implied (for example "before code freeze") is labelled `null`, because the tool is supposed to ask rather than infer.

Only the rule-based extractor has been evaluated. No HF token was available when these numbers were produced. Run `--backend model` with `HF_TOKEN` set to score the model.

### Main samples (3 meetings), rules

```
category          TP  FP  FN  precision  recall
decisions          6   0   0       100%    100%
action_items      18   0   0       100%    100%
open_questions     4   0   0       100%    100%
follow_ups         3   0   0       100%    100%
all items         31   0   0       100%    100%
owner correct 18/18, due correct 18/18, guessed: 0
```

These numbers are inflated. The rules were written while looking at these three samples, so they measure fit rather than generalisation.

### Held-out samples (2 meetings, `samples/holdout/`), rules

The held-out meetings use different styles: a numbered "Next steps" list, "Action item for X:", "Outcome:", and questions embedded in parentheses. They were labelled and committed before the extractor was run on them.

First run (commit `356d951`):

```
category          TP  FP  FN  precision  recall
decisions          1   0   1       100%     50%
action_items       5   7   4        42%     56%
open_questions     1   1   2        50%     33%
follow_ups         1   0   1       100%     50%
all items          8   8   8        50%     50%
owner correct 4/5 (missed 1), due correct 4/5 (missed 1), guessed: 0
```

After fixing two parser bugs found by that run (numbered lists weren't treated as bullets, and `Due: Oct 30` was split off as its own item), commit `bb4b52a`:

```
category          TP  FP  FN  precision  recall
decisions          1   0   1       100%     50%
action_items       5   2   4        71%     56%
open_questions     1   1   2        50%     33%
follow_ups         1   0   1       100%     50%
all items          8   3   8        73%     50%
owner correct 4/5 (missed 1), due correct 5/5, guessed: 0
```

The held-out set has now been seen, so treat the second table as optimistic as well. No phrasing-specific rules were added for it.

Remaining held-out failures:

| meeting | failure | cause |
|---|---|---|
| hiring | missed "Send the panel schedule to payments" (Sam) | `Action item for Sam:` is not a recognised label |
| hiring | missed "Coordinate with the payments team" | "so we should coordinate…" is mid-sentence; unowned cues only match at sentence start |
| hiring | missed "Ask finance…", spurious "Get back to you by the 20th" | took the wrong sentence of "I need to ask finance. I'll get back to you…"; "the 20th" is not a supported date form |
| hiring | "Can somebody refresh it…?" became a question, not an action | only "can/could you" requests become actions |
| hiring | missed follow-up "We'll sync again Thursday 4:30pm" | "sync again" is not a follow-up cue |
| vendor | missed decision "Outcome: renew for one year…" | "Outcome:" is not a decision label |
| vendor | "Still unclear whether the SSO add-on…" became an action, not a question | the "Next steps" section carries over to later lines |
| vendor | missed question inside "(need confirmation the CSV export covers…)" | parenthetical questions not detected |
| vendor | "Aisha owns the data export test" has no owner | "owns" is not an owner verb (safe failure: flagged for confirmation) |

Across all five meetings no owner or date was ever guessed. However, recall is about 50% on unseen styles, and a **missed** item never appears in the review table. The reviewer still has to read the notes.

## Tests

`pytest -q` runs 92 tests:

- date parsing: weekdays, "next X", end of week/month, numeric and month-name dates, vague phrases, times
- schema validation: blank owners, confidence bounds, malformed model JSON, and grounding that drops owners and dates not found in the notes
- rules
- `.ics` output: parsed back with the `icalendar` library; also checks CRLF, 75-octet folding (including multi-byte characters), escaping and stable UIDs
- drafts
- an app smoke test: approval gates export, and re-extraction withdraws approval

## Deploy to Hugging Face Spaces

Create a Space with the **Docker** SDK and push this repo. The front matter above and the `Dockerfile` are all it needs. Add `HF_TOKEN` as a Space secret to use the model. Without it the app uses rules.

## Limitations

- **Rules are brittle.** See the held-out results. They work on structured notes with an attendee list and degrade on free-form prose.
- **Model not evaluated.** The model path is covered by schema and grounding tests using fake outputs, but its extraction quality is unmeasured here. Free HF endpoints change and rate-limit, and any failure falls back to rules (the UI says so).
- **Grounding is string matching.** An owner who is named in the notes but assigned to the wrong task would pass. Review catches this; the code doesn't.
- **Date conventions are fixed.** A bare weekday means the next occurrence after the meeting date (said on a Monday, "Monday" means a week later). "Next Thursday" means the Thursday of the following calendar week. Numeric dates are month/day (US). "Before X" is treated as due on X.
- **Floating times.** Calendar times have no timezone, so they import at the same clock time wherever opened.
- **Small eval.** 5 meetings and 47 labelled items, labelled by one person. The numbers show direction, not reliability.
- **No persistence or auth.** Notes and edits live in the browser session only.
