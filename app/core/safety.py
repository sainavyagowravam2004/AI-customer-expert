import re

INJECTION_PATTERNS = [
    r"ignore (all |your )?(previous |prior )?(instructions|rules|prompts)",
    r"reveal (your )?(hidden |system )?(prompt|instructions)",
    r"show me (every|all) customer",
    r"bypass (security|rls|tenant|safety)",
    r"jailbreak",
    r"act as developer mode",
    r"dump database",
    r"select \* from",
    r"override system",
    r"forget everything above",
]

ESCALATION_KEYWORDS = [
    "refund", "chargeback", "lawsuit", "legal action", "attorney", "lawyer",
    "sue you", "angry", "furious", "scam", "fraud", "cancel immediately", "speak to a human", "manager"
]

def detect_prompt_injection(text_val: str) -> bool:
    low = text_val.lower()
    return any(re.search(pat, low) for pat in INJECTION_PATTERNS)

def detect_human_escalation(text_val: str) -> tuple[bool, str]:
    low = text_val.lower()
    for kw in ESCALATION_KEYWORDS:
        if kw in low:
            return True, f"Sensitive trigger detected ('{kw}')"
    return False, ""