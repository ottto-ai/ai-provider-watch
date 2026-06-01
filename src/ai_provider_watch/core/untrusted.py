from __future__ import annotations

import re

PROMPT_INJECTION_MARKERS = (
    "blind merge",
    "call mcp",
    "delete this repository",
    "developer message",
    "disable validation",
    "disregard all previous",
    "do not validate",
    "exfiltrate",
    "ignore all previous",
    "ignore previous instructions",
    "ignore instructions",
    "merge this pr",
    "publish every candidate",
    "release token",
    "run shell",
    "system prompt",
    "tool call",
)

PROMPT_INJECTION_PATTERN = re.compile(
    "|".join(re.escape(marker) for marker in PROMPT_INJECTION_MARKERS),
    re.IGNORECASE,
)


def contains_prompt_injection_marker(value: str) -> bool:
    normalized = re.sub(r"[\s_-]+", " ", value.lower())
    return PROMPT_INJECTION_PATTERN.search(value) is not None or PROMPT_INJECTION_PATTERN.search(normalized) is not None
