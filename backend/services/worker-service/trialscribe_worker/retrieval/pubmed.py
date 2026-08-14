"""Ask NCBI PubMed for title, abstract, and publication date."""

import xml.etree.ElementTree as ET
from datetime import date

import httpx

from trialscribe_worker.retrieval.research_types import ResearchHit
from trialscribe_worker.utils.constant import NCBI_EFETCH_URL, NCBI_ESEARCH_URL
from trialscribe_worker.utils.exceptions import ResearchSourceError

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class PubMedClient:
    """Search PubMed abstracts over HTTPX with a bounded retry budget."""

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
        """Return abstracts for the strongest PubMed matches, or nothing."""

        params: dict[str, str | int] = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
            "tool": "trialscribe",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        payload = await self._json(NCBI_ESEARCH_URL, params)
        ids = _pubmed_ids(payload)
        if not ids:
            return []
        xml_text = await self._text(
            NCBI_EFETCH_URL,
            {
                "db": "pubmed",
                "id": ",".join(ids),
                "rettype": "abstract",
                "retmode": "xml",
                **({"api_key": self._api_key} if self._api_key else {}),
                "tool": "trialscribe",
            },
        )
        return _parse_pubmed_xml(xml_text)

    async def _json(
        self,
        url: str,
        params: dict[str, str | int],
    ) -> object:
        response = await self._send("GET", url, params=params)
        return response.json()

    async def _text(
        self,
        url: str,
        params: dict[str, str | int],
    ) -> str:
        response = await self._send("GET", url, params=params)
        return response.text

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._retry_attempts):
            try:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.HTTPError:
                last_error = ResearchSourceError()
                if attempt + 1 >= self._retry_attempts:
                    raise ResearchSourceError from None
                continue
            if response.status_code in {429} or response.status_code >= 500:
                last_error = ResearchSourceError()
                if attempt + 1 >= self._retry_attempts:
                    raise ResearchSourceError
                continue
            if response.status_code >= 400:
                raise ResearchSourceError
            return response
        raise last_error if last_error is not None else ResearchSourceError()


def _pubmed_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return []
    raw_ids = result.get("idlist")
    if not isinstance(raw_ids, list):
        return []
    return [str(item) for item in raw_ids if str(item).strip()]


def _parse_pubmed_xml(xml_text: str) -> list[ResearchHit]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    hits: list[ResearchHit] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = "".join(article.findtext(".//PMID") or "").strip()
        title = "".join(article.findtext(".//ArticleTitle") or "").strip()
        abstract = " ".join(
            "".join(node.itertext()).strip()
            for node in article.findall(".//AbstractText")
        ).strip()
        if not pmid or not (title or abstract):
            continue
        hits.append(
            ResearchHit(
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                title=title,
                published_on=_pub_date(article),
                body=abstract,
            )
        )
    return hits


def _pub_date(article: ET.Element) -> date | None:
    node = article.find(".//PubDate")
    if node is None:
        return None
    year_text = (node.findtext("Year") or "").strip()
    if not year_text.isdigit():
        return None
    month = _month_number(node.findtext("Month") or "")
    day_text = (node.findtext("Day") or "1").strip()
    day = int(day_text) if day_text.isdigit() else 1
    try:
        return date(int(year_text), month, day)
    except ValueError:
        return None


def _month_number(raw: str) -> int:
    stripped = raw.strip()
    if stripped.isdigit():
        value = int(stripped)
        return value if 1 <= value <= 12 else 1
    return _MONTHS.get(stripped[:3].lower(), 1)
