"""Keep only citation markers that point at retrieved passages."""

import re
from uuid import UUID

_CITE_PATTERN = re.compile(
    r"\[cite:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]"
)


def parse_cite_ids(text: str) -> list[UUID]:
    """Return unique citation ids in the order they first appear."""

    found: list[UUID] = []
    seen: set[UUID] = set()
    for match in _CITE_PATTERN.finditer(text):
        chunk_id = UUID(match.group(1))
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        found.append(chunk_id)
    return found


def apply_citations(text: str, allowed: set[UUID]) -> str:
    """Drop citation markers whose ids are not in the allowed set."""

    def replace(match: re.Match[str]) -> str:
        chunk_id = UUID(match.group(1))
        if chunk_id in allowed:
            return match.group(0)
        return ""

    return _CITE_PATTERN.sub(replace, text)


def apply_numbered_citations(text: str, ordered: list[UUID]) -> str:
    """Replace remaining citation markers with 1-based numbers from `ordered`."""

    index = {chunk_id: number for number, chunk_id in enumerate(ordered, start=1)}

    def replace(match: re.Match[str]) -> str:
        chunk_id = UUID(match.group(1))
        number = index.get(chunk_id)
        if number is None:
            return ""
        return f"[{number}]"

    return _CITE_PATTERN.sub(replace, apply_citations(text, set(ordered)))


def number_citations(text: str, allowed: set[UUID]) -> tuple[str, list[UUID]]:
    """Drop unresolved markers and number the rest in first-appearance order."""

    cleaned = apply_citations(text, allowed)
    ordered = parse_cite_ids(cleaned)
    return apply_numbered_citations(text, ordered), ordered
