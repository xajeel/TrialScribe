from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from docx import Document

from trialscribe_worker.models.evidence_chunk import EvidenceChunk
from trialscribe_worker.models.m11_section_record import M11SectionListRecord
from trialscribe_worker.services.protocol_docx import (
    build_protocol_docx,
    export_filename,
)
from trialscribe_worker.utils.constant import (
    EXPORT_SCOPE_DONE_ONLY,
    EXPORT_SCOPE_INCLUDE_DRAFTS,
    M11_SECTION_DONE_STATUS,
    M11_SECTION_DRAFT_STATUS,
)

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000921")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000922")
CITE_ID = UUID("00000000-0000-4000-8000-000000000923")
MISSING_CITE = UUID("00000000-0000-4000-8000-000000000924")
SECRET_PASSAGE = "SECRET_PASSAGE_TEXT_SHOULD_NOT_APPEAR"
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
SOURCE_IDENTITY = "https://example.test/aurora-eligibility"


def _section(
    number: str,
    title: str,
    content: str,
    status: str,
    position: int,
) -> M11SectionListRecord:
    return M11SectionListRecord(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        section_number=number,
        title=title,
        position=position,
        content=content,
        status=status,
        current_revision=1,
        updated_at=NOW,
    )


def _chunk() -> EvidenceChunk:
    return EvidenceChunk(
        id=CITE_ID,
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        source_kind="web",
        source_identity=SOURCE_IDENTITY,
        page_number=3,
        start_char=0,
        end_char=len(SECRET_PASSAGE),
        text=SECRET_PASSAGE,
        embedding_model="fake-embed",
        embedding_dimensions=384,
    )


def _document(
    *,
    scope: str,
    sections: list[M11SectionListRecord],
    chunks: list[EvidenceChunk] | None = None,
    title: str = "AURORA-301",
) -> Document:
    payload = build_protocol_docx(
        protocol_title=title,
        exported_at=NOW,
        scope=scope,
        sections=sections,
        chunks=[] if chunks is None else chunks,
    )
    return Document(BytesIO(payload))


def _plain_text(document: Document) -> str:
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_headings_follow_given_section_order() -> None:
    document = _document(
        scope=EXPORT_SCOPE_INCLUDE_DRAFTS,
        sections=[
            _section("1", "Protocol Summary", "Summary body", M11_SECTION_DONE_STATUS, 1),
            _section("2", "Introduction", "Intro body", M11_SECTION_DONE_STATUS, 2),
        ],
    )
    text = _plain_text(document)
    assert text.index("1. Protocol Summary") < text.index("2. Introduction")
    assert "Summary body" in text
    assert "Intro body" in text


def test_done_only_omits_draft_chapters() -> None:
    document = _document(
        scope=EXPORT_SCOPE_DONE_ONLY,
        sections=[
            _section("1", "Protocol Summary", "Done wording", M11_SECTION_DONE_STATUS, 1),
            _section("2", "Introduction", "Draft wording", M11_SECTION_DRAFT_STATUS, 2),
        ],
    )
    text = _plain_text(document)
    assert "1. Protocol Summary" in text
    assert "2. Introduction" not in text
    assert "Draft wording" not in text
    assert "Done sections only" in text


def test_include_drafts_marks_unfinished_headings() -> None:
    document = _document(
        scope=EXPORT_SCOPE_INCLUDE_DRAFTS,
        sections=[
            _section("1", "Protocol Summary", "Still drafting", M11_SECTION_DRAFT_STATUS, 1),
        ],
    )
    text = _plain_text(document)
    assert "1. Protocol Summary (Draft)" in text
    assert "Includes unfinished sections (drafts marked)" in text


def test_citations_become_numbered_references_without_passage_text() -> None:
    document = _document(
        scope=EXPORT_SCOPE_DONE_ONLY,
        sections=[
            _section(
                "1",
                "Protocol Summary",
                f"Adults with NSCLC [cite:{CITE_ID}] and extra [cite:{MISSING_CITE}].",
                M11_SECTION_DONE_STATUS,
                1,
            ),
        ],
        chunks=[_chunk()],
    )
    text = _plain_text(document)
    assert "[1]" in text
    assert "[cite:" not in text
    assert SOURCE_IDENTITY in text
    assert "References" in text
    assert "p. 3" in text
    assert SECRET_PASSAGE not in text


def test_hostile_title_still_yields_a_docx_filename() -> None:
    name = export_filename('研究📄 "draft"\r\n', NOW)
    assert name.endswith(".docx")
    assert "\r" not in name
    assert "\n" not in name
    assert name == "draft_protocol_2026-08-15.docx"
