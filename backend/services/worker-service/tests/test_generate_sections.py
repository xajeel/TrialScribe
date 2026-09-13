import asyncio
import importlib.util
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.models.m11_section_record import M11SectionRecord
from trialscribe_worker.pipelines.generate_sections import generate_sections_pipeline
from trialscribe_worker.providers.fake import FakeEmbeddingProvider, fake_vector_for
from trialscribe_worker.providers.gateway import MemoryUsageRecorder, ProviderGateway
from trialscribe_worker.providers.types import ChatRequest, ChatResult
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EVIDENCE_SOURCE_TRIAL_DATA,
    GENERATE_EXPECTED_REVISIONS_PARAMETER,
    GENERATE_SECTIONS_PARAMETER,
    M11_SECTION_DONE_STATUS,
    M11_SECTION_DRAFT_STATUS,
)
from trialscribe_worker.utils.enum import JobKind
from trialscribe_worker.utils.exceptions import (
    GenerateSectionError,
    ProviderUnavailableError,
)

_HELPERS = importlib.util.spec_from_file_location(
    "generate_sections_evidence_helpers",
    Path(__file__).with_name("test_evidence_index.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_evidence_helpers = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_evidence_helpers)
MemoryChroma = _evidence_helpers.MemoryChroma
MemoryChunks = _evidence_helpers.MemoryChunks

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000911")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000912")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000913")
JOB_ID = UUID("00000000-0000-4000-8000-000000000914")
MARKER = "FAROHEALTH_INCLUSION_AGE_18"
FOREIGN_ID = UUID("00000000-0000-4000-8000-000000000999")
_ID_IN_PROMPT = re.compile(
    r"id=([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


class CitingChat:
    def __init__(self, fail_on: str | None = None, extra_cite: UUID | None = None) -> None:
        self.fail_on = fail_on
        self.extra_cite = extra_cite
        self.section_calls: list[str] = []

    async def complete(self, request: ChatRequest) -> ChatResult:
        combined = "\n".join(message.content for message in request.messages)
        for number in ("4", "5"):
            if f"number={number}" in combined:
                self.section_calls.append(number)
                if self.fail_on == number:
                    raise ProviderUnavailableError()
        match = _ID_IN_PROMPT.search(combined)
        cite = f"[cite:{match.group(1)}]" if match else ""
        extra = f" [cite:{self.extra_cite}]" if self.extra_cite is not None else ""
        return ChatResult(
            text=f"Inclusion requires {MARKER}. {cite}{extra}",
            model="fake-chat",
            input_tokens=10,
            output_tokens=5,
            cache_hit_tokens=0,
            latency_ms=1,
        )


class MemorySections:
    def __init__(self, rows: dict[str, M11SectionRecord]) -> None:
        self.rows = dict(rows)

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        section_number: str,
    ) -> M11SectionRecord | None:
        del organization_id, conversation_id
        return self.rows.get(section_number)

    async def revise_draft(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        expected_revision: int,
        content: str,
        author_account_id: UUID,
        now: object,
        action: str = "revised",
    ) -> bool:
        del organization_id, conversation_id, author_account_id, now, action
        row = self.rows.get(section_number)
        if (
            row is None
            or row.status != M11_SECTION_DRAFT_STATUS
            or row.current_revision != expected_revision
        ):
            return False
        self.rows[section_number] = replace(
            row,
            content=content,
            current_revision=row.current_revision + 1,
        )
        return True


class MemoryMemory:
    async def recent(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> list[tuple[str, str]]:
        del organization_id, conversation_id, limit
        return []


class MemoryAttempts:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add(self, **values: object) -> None:
        self.rows.append(values)


async def _no_sleep(_seconds: float) -> None:
    return None


async def _never_cancelled() -> None:
    return None


def _section(number: str, title: str, *, revision: int = 0, status: str = M11_SECTION_DRAFT_STATUS, content: str = "") -> M11SectionRecord:
    return M11SectionRecord(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        section_number=number,
        title=title,
        instructions="Include adults.",
        content=content,
        status=status,
        current_revision=revision,
    )


def _gateway(chat: object) -> ProviderGateway:
    return ProviderGateway(
        chat,  # type: ignore[arg-type]
        FakeEmbeddingProvider(),
        WorkerSettings(provider_retry_attempts=1),
        MemoryUsageRecorder(),
        sleep=_no_sleep,
        rng=lambda: 0.0,
    )


def _evidence() -> EvidenceIndex:
    return EvidenceIndex(
        MemoryChunks(),  # type: ignore[arg-type]
        ChromaIndex(MemoryChroma(), embed_query=None),
    )


def _context(
    *,
    evidence: EvidenceIndex,
    gateway: ProviderGateway,
    sections: MemorySections,
    attempts: MemoryAttempts,
) -> JobContext:
    reports: list[int] = []

    async def report(percent: int) -> None:
        reports.append(percent)

    return JobContext(
        job_id=JOB_ID,
        attempt=1,
        parameters={
            GENERATE_SECTIONS_PARAMETER: list(sections.rows),
            GENERATE_EXPECTED_REVISIONS_PARAMETER: {
                number: row.current_revision for number, row in sections.rows.items()
            },
        },
        report=report,
        check_cancelled=_never_cancelled,
        organization_id=ORGANIZATION_ID,
        account_id=ACCOUNT_ID,
        conversation_id=CONVERSATION_ID,
        gateway=gateway,
        evidence=evidence,
        generate=SimpleNamespace(
            sections=sections,
            memory=MemoryMemory(),
            attempts=attempts,
        ),
        max_attempts=2,
    )


async def _seed_trial(evidence: EvidenceIndex, text: str) -> UUID:
    chunk = await evidence.put(
        organization_id=ORGANIZATION_ID,
        conversation_id=CONVERSATION_ID,
        text=text,
        vector=fake_vector_for(text),
        source_kind=EVIDENCE_SOURCE_TRIAL_DATA,
        source_identity="trial-1",
        start_char=0,
        end_char=len(text),
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
    )
    return chunk.id


def test_generate_sections_kind_is_plain_text() -> None:
    assert JobKind.GENERATE_SECTIONS.value == "generate_sections"
    assert "section-generation" not in {kind.value for kind in JobKind}


def test_second_section_failure_keeps_the_first_draft() -> None:
    evidence = _evidence()
    asyncio.run(_seed_trial(evidence, MARKER))
    sections = MemorySections(
        {
            "5": _section("5", "TRIAL POPULATION"),
            "4": _section("4", "TRIAL DESIGN"),
        }
    )
    chat = CitingChat(fail_on="4")
    with pytest.raises(GenerateSectionError):
        asyncio.run(
            generate_sections_pipeline(
                _context(
                    evidence=evidence,
                    gateway=_gateway(chat),
                    sections=sections,
                    attempts=MemoryAttempts(),
                )
            )
        )
    assert MARKER in sections.rows["5"].content
    assert sections.rows["5"].current_revision == 1
    assert sections.rows["4"].content == ""
    assert sections.rows["4"].current_revision == 0


def test_retry_skips_the_section_that_already_moved() -> None:
    evidence = _evidence()
    asyncio.run(_seed_trial(evidence, MARKER))
    sections = MemorySections(
        {
            "5": _section("5", "TRIAL POPULATION"),
            "4": _section("4", "TRIAL DESIGN"),
        }
    )
    first = CitingChat(fail_on="4")
    with pytest.raises(GenerateSectionError):
        asyncio.run(
            generate_sections_pipeline(
                _context(
                    evidence=evidence,
                    gateway=_gateway(first),
                    sections=sections,
                    attempts=MemoryAttempts(),
                )
            )
        )
    first_content = sections.rows["5"].content
    first_revision = sections.rows["5"].current_revision
    second = CitingChat(fail_on="4")
    context = _context(
        evidence=evidence,
        gateway=_gateway(second),
        sections=sections,
        attempts=MemoryAttempts(),
    )
    context.parameters[GENERATE_EXPECTED_REVISIONS_PARAMETER] = {"5": 0, "4": 0}
    with pytest.raises(GenerateSectionError):
        asyncio.run(generate_sections_pipeline(context))
    assert sections.rows["5"].content == first_content
    assert sections.rows["5"].current_revision == first_revision
    assert "5" not in second.section_calls
    assert second.section_calls == ["4"]


def test_unresolved_citation_is_stripped() -> None:
    evidence = _evidence()
    chunk_id = asyncio.run(_seed_trial(evidence, MARKER))
    sections = MemorySections({"5": _section("5", "TRIAL POPULATION")})
    asyncio.run(
        generate_sections_pipeline(
            _context(
                evidence=evidence,
                gateway=_gateway(CitingChat(extra_cite=FOREIGN_ID)),
                sections=sections,
                attempts=MemoryAttempts(),
            )
        )
    )
    content = sections.rows["5"].content
    assert f"[cite:{chunk_id}]" in content
    assert f"[cite:{FOREIGN_ID}]" not in content


def test_done_section_is_not_overwritten() -> None:
    evidence = _evidence()
    asyncio.run(_seed_trial(evidence, MARKER))
    sections = MemorySections(
        {
            "5": _section(
                "5",
                "TRIAL POPULATION",
                status=M11_SECTION_DONE_STATUS,
                content="keep me",
            )
        }
    )
    asyncio.run(
        generate_sections_pipeline(
            _context(
                evidence=evidence,
                gateway=_gateway(CitingChat()),
                sections=sections,
                attempts=MemoryAttempts(),
            )
        )
    )
    asyncio.run(
        generate_sections_pipeline(
            _context(
                evidence=evidence,
                gateway=_gateway(CitingChat()),
                sections=sections,
                attempts=MemoryAttempts(),
            )
        )
    )
    assert sections.rows["5"].content == "keep me"
    assert sections.rows["5"].current_revision == 0
