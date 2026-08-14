from datetime import date

from trialscribe_worker.retrieval.web_allowlist import (
    DEFAULT_ALLOWED_WEB_DOMAINS,
    canonical_url,
    format_web_passage,
    host_allowed,
    source_identity_for,
)
from trialscribe_worker.utils.constant import MAX_SOURCE_IDENTITY_LENGTH


def test_required_hosts_are_on_the_default_list() -> None:
    for domain in ("cdc.gov", "nih.gov", "who.int", "clinicaltrials.gov", "ncbi.nlm.nih.gov"):
        assert domain in DEFAULT_ALLOWED_WEB_DOMAINS


def test_canonical_url_drops_fragment_and_trailing_slash() -> None:
    assert (
        canonical_url("HTTPS://WWW.CDC.GOV/path/?q=1#frag")
        == "https://www.cdc.gov/path?q=1"
    )
    assert canonical_url("https://www.cdc.gov/") == "https://www.cdc.gov/"
    assert canonical_url("javascript:alert(1)") is None
    assert canonical_url("data:text/plain,hi") is None
    assert canonical_url("   ") is None
    assert canonical_url("not-a-url") is None


def test_www_cdc_matches_cdc_gov() -> None:
    assert host_allowed("https://www.cdc.gov/index")
    assert host_allowed("https://cdc.gov/index")
    assert not host_allowed("https://evil.example/x")
    assert host_allowed(
        "https://evil.example/x",
        domains=frozenset({"evil.example"}),
    )


def test_long_url_identity_is_hashed() -> None:
    short = "https://www.cdc.gov/a"
    assert source_identity_for(short) == short
    long_url = "https://www.cdc.gov/" + ("a" * MAX_SOURCE_IDENTITY_LENGTH)
    identity = source_identity_for(long_url)
    assert identity != long_url
    assert len(identity) == 64


def test_passage_prefix_names_title_url_and_dates() -> None:
    text = format_web_passage(
        title="Adult inclusion",
        url="https://pubmed.ncbi.nlm.nih.gov/1/",
        published_on=date(2020, 1, 15),
        retrieved_on=date(2026, 8, 14),
        body="FAROHEALTH_PUBMED_MARKER",
    )
    assert text == (
        "Title: Adult inclusion\n"
        "URL: https://pubmed.ncbi.nlm.nih.gov/1/\n"
        "Date: 2020-01-15\n"
        "Retrieved: 2026-08-14\n"
        "\n"
        "FAROHEALTH_PUBMED_MARKER"
    )
    unknown = format_web_passage(
        title="Unknown date",
        url="https://www.cdc.gov/x",
        published_on=None,
        retrieved_on=date(2026, 8, 14),
        body="body",
    )
    assert "Date: unknown\n" in unknown
