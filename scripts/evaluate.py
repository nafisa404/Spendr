"""Score extraction against hand-labelled items.

    python scripts/evaluate.py                    # rules, main samples
    python scripts/evaluate.py --set holdout      # meetings not used while writing the rules
    python scripts/evaluate.py --backend model    # needs HF_TOKEN or LOCAL_MODEL

Matching: predicted and expected items are paired one-to-one (greedy, best first) when their
content words overlap with Dice >= 0.4. Follow-ups also match on equal dates.
Owner/due accuracy is measured on matched action items only.
"guessed" = predicted an owner/date where the label has none (the thing we must never do).
"""
import argparse
import json
import re
import sys
from datetime import date, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from meeting_assistant.extract import extract  # noqa: E402
from meeting_assistant.llm import get_generator  # noqa: E402

MATCH_AT = 0.4
STOP = set("""a an the and or of to for in on at by with from into is are be we our us it this that
these those will should can could would need needs not no who what when how do does did have has
any all some still now also about before after them they their your you i i'll let's""".split())


def words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        if w in STOP or len(w) < 3:
            continue
        for suf in ("ing", "ed", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


def sim(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    return 2 * len(wa & wb) / (len(wa) + len(wb)) if wa and wb else 0.0


def match(expected, predicted, key_e, key_p, extra=None):
    pairs = []
    for i, e in enumerate(expected):
        for j, p in enumerate(predicted):
            s = sim(key_e(e), key_p(p))
            if extra and extra(e, p):
                s = max(s, 1.0)
            if s >= MATCH_AT:
                pairs.append((s, i, j))
    used_e, used_p, out = set(), set(), []
    for s, i, j in sorted(pairs, reverse=True):
        if i not in used_e and j not in used_p:
            used_e.add(i), used_p.add(j), out.append((i, j))
    return out


def same_person(expected: str | None, predicted: str | None) -> bool:
    if expected is None or predicted is None:
        return expected is predicted
    e, p = expected.lower(), predicted.lower()
    return e == p or e.split()[0] == p.split()[0]


def _d(s):
    return date.fromisoformat(s) if s else None


def _error_kind(field, expected, predicted) -> str:
    if expected is None:
        return f"{field}_guessed"       # filled in a value the notes don't support
    if predicted is None:
        return f"{field}_missed"        # flagged for confirmation although the notes say it
    return f"{field}_wrong"


def evaluate(paths, generate):
    totals = {k: [0, 0, 0] for k in ("decisions", "action_items", "open_questions", "follow_ups")}
    fields = {"matched": 0, "fu_time_ok": 0, "fu_matched": 0,
              **{f"{k}_{s}": 0 for k in ("owner", "due") for s in ("ok", "guessed", "missed", "wrong")}}
    failures, backends = [], set()

    for path in paths:
        exp = json.loads(path.with_suffix(".expected.json").read_text(encoding="utf-8"))
        ex = extract(path.read_text(encoding="utf-8"), generate)
        backends.add(ex.backend + (f" [{ex.note}]" if ex.note else ""))
        name = path.stem

        cats = {
            "decisions": (exp["decisions"], ex.decisions, lambda e: e, lambda p: p.text, None),
            "open_questions": (exp["open_questions"], ex.open_questions, lambda e: e, lambda p: p.text, None),
            "action_items": (exp["action_items"], ex.action_items, lambda e: e["task"], lambda p: p.task, None),
            "follow_ups": (exp["follow_ups"], ex.follow_ups, lambda e: e["title"], lambda p: p.title,
                           lambda e, p: p.date is not None and _d(e["date"]) == p.date),
        }
        for cat, (E, P, ke, kp, extra) in cats.items():
            pairs = match(E, P, ke, kp, extra)
            tp = len(pairs)
            totals[cat][0] += tp
            totals[cat][1] += len(P) - tp
            totals[cat][2] += len(E) - tp
            mi, mj = {i for i, _ in pairs}, {j for _, j in pairs}
            failures += [f"{name}  {cat}  MISSED    {ke(e)!r}" for i, e in enumerate(E) if i not in mi]
            failures += [f"{name}  {cat}  SPURIOUS  {kp(p)!r}" for j, p in enumerate(P) if j not in mj]

            for i, j in pairs:
                e, p = E[i], P[j]
                if cat == "action_items":
                    fields["matched"] += 1
                    if same_person(e["owner"], p.owner):
                        fields["owner_ok"] += 1
                    else:
                        failures.append(f"{name}  owner     {e['task']!r}: expected {e['owner']}, got {p.owner}")
                        fields[_error_kind("owner", e["owner"], p.owner)] += 1
                    if _d(e["due"]) == p.due:
                        fields["due_ok"] += 1
                    else:
                        failures.append(f"{name}  due       {e['task']!r}: expected {e['due']}, got {p.due}")
                        fields[_error_kind("due", e["due"], p.due)] += 1
                elif cat == "follow_ups":
                    fields["fu_matched"] += 1
                    et = time.fromisoformat(e["time"]) if e.get("time") else None
                    if _d(e["date"]) == p.date and et == p.time:
                        fields["fu_time_ok"] += 1
                    else:
                        failures.append(f"{name}  follow-up {e['title']!r}: expected {e['date']} {e.get('time')}, "
                                        f"got {p.date} {p.time}")
    return totals, fields, failures, backends


def pct(n, d):
    return f"{n / d:.0%}" if d else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["main", "holdout", "all"], default="main")
    ap.add_argument("--backend", choices=["rules", "model"], default="rules")
    args = ap.parse_args()

    dirs = {"main": [ROOT / "samples"], "holdout": [ROOT / "samples" / "holdout"],
            "all": [ROOT / "samples", ROOT / "samples" / "holdout"]}[args.set]
    paths = sorted(p for d in dirs for p in d.glob("*.txt"))

    generate = None
    if args.backend == "model":
        generate, note = get_generator()
        if generate is None:
            sys.exit(note)

    totals, f, failures, backends = evaluate(paths, generate)
    print(f"Set: {args.set} ({len(paths)} meetings)   Backend: {', '.join(sorted(backends))}\n")
    print(f"{'category':<16}{'TP':>4}{'FP':>4}{'FN':>4}{'precision':>11}{'recall':>8}")
    for cat, (tp, fp, fn) in totals.items():
        print(f"{cat:<16}{tp:>4}{fp:>4}{fn:>4}{pct(tp, tp + fp):>11}{pct(tp, tp + fn):>8}")
    tp, fp, fn = (sum(v[i] for v in totals.values()) for i in range(3))
    print(f"{'all items':<16}{tp:>4}{fp:>4}{fn:>4}{pct(tp, tp + fp):>11}{pct(tp, tp + fn):>8}")

    m = f["matched"]
    print(f"\nMatched action items: {m}")
    for k in ("owner", "due"):
        print(f"  {k + ' correct':<14}{f[k + '_ok']}/{m} ({pct(f[k + '_ok'], m)})   guessed: {f[k + '_guessed']}"
              f"   missed: {f[k + '_missed']}   wrong: {f[k + '_wrong']}")
    print(f"Matched follow-ups: date+time correct {f['fu_time_ok']}/{f['fu_matched']}")

    print("\nFailures:" if failures else "\nFailures: none")
    for line in failures:
        print("  " + line)


if __name__ == "__main__":
    main()
