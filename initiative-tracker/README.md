---
title: Initiative Tracker
emoji: 📋
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 8501
pinned: false
---

# initiative-tracker

Tracks strategic initiatives from a CSV, computes health per initiative, rolls up by workstream and owner, flags risks, and drafts a weekly status report for human review before export.

All numbers are computed in pandas (`initiative_tracker/metrics.py`) and covered by pytest. An optional Hugging Face model may reword the report's summary paragraph. It never produces numbers.

## Run

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # Windows: .venv\Scripts\pip
.venv/bin/streamlit run app.py
.venv/bin/pytest -q
```

Regenerate the sample data (seeded, 40 rows): `python scripts/generate_sample.py`.

## Input

CSV with columns:

| column | type |
|---|---|
| initiative, owner, workstream, risk_note | text (risk_note may be blank) |
| start, due, last_update | `YYYY-MM-DD` |
| status | `Not started`, `On track`, `At risk`, `Blocked`, `Done` |
| percent_complete | 0–100 |

Invalid files are rejected with a message: missing columns, unknown status, bad dates, out-of-range %, due before start.

## Metrics

All metrics are evaluated **as of** a date. The default is the latest `last_update` in the file, and you can change it in the sidebar. "Open" means status is not `Done`. Done items are never overdue, slipping or stale.

| metric | definition |
|---|---|
| expected_pct | `(as_of − start) / (due − start) × 100`, clipped to 0–100. Assumes linear progress. |
| schedule_gap | `percent_complete − expected_pct` (percentage points) |
| overdue | open and `due < as_of` (the due date itself is not overdue) |
| days_overdue | `as_of − due` in days for overdue items, else 0 |
| slipping | open, not overdue, and `schedule_gap < −15` |
| stale | open and `as_of − last_update > 14` days |
| status_mismatch | status is `On track` or `Not started` but the item is overdue or slipping |
| **health** | **Done** if done; else **Red** if overdue or Blocked; else **Amber** if slipping, stale or At risk; else **Green** |
| flags | readable list of the above, e.g. `Overdue 8d; Stale 21d` |

Rollups (by workstream or owner) give counts of initiatives, done, red, amber, green, overdue, slipping, stale and blocked, plus the mean `percent_complete`. Top risks are Red items first, then Amber, sorted by most days overdue and then furthest behind plan. Thresholds are constants in `metrics.py` (`STALE_DAYS`, `SLIP_TOLERANCE`).

## Weekly report

"Generate weekly report" builds Markdown from the filtered view:

1. Code writes a facts paragraph from the computed metrics.
2. If a model is configured, it is asked to reword that paragraph only. Its output is **rejected** if it adds any number, drops any number, or uses number words ("two", "half", "majority"…). Rejections, errors and timeouts fall back to the template text, and the UI says why.
3. Tables (health, top risks, workstreams, stale updates) are always rendered by code.
4. The draft is shown in an editable text box. Export is disabled until the reviewer ticks "approve", and any further edit withdraws approval.

Model selection (environment variables):

| variable | effect |
|---|---|
| `HF_TOKEN` | use the HF Inference API with `HF_MODEL` (default `Qwen/Qwen2.5-7B-Instruct`) |
| `LOCAL_MODEL` | if no token, run this model locally via `transformers` (`pip install transformers torch`), e.g. `Qwen/Qwen2.5-0.5B-Instruct` |
| neither | rule-based template |

## Deploy to Hugging Face Spaces

Create a Space with the **Docker** SDK and push this repo. The front matter above and the `Dockerfile` are all it needs. For LLM wording, add `HF_TOKEN` as a Space secret. Without it the app uses the template.

## Limitations

- **Linear plan.** Expected progress assumes steady progress from start to due. Front-loaded or back-loaded work will look slipping or healthy when it isn't.
- **Self-reported inputs.** Status and % complete come from owners. The tool flags inconsistencies but cannot verify progress.
- **Single snapshot.** There is no history, so no week-over-week trends and no "newly red" detection.
- **Calendar days.** Weekends and holidays are not excluded. Thresholds are fixed, not per workstream.
- **The guard checks numbers, not meaning.** An LLM could still attach a correct number to the wrong label (e.g. swap red and amber counts) or shift emphasis. This is why every report needs human review before export. The guard is strict and may reject harmless rewording, in which case you get the template.
- **Model availability.** Free HF inference endpoints change and rate-limit. Local models are slow on CPU-only Spaces. The template fallback keeps the report working.
- **No auth or persistence.** Uploaded CSVs and edited reports live only in the browser session.
