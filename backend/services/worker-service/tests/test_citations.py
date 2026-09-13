from uuid import UUID

from trialscribe_worker.retrieval.citations import (
    apply_citations,
    number_citations,
    parse_cite_ids,
)

ALLOWED = UUID("00000000-0000-4000-8000-000000000001")
FOREIGN = UUID("00000000-0000-4000-8000-000000000002")


def test_parse_cite_ids_keeps_first_appearance_order() -> None:
    text = (
        f"Start [cite:{FOREIGN}] mid [cite:{ALLOWED}] "
        f"again [cite:{FOREIGN}]"
    )
    assert parse_cite_ids(text) == [FOREIGN, ALLOWED]


def test_apply_citations_drops_unresolved_markers() -> None:
    text = f"Kept [cite:{ALLOWED}] gone [cite:{FOREIGN}] end"
    cleaned = apply_citations(text, {ALLOWED})
    assert f"[cite:{ALLOWED}]" in cleaned
    assert f"[cite:{FOREIGN}]" not in cleaned
    assert "Kept" in cleaned
    assert "end" in cleaned


def test_apply_citations_does_not_invent_markers() -> None:
    assert apply_citations("no markers", {ALLOWED}) == "no markers"


def test_number_citations_uses_first_appearance_and_drops_unresolved() -> None:
    text = f"Start [cite:{FOREIGN}] mid [cite:{ALLOWED}] again [cite:{ALLOWED}]"
    numbered, ordered = number_citations(text, {ALLOWED})
    assert ordered == [ALLOWED]
    assert numbered == "Start  mid [1] again [1]"
    assert "[cite:" not in numbered
