"""Ask Tavily for allow-listed web pages over HTTPX."""

from datetime import date

import httpx

from trialscribe_worker.retrieval.research_types import ResearchHit
from trialscribe_worker.retrieval.web_allowlist import DEFAULT_ALLOWED_WEB_DOMAINS
from trialscribe_worker.utils.constant import TAVILY_SEARCH_URL
from trialscribe_worker.utils.exceptions import ResearchSourceError


class TavilyClient:
    """Search trusted websites, or return nothing when no key is configured."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        timeout_seconds: float,
        retry_attempts: int,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._retry_attempts = retry_attempts

    async def search(self, query: str, *, max_results: int) -> list[ResearchHit]:
        """Return snippets from the allow-listed web search, if a key is set."""

        if not self._api_key:
            return []
        payload = await self._json(
            {
                "query": query,
                "max_results": max_results,
                "include_domains": sorted(DEFAULT_ALLOWED_WEB_DOMAINS),
            }
        )
        return _hits_from(payload)

    async def _json(self, body: dict[str, object]) -> object:
        last_error: Exception | None = None
        headers = {"Authorization": f"Bearer {self._api_key}"}
        for attempt in range(self._retry_attempts):
            try:
                response = await self._client.post(
                    TAVILY_SEARCH_URL,
                    json=body,
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.HTTPError:
                last_error = ResearchSourceError()
                if attempt + 1 >= self._retry_attempts:
                    raise ResearchSourceError from None
                continue
            if response.status_code == 429 or response.status_code >= 500:
                last_error = ResearchSourceError()
                if attempt + 1 >= self._retry_attempts:
                    raise ResearchSourceError
                continue
            if response.status_code >= 400:
                raise ResearchSourceError
            return response.json()
        raise last_error if last_error is not None else ResearchSourceError()


def _hits_from(payload: object) -> list[ResearchHit]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("results")
    if not isinstance(rows, list):
        return []
    hits: list[ResearchHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        body = str(row.get("content") or "").strip()
        if not url:
            continue
        hits.append(
            ResearchHit(
                url=url,
                title=title,
                published_on=_parse_day(str(row.get("published_date") or "")),
                body=body,
            )
        )
    return hits


def _parse_day(raw: str) -> date | None:
    stripped = raw.strip()
    if len(stripped) < 10:
        return None
    try:
        return date.fromisoformat(stripped[:10])
    except ValueError:
        return None
