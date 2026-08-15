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
