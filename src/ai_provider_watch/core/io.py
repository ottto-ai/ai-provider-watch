from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "schemas").is_dir():
            return candidate
    raise FileNotFoundError(f"could not find AI Provider Watch repo root from {current}")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_ndjson_text(values: list[dict[str, Any]]) -> str:
    if not values:
        return ""
    return "\n".join(json.dumps(item, sort_keys=True, ensure_ascii=True) for item in values) + "\n"


def event_paths(root: Path) -> list[Path]:
    events_root = root / "data" / "events"
    if not events_root.exists():
        return []
    return sorted(path for path in events_root.rglob("*.json") if path.is_file())


def candidate_paths(root: Path) -> list[Path]:
    candidates_root = root / "data" / "candidates"
    if not candidates_root.exists():
        return []
    return sorted(path for path in candidates_root.rglob("*.json") if path.is_file())
