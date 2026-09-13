"""One way for a pipeline to reach tenant-scoped stores.

A pipeline needs the same four stores whether it is running against a live
database or against in-memory doubles, and it needs them in short bursts: hold a
SQL transaction open across a chat completion and the connection sits idle for
as long as the model takes to answer.

A scope answers both needs. `open()` hands back the stores a unit of work needs
and gives them back afterwards. `TransactionScope` opens one short transaction
per unit; `BoundScope` reuses stores a caller already built. The pipeline reads
the same, so the code that runs in production is the code the tests exercise.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.models.m11_section_record import M11SectionRecord
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.repositories.conversation_memory import ConversationMemoryStore
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.m11_sections import M11SectionStore
from trialscribe_worker.repositories.section_generation_attempts import (
    SectionGenerationAttemptRepository,
)
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.exceptions import WorkerServiceError


class SectionStore(Protocol):
    """Read one M11 section, and save a draft revision of it."""

    async def get_scoped(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        section_number: str,
    ) -> M11SectionRecord | None: ...

    async def revise_draft(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        section_number: str,
        *,
        expected_revision: int,
        content: str,
        author_account_id: UUID,
        now: datetime,
        action: str = ...,
    ) -> bool: ...


class MemoryStore(Protocol):
    """Return the latest bounded window of conversation turns."""

    async def recent(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> list[tuple[str, str]]: ...


class AttemptStore(Protocol):
    """Record what one section attempt did."""

    async def add(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        job_id: UUID,
        attempt: int,
        section_number: str,
        status: str,
        model: str | None = None,
        prompt: str | None = None,
        content: str | None = None,
        error_code: str | None = None,
        citation_ids: list[str] | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class GenerationStores:
    """Everything drafting one section reads from or writes to."""

    evidence: EvidenceIndex
    sections: SectionStore
    memory: MemoryStore
    attempts: AttemptStore


class GenerationScope(Protocol):
    """Hand out generation stores for the length of one unit of work."""

    def open(self) -> AsyncIterator[GenerationStores]: ...


class EvidenceScope(Protocol):
    """Hand out an evidence index for the length of one unit of work."""

    def open(self) -> AsyncIterator[EvidenceIndex]: ...


class BoundScope:
    """Reuse stores the caller already built, and never open a transaction.

    Used by callers that own their own session, and by tests that pass in-memory
    doubles. Reopening the scope hands back the same stores.
    """

    __slots__ = ("_stores",)

    def __init__(self, stores: GenerationStores | EvidenceIndex) -> None:
        self._stores = stores

    @asynccontextmanager
    async def open(self) -> AsyncIterator[GenerationStores | EvidenceIndex]:
        yield self._stores


class TransactionScope:
    """Open one short database transaction for each unit of work.

    Nothing outside the `open()` block holds a connection, so a chat completion
    that takes a minute does not keep a transaction — or its locks — alive for
    that minute.
    """

    __slots__ = ("_runtime", "_chroma", "_context")

    def __init__(
        self,
        runtime: DatabaseRuntime,
        chroma_index: ChromaIndex,
        context: JobContext | None = None,
    ) -> None:
        self._runtime = runtime
        self._chroma = chroma_index
        self._context = context

    @asynccontextmanager
    async def open(self) -> AsyncIterator[GenerationStores]:
        async with self._runtime.transaction() as session:
            stores = GenerationStores(
                evidence=EvidenceIndex(EvidenceChunkRepository(session), self._chroma),
                sections=M11SectionStore(session),
                memory=ConversationMemoryStore(session),
                attempts=SectionGenerationAttemptRepository(session),
            )
            self._publish(stores)
            yield stores

    def _publish(self, stores: GenerationStores) -> None:
        """Keep `JobContext` pointing at the live stores for anything still reading it."""

        if self._context is None:
            return
        self._context.evidence = stores.evidence
        self._context.generate = stores


class EvidenceTransactionScope:
    """Open one short transaction holding only the evidence index."""

    __slots__ = ("_runtime", "_chroma", "_context")

    def __init__(
        self,
        runtime: DatabaseRuntime,
        chroma_index: ChromaIndex,
        context: JobContext | None = None,
    ) -> None:
        self._runtime = runtime
        self._chroma = chroma_index
        self._context = context

    @asynccontextmanager
    async def open(self) -> AsyncIterator[EvidenceIndex]:
        async with self._runtime.transaction() as session:
            evidence = EvidenceIndex(EvidenceChunkRepository(session), self._chroma)
            if self._context is not None:
                self._context.evidence = evidence
            yield evidence


def generation_stores_from(context: JobContext) -> GenerationStores:
    """Read the stores a caller attached to the context, or refuse.

    Callers may attach either a `GenerationStores` or any object carrying the
    three named stores; both are accepted so existing bindings keep working.
    """

    evidence = context.evidence
    if not isinstance(evidence, EvidenceIndex):
        raise WorkerServiceError
    attached = context.generate
    if attached is None:
        raise WorkerServiceError
    if isinstance(attached, GenerationStores):
        return attached
    sections = getattr(attached, "sections", None)
    memory = getattr(attached, "memory", None)
    attempts = getattr(attached, "attempts", None)
    if not _is_section_store(sections) or not _has_callable(memory, "recent"):
        raise WorkerServiceError
    if not _has_callable(attempts, "add"):
        raise WorkerServiceError
    return GenerationStores(
        evidence=evidence,
        sections=sections,  # type: ignore[arg-type]
        memory=memory,  # type: ignore[arg-type]
        attempts=attempts,  # type: ignore[arg-type]
    )


def evidence_from(context: JobContext) -> EvidenceIndex:
    """Read the evidence index a caller attached to the context, or refuse."""

    evidence = context.evidence
    if not isinstance(evidence, EvidenceIndex):
        raise WorkerServiceError
    return evidence


def _has_callable(candidate: object, name: str) -> bool:
    return callable(getattr(candidate, name, None))


def _is_section_store(candidate: object) -> bool:
    return _has_callable(candidate, "get_scoped") and _has_callable(
        candidate,
        "revise_draft",
    )


def require_gateway(context: JobContext) -> ProviderGateway:
    """Read the provider gateway a pipeline must go through, or refuse.

    Every model and embedding call goes through the gateway so that timeouts,
    retries, concurrency limits, circuit breaking, and metering apply. A context
    without one is a wiring defect, not a user error.
    """

    gateway = context.gateway
    if not isinstance(gateway, ProviderGateway):
        raise WorkerServiceError
    return gateway
