from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from ai_provider_watch.sources.registry import SourceDescriptor


@dataclass(frozen=True)
class ScopedSourceContent:
    raw: bytes
    errors: list[str]


@dataclass(frozen=True)
class _Heading:
    level: int
    start: int
    text: str


class _HeadingTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


HEADING_PATTERN = re.compile(r"<h([1-6])\b[^>]*>.*?</h\1>", re.IGNORECASE | re.DOTALL)
IGNORED_HTML_PATTERN = re.compile(
    r"<!--.*?-->|<(script|style|noscript|template)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _heading_text(fragment: str) -> str:
    parser = _HeadingTextParser()
    parser.feed(fragment)
    return _normalize_text(" ".join(parser.parts))


def _mask_ignored_html(html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return " " * (match.end() - match.start())

    return IGNORED_HTML_PATTERN.sub(replace, html)


def _iter_headings(html: str) -> list[_Heading]:
    headings: list[_Heading] = []
    scoped_html = _mask_ignored_html(html)
    for match in HEADING_PATTERN.finditer(scoped_html):
        headings.append(
            _Heading(
                level=int(match.group(1)),
                start=match.start(),
                text=_heading_text(html[match.start() : match.end()]),
            )
        )
    return headings


def _matches_heading(heading_text: str, expected: str) -> bool:
    expected_text = _normalize_text(expected)
    return bool(expected_text) and expected_text in heading_text


def _scope_html_heading_range(raw: bytes, scope: dict[str, Any]) -> ScopedSourceContent:
    html = raw.decode("utf-8", errors="ignore")
    start_heading = scope.get("start_heading")
    end_headings = scope.get("end_headings", [])
    if not isinstance(start_heading, str) or not start_heading.strip():
        return ScopedSourceContent(raw=b"", errors=["content_scope start_heading is missing"])
    if not isinstance(end_headings, list):
        end_headings = []
    end_heading_values = [value for value in end_headings if isinstance(value, str)]

    headings = _iter_headings(html)
    start_index = next(
        (
            index
            for index, heading in enumerate(headings)
            if _matches_heading(heading.text, start_heading)
        ),
        None,
    )
    if start_index is None:
        return ScopedSourceContent(
            raw=b"",
            errors=[f"content_scope start heading not found: {start_heading}"],
        )

    start = headings[start_index].start
    end = len(html)
    start_level = headings[start_index].level
    for heading in headings[start_index + 1 :]:
        if end_heading_values and any(
            _matches_heading(heading.text, end_heading) for end_heading in end_heading_values
        ):
            end = heading.start
            break
        if heading.level <= start_level:
            end = heading.start
            break

    return ScopedSourceContent(raw=html[start:end].encode("utf-8"), errors=[])


def scoped_source_content(source: SourceDescriptor, raw: bytes) -> ScopedSourceContent:
    scope = source.content_scope
    if not scope:
        return ScopedSourceContent(raw=raw, errors=[])
    if scope.get("kind") == "html_heading_range":
        return _scope_html_heading_range(raw, scope)
    return ScopedSourceContent(
        raw=b"",
        errors=[f"unsupported content_scope kind: {scope.get('kind')}"],
    )
