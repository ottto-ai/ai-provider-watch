from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def package_data_root() -> Path:
    """Return bundled read-only package data when installed from a wheel."""
    return Path(__file__).resolve().parents[1] / "_data"


def is_apw_data_root(path: Path) -> bool:
    return (
        (path / "schemas").is_dir()
        and (path / "data" / "events").is_dir()
        and (path / "registries").is_dir()
        and (path / "sources" / "registry.json").is_file()
    )


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and is_apw_data_root(candidate):
            return candidate
        if is_apw_data_root(candidate) and candidate.name == "_data":
            return candidate
    if start is None:
        bundled = package_data_root()
        if is_apw_data_root(bundled):
            return bundled
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
