"""Entry point: try the model, fall back to rules on any failure."""
from datetime import date

from .llm import extract_llm
from .rules import extract_rules
from .schema import Extraction


def extract(text: str, generate=None, today: date | None = None, note: str = "") -> Extraction:
    if generate is not None:
        try:
            return extract_llm(text, generate, today)
        except Exception as e:  # invalid JSON, schema violation, network error, timeout
            note = f"Model output unusable ({type(e).__name__}: {str(e)[:200]}); used rules."
    ex = extract_rules(text, today)
    ex.note = note
    return ex
