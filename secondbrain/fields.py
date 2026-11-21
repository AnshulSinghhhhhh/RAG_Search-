"""Conservative extraction of three exact fields from image OCR lines."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


LABELS = {
    "receipt_total": re.compile(r"\b(?:grand\s+total|receipt\s+total|total(?:\s+amount)?|amount\s+due)\b", re.I),
    "invoice_id": re.compile(r"\binvoice\s*(?:identifiers?\b|numbers?\b|no\.?\b|ids?\b|#)", re.I),
    "product_price": re.compile(r"\b(?:(?:displayed|product|sale)\s+)?price\b|\bhow much (?:does|did|is|was)\b", re.I),
}
TOTAL_LABEL = re.compile(r"^(?:grand\s+total|receipt\s+total|total(?:\s+amount)?|amount\s+due)\b", re.I)
INVOICE_LABEL = re.compile(r"^invoice\s*(?:number\b|no\b\.?|id\b|#)?\s*[:#-]?\s*", re.I)
INVOICE_ID = re.compile(r"(?=[A-Z0-9./_-]*\d)[A-Z0-9]+(?:[-./_][A-Z0-9]+)*", re.I)
INVOICE_PREFIX = re.compile(r"(?:INV|INVOICE)[-#][A-Z0-9]+(?:[-./_][A-Z0-9]+)*", re.I)
CURRENCY = r"(?:INR|USD|EUR|GBP|CAD|AUD|JPY|₹|\$|€|£|¥)"
AMOUNT = r"(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?"
MONEY = re.compile(rf"(?:(?P<before>{CURRENCY})\s*)?(?P<amount>{AMOUNT})(?:\s*(?P<after>{CURRENCY}))?", re.I)
PRICE_LABEL = re.compile(r"^(?:(?:displayed|product)\s+)?price\s*[:=]?\s*", re.I)
UNSUPPORTED = re.compile(r"\b(?:subtotal|sub-total|tax|discount|shipping|change due|refund|unit price|list price|original price|compare at|was price|mrp)\b", re.I)
STOP_WORDS = set("a an the for from of on in at is was did does cost what whats s show find tell give me my this that it please receipt receipts invoice screenshot image saved product displayed amount paid".split())


@dataclass(frozen=True)
class FieldQuestion:
    kind: str
    subject: str


def tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return re.findall(r"[^\W_]+", "".join(c for c in normalized if not unicodedata.combining(c)))


def field_question(query: str) -> FieldQuestion | None:
    # Ambiguous and compound requests belong to the general Ask flow.
    if UNSUPPORTED.search(query) or re.search(r"\b(?:totals|prices|each|all|between)\b", query, re.I):
        return None
    matches = [(kind, pattern) for kind, pattern in LABELS.items() if pattern.search(query)]
    if len(matches) != 1:
        return None
    kind, pattern = matches[0]
    subject = " ".join(word for word in tokens(pattern.sub(" ", query)) if word not in STOP_WORDS)
    return FieldQuestion(kind, subject)


def matches_subject(lines: list[dict], question: FieldQuestion) -> bool:
    words = " ".join(word for line in lines for word in tokens(line["text"]) if word not in STOP_WORDS)
    return not question.subject or f" {question.subject} " in f" {words} "


def _on_right(label: dict, value: dict) -> bool:
    left = label["box"]
    right = value["box"]
    return right[0] >= left[2] - 3 and min(left[3], right[3]) > max(left[1], right[1])


def _reading(line: dict, value: str, other: dict | None = None) -> dict:
    box = line["box"]
    text = line["text"]
    if other is not None:
        right = other["box"]
        box = [min(box[0], right[0]), min(box[1], right[1]), max(box[2], right[2]), max(box[3], right[3])]
        text += " " + other["text"]
    return {"value": value, "text": text, "box": box}


def _money(text: str, require_currency: bool = False) -> str | None:
    match = MONEY.fullmatch(text.lstrip(" :=#").strip())
    if match and (not require_currency or match["before"] or match["after"]):
        return match[0]
    return None


def _invoice(text: str) -> str | None:
    value = text.strip()
    return value if INVOICE_ID.fullmatch(value) else None


def field_readings(lines: list[dict], kind: str, *, price_context: bool | None = None) -> list[dict]:
    if price_context is None:
        price_context = any(re.search(r"[^\W\d_]", line["text"]) and not MONEY.fullmatch(line["text"].strip())
                            for line in lines) and not any(TOTAL_LABEL.match(line["text"].strip()) for line in lines)
    readings = []
    for line in lines:
        text = line["text"].strip()
        if UNSUPPORTED.search(text):
            continue
        if kind == "receipt_total":
            label, parse = TOTAL_LABEL.match(text), _money
        elif kind == "invoice_id":
            if INVOICE_PREFIX.fullmatch(text) and any(c.isdigit() for c in text):
                readings.append(_reading(line, text))
                continue
            label, parse = INVOICE_LABEL.match(text), _invoice
        else:
            if not price_context:
                continue
            if value := _money(text, require_currency=True):
                readings.append(_reading(line, value))
                continue
            label, parse = PRICE_LABEL.match(text), _money
        if label is None:
            continue
        remainder = text[label.end():].lstrip(" :=#")
        if value := parse(remainder):
            readings.append(_reading(line, value))
        elif not remainder or re.fullmatch(CURRENCY, remainder, re.I):
            for other in lines:
                if _on_right(line, other) and (value := parse(f"{remainder} {other['text']}".strip())):
                    readings.append(_reading(line, value, other))
    return readings


def retry_region(lines: list[dict], readings: list[dict], kind: str) -> list[int] | None:
    labels = {"receipt_total": TOTAL_LABEL, "invoice_id": INVOICE_LABEL, "product_price": PRICE_LABEL}
    boxes = [reading["box"] for reading in readings]
    if not boxes:
        boxes = [line["box"] for line in lines if labels[kind].match(line["text"].strip())]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
