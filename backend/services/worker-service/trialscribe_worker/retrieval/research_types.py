"""Hits returned by a research library, ready to store as evidence."""

from datetime import date
from typing import Protocol
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchHit:
    """One page or paper a research library offered for a question."""

    url: str
    title: str
    published_on: date | None
    body: str


class ResearchSource(Protocol):
    """One library the research job may ask."""

    async def search(self, query: str, *, max_results: int) -> list[ResearchHit]: ...
