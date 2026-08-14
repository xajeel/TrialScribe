import asyncio
from collections.abc import Callable

import httpx

from trialscribe_worker.retrieval.pubmed import PubMedClient
from trialscribe_worker.retrieval.tavily import TavilyClient
from trialscribe_worker.utils.constant import NCBI_EFETCH_URL, NCBI_ESEARCH_URL, TAVILY_SEARCH_URL
from trialscribe_worker.utils.exceptions import ResearchSourceError

PMID = "12345678"
PUBMED_SEARCH = {
    "esearchresult": {"idlist": [PMID]},
}
PUBMED_XML = f"""
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>{PMID}</PMID>
      <Article>
        <ArticleTitle>Fixture paper</ArticleTitle>
        <Abstract><AbstractText>FAROHEALTH_PUBMED_MARKER</AbstractText></Abstract>
        <Journal>
          <JournalIssue>
            <PubDate>
              <Year>2020</Year>
              <Month>Jan</Month>
              <Day>15</Day>
            </PubDate>
          </JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
""".strip()
TAVILY_BODY = {
    "results": [
        {
            "url": "https://www.cdc.gov/farohealth-fixture",
            "title": "CDC fixture",
            "content": "FAROHEALTH_WEB_MARKER",
            "published_date": "2021-02-03",
        }
    ]
}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_pubmed_fixture_yields_one_hit() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(NCBI_ESEARCH_URL):
                return httpx.Response(200, json=PUBMED_SEARCH)
            if str(request.url).startswith(NCBI_EFETCH_URL):
                return httpx.Response(200, text=PUBMED_XML)
            return httpx.Response(404)

        async with _client(handler) as http:
            client = PubMedClient(
                http,
                api_key="",
                timeout_seconds=5.0,
                retry_attempts=1,
            )
            hits = await client.search("adult inclusion", max_results=1)
        assert len(hits) == 1
        assert PMID in hits[0].url
        assert hits[0].title == "Fixture paper"
        assert hits[0].body == "FAROHEALTH_PUBMED_MARKER"
        assert hits[0].published_on is not None
        assert hits[0].published_on.isoformat() == "2020-01-15"

    asyncio.run(run())


def test_pubmed_retries_once_after_server_error() -> None:
    calls = {"n": 0}

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(NCBI_ESEARCH_URL):
                calls["n"] += 1
                if calls["n"] == 1:
                    return httpx.Response(500, text="upstream exploded")
                return httpx.Response(200, json=PUBMED_SEARCH)
            return httpx.Response(200, text=PUBMED_XML)

        async with _client(handler) as http:
            client = PubMedClient(
                http,
                api_key="",
                timeout_seconds=5.0,
                retry_attempts=2,
            )
            hits = await client.search("query", max_results=1)
        assert len(hits) == 1
        assert calls["n"] == 2

    asyncio.run(run())


def test_pubmed_error_does_not_include_response_text() -> None:
    async def run() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="secret-body")

        async with _client(handler) as http:
            client = PubMedClient(
                http,
                api_key="",
                timeout_seconds=5.0,
                retry_attempts=1,
            )
            try:
                await client.search("query", max_results=1)
            except ResearchSourceError as error:
                assert "secret-body" not in str(error)
                assert "secret-body" not in repr(error)
                return
        raise AssertionError("expected ResearchSourceError")

    asyncio.run(run())


def test_tavily_without_a_key_does_not_http() -> None:
    calls = {"n": 0}

    async def run() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=TAVILY_BODY)

        async with _client(handler) as http:
            client = TavilyClient(
                http,
                api_key="",
                timeout_seconds=5.0,
                retry_attempts=1,
            )
            hits = await client.search("query", max_results=1)
        assert hits == []
        assert calls["n"] == 0

    asyncio.run(run())


def test_tavily_maps_one_result() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url).startswith(TAVILY_SEARCH_URL)
            assert request.headers.get("authorization") == "Bearer test-key"
            return httpx.Response(200, json=TAVILY_BODY)

        async with _client(handler) as http:
            client = TavilyClient(
                http,
                api_key="test-key",
                timeout_seconds=5.0,
                retry_attempts=1,
            )
            hits = await client.search("query", max_results=1)
        assert len(hits) == 1
        assert hits[0].url == "https://www.cdc.gov/farohealth-fixture"
        assert hits[0].title == "CDC fixture"
        assert hits[0].body == "FAROHEALTH_WEB_MARKER"
        assert hits[0].published_on is not None
        assert hits[0].published_on.isoformat() == "2021-02-03"

    asyncio.run(run())


def test_tavily_error_does_not_include_response_text() -> None:
    async def run() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, text="secret-body")

        async with _client(handler) as http:
            client = TavilyClient(
                http,
                api_key="test-key",
                timeout_seconds=5.0,
                retry_attempts=1,
            )
            try:
                await client.search("query", max_results=1)
            except ResearchSourceError as error:
                assert "secret-body" not in str(error)
                assert "secret-body" not in repr(error)
                return
        raise AssertionError("expected ResearchSourceError")

    asyncio.run(run())
