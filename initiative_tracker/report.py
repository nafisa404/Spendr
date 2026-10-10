"""Weekly status report.

All numbers come from metrics.py. The optional LLM sees only the facts paragraph and may
rephrase it; its output is rejected (template used instead) if it adds, drops or spells out
any number. Tables are always rendered from the computed frames, never by the LLM.
"""
import os
import re
from dataclasses import dataclass

import pandas as pd

from .metrics import STALE_DAYS, portfolio_summary, rollup, top_risks

DEFAULT_HF_MODEL = "Qwen/Qwen2.5-7B-Instruct"

SYSTEM_PROMPT = (
    "Rewrite the status facts below as a short executive summary paragraph (3-4 sentences). "
    "Use every number exactly as given, written as digits. Do not add, round, combine or "
    "calculate numbers. Do not add facts or recommendations. Plain business tone. "
    "No headings, no bullet points."
)

_NUM = re.compile(r"\d+(?:\.\d+)?")
_NUMBER_WORDS = re.compile(
    r"\b(zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|"
    r"forty|fifty|hundred|dozen|half|third|quarter|majority|minority)\b",
    re.IGNORECASE,
)


@dataclass
class Report:
    markdown: str
    backend: str
    note: str = ""


# --- facts & guard -----------------------------------------------------------

def summary_facts(h: pd.DataFrame) -> str:
    """Plain sentences built from computed metrics: the only text an LLM ever sees."""
    s = portfolio_summary(h)
    parts = [
        f"{s['open']} of {s['total']} initiatives are open and {s['done']} are done.",
        f"Open work health: {s['red']} red, {s['amber']} amber, {s['green']} green.",
        f"{s['overdue']} are overdue, {s['slipping']} are slipping behind plan, {s['blocked']} are blocked "
        f"and {s['stale']} have had no update in over {STALE_DAYS} days.",
        f"Average completion of open initiatives is {s['avg_pct_open']:g}%.",
    ]
    if s["status_mismatch"]:
        parts.append(f"{s['status_mismatch']} report On track or Not started but are overdue or behind plan.")
    ws = rollup(h, "workstream")
    if s["red"]:
        worst = ws.iloc[0]
        parts.append(f"{worst['workstream']} has the most red items ({worst['red']}).")
    return " ".join(parts)


def _numbers(text: str) -> set[float]:
    return {float(n) for n in _NUM.findall(text)}


def number_problems(candidate: str, source: str) -> list[str]:
    """Reasons a rephrasing is unsafe; empty list means every number is preserved and none invented."""
    src, cand = _numbers(source), _numbers(candidate)
    problems = []
    if added := sorted(cand - src):
        problems.append(f"added numbers {[f'{n:g}' for n in added]}")
    if dropped := sorted(src - cand):
        problems.append(f"dropped numbers {[f'{n:g}' for n in dropped]}")
    if words := sorted({w.lower() for w in _NUMBER_WORDS.findall(candidate)}):
        problems.append(f"number words {words}")
    return problems


# --- rephrasers --------------------------------------------------------------

class HFApiRephraser:
    def __init__(self, model: str, token: str):
        from huggingface_hub import InferenceClient
        self.client = InferenceClient(model=model, token=token, timeout=60)
        self.name = f"HF Inference API ({model})"

    def __call__(self, facts: str) -> str:
        r = self.client.chat_completion(
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": facts}],
            max_tokens=300, temperature=0.1, seed=0,
        )
        return r.choices[0].message.content


class LocalRephraser:
    def __init__(self, model: str):
        from transformers import pipeline
        self.pipe = pipeline("text-generation", model=model)
        self.name = f"local transformers ({model})"

    def __call__(self, facts: str) -> str:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": facts}]
        out = self.pipe(msgs, max_new_tokens=250, do_sample=False)
        return out[0]["generated_text"][-1]["content"]


def get_rephraser(env=None):
    """HF_TOKEN -> Inference API; LOCAL_MODEL -> transformers; otherwise (None, reason)."""
    env = os.environ if env is None else env
    try:
        if env.get("HF_TOKEN"):
            return HFApiRephraser(env.get("HF_MODEL", DEFAULT_HF_MODEL), env["HF_TOKEN"]), ""
        if env.get("LOCAL_MODEL"):
            return LocalRephraser(env["LOCAL_MODEL"]), ""
    except Exception as e:  # missing package, bad model id, no network
        return None, f"Model unavailable ({type(e).__name__}: {e}); used template."
    return None, "No model configured (set HF_TOKEN or LOCAL_MODEL); used template."


# --- rendering ---------------------------------------------------------------

def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_None._"
    cells = lambda vals: "| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in vals) + " |"
    lines = [cells(df.columns), "|" + "---|" * len(df.columns)]
    lines += [cells(row) for row in df.itertuples(index=False)]
    return "\n".join(lines)


def build_report(h: pd.DataFrame, as_of, scope: str = "All initiatives", rephraser=None, n_risks: int = 8) -> Report:
    facts = summary_facts(h)
    summary, backend, note = facts, "template", ""
    if rephraser is not None:
        try:
            candidate = rephraser(facts).strip()
            problems = number_problems(candidate, facts)
            if problems:
                note = f"LLM output rejected ({'; '.join(problems)}); used template."
            elif candidate:
                summary, backend = candidate, rephraser.name
        except Exception as e:
            note = f"LLM call failed ({type(e).__name__}: {e}); used template."

    s = portfolio_summary(h)
    glance = pd.DataFrame([{k.title(): s[k] for k in ["red", "amber", "green", "done", "total"]}])
    risks = top_risks(h, n_risks).rename(columns=str.title).rename(columns={"Risk_Note": "Owner note"})
    ws = rollup(h, "workstream")[
        ["workstream", "initiatives", "red", "amber", "green", "done", "overdue", "avg_pct_complete"]
    ].rename(columns={"avg_pct_complete": "avg % complete"})
    stale = h[h["stale"]].sort_values("days_since_update", ascending=False)
    stale = stale[["owner", "initiative", "days_since_update"]].rename(columns={"days_since_update": "days since update"})

    as_of = pd.Timestamp(as_of)
    md = f"""# Weekly initiative status: {as_of:%Y-%m-%d}

Scope: {scope}

## Summary

{summary}

## Health at a glance

{_md_table(glance)}

## Top risks

{_md_table(risks)}

## By workstream

{_md_table(ws)}

## Updates needed (no update in over {STALE_DAYS} days)

{_md_table(stale)}

---
_All figures computed from the tracker data as of {as_of:%Y-%m-%d}. Summary wording: {backend}._
"""
    return Report(markdown=md, backend=backend, note=note)
