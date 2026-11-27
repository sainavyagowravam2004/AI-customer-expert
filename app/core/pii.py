import re

PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"), "[PHONE_REDACTED]"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CARD_REDACTED]"),
]

def mask_pii(text: str) -> str:
    masked = text
    for pattern, replacement in PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked
