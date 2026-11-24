from __future__ import annotations

import re
from datetime import datetime
from typing import Any

RFC3339_DATE_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def require_rfc3339_date_time(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not RFC3339_DATE_TIME_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be an RFC 3339 date-time")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    datetime.fromisoformat(normalized)


def is_rfc3339_date_time(value: Any) -> bool:
    try:
        require_rfc3339_date_time(value, "date-time")
    except ValueError:
        return False
    return True
