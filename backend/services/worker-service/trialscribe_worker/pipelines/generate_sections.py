"""Draft requested M11 sections from tenant-scoped evidence with citations."""

from datetime import UTC, datetime
from types import SimpleNamespace

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.prompts.section_generation import section_generation_messages
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import ChatRequest
from trialscribe_worker.repositories.conversation_memory import ConversationMemoryStore
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.m11_sections import M11SectionStore
from trialscribe_worker.repositories.section_generation_attempts import (
    SectionGenerationAttemptRepository,
)
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
from trialscribe_worker.retrieval.citations import apply_citations, parse_cite_ids
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    EVIDENCE_SOURCE_TRIAL_DATA,
    GENERATE_EXPECTED_REVISIONS_PARAMETER,
    GENERATE_MEMORY_TURN_LIMIT,
    GENERATE_SECTION_NUMBERS,
    GENERATE_SECTIONS_PARAMETER,
    M11_SECTION_DONE_STATUS,
)
from trialscribe_worker.utils.enum import GenerationAttemptStatus, GenerationErrorCode
from trialscribe_worker.utils.exceptions import (
    GenerateSectionError,
    InvalidJobInputError,
    ProviderCircuitOpenError,
    ProviderConfigError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    WorkerServiceError,
)

_PROVIDER_ERRORS = (
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderRateLimitedError,
    ProviderCircuitOpenError,
    ProviderConfigError,
)


def parse_generate_request(parameters: dict[str, object]) -> list[tuple[str, int]]:
    """Return ordered (section_number, expected_revision) pairs, or refuse."""

    numbers = parameters.get(GENERATE_SECTIONS_PARAMETER)
    expected = parameters.get(GENERATE_EXPECTED_REVISIONS_PARAMETER)
    if not isinstance(numbers, list) or not numbers:
        raise InvalidJobInputError
    if any(not isinstance(item, str) for item in numbers):
        raise InvalidJobInputError
    if len(set(numbers)) != len(numbers):
        raise InvalidJobInputError
    if any(item not in GENERATE_SECTION_NUMBERS for item in numbers):
        raise InvalidJobInputError
    if not isinstance(expected, dict):
        raise InvalidJobInputError
    pairs: list[tuple[str, int]] = []
    for number in numbers:
        if number not in expected:
            raise InvalidJobInputError
        revision = expected[number]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise InvalidJobInputError
        pairs.append((number, revision))
    return pairs


async def _record(
    context: JobContext,
    section_number: str,
    status: str,
    *,
    model: str | None = None,
    prompt: str | None = None,
    content: str | None = None,
    error_code: str | None = None,
    citation_ids: list[str] | None = None,
) -> None:
    attempts = getattr(context.generate, "attempts", None)
    add = getattr(attempts, "add", None)
    if not callable(add):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    await add(
        organization_id=context.organization_id,
        conversation_id=context.conversation_id,
        job_id=context.job_id,
        attempt=context.attempt,
        section_number=section_number,
        status=status,
        model=model,
        prompt=prompt,
        content=content,
        error_code=error_code,
        citation_ids=citation_ids or [],
    )


async def generate_one_section(
    context: JobContext,
    section_number: str,
    expected_revision: int,
) -> str:
    """Draft one section. Return succeeded, skipped, or failed."""

    if context.gateway is None or context.evidence is None or context.generate is None:
        raise WorkerServiceError
    if not isinstance(context.gateway, ProviderGateway):
        raise WorkerServiceError
    if not isinstance(context.evidence, EvidenceIndex):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    sections = getattr(context.generate, "sections", None)
    memory_store = getattr(context.generate, "memory", None)
    get_scoped = getattr(sections, "get_scoped", None)
    revise_draft = getattr(sections, "revise_draft", None)
    recent = getattr(memory_store, "recent", None)
    if not callable(get_scoped) or not callable(revise_draft) or not callable(recent):
        raise WorkerServiceError
    conversation_id = context.conversation_id
    record = await get_scoped(
        context.organization_id,
        conversation_id,
        section_number,
    )
    if record is None:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.FAILED.value,
            error_code=GenerationErrorCode.MISSING_SECTION.value,
        )
        return GenerationAttemptStatus.FAILED.value
    if record.status == M11_SECTION_DONE_STATUS:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.SKIPPED.value,
        )
        return GenerationAttemptStatus.SKIPPED.value
    if record.current_revision != expected_revision:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.SKIPPED.value,
            error_code=GenerationErrorCode.REVISION_CONFLICT.value,
        )
        return GenerationAttemptStatus.SKIPPED.value
    settings = WorkerSettings()
    query = record.title
    if record.instructions.strip():
        query = f"{record.title}\n{record.instructions}"
    retriever = ConversationRetriever(context.gateway, context.evidence, settings)
    try:
        retrieved = await retriever.retrieve(
            organization_id=context.organization_id,
            conversation_id=conversation_id,
            query=query,
            job_id=context.job_id,
            account_id=context.account_id,
            k=settings.retrieve_k,
        )
        turns = await recent(
            context.organization_id,
            conversation_id,
            GENERATE_MEMORY_TURN_LIMIT,
        )
        trial_passages = [
            chunk.text
            for chunk in retrieved
            if chunk.source_kind == EVIDENCE_SOURCE_TRIAL_DATA
        ]
        messages = section_generation_messages(
            section_number=record.section_number,
            title=record.title,
            instructions=record.instructions,
            trial_passages=trial_passages,
            evidence=list(retrieved),
            memory=list(turns),
        )
        prompt = "\n\n".join(message.content for message in messages)
        completed = await context.gateway.complete(
            ChatRequest(
                messages=messages,
                model=settings.chat_model,
                organization_id=context.organization_id,
                conversation_id=conversation_id,
                job_id=context.job_id,
                account_id=context.account_id,
                idempotency_key=(
                    f"{context.job_id}:{context.attempt}:generate:{section_number}"
                ),
                thinking=False,
            )
        )
    except _PROVIDER_ERRORS:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.FAILED.value,
            error_code=GenerationErrorCode.PROVIDER_FAILED.value,
        )
        return GenerationAttemptStatus.FAILED.value
    allowed = {chunk.id for chunk in retrieved}
    cleaned = apply_citations(completed.text, allowed).strip()
    if not cleaned:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.FAILED.value,
            model=completed.model,
            prompt=prompt,
            error_code=GenerationErrorCode.EMPTY_OUTPUT.value,
        )
        return GenerationAttemptStatus.FAILED.value
    saved = await revise_draft(
        context.organization_id,
        conversation_id,
        section_number,
        expected_revision=expected_revision,
        content=cleaned,
        author_account_id=context.account_id,
        now=datetime.now(UTC),
    )
    if not saved:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.FAILED.value,
            model=completed.model,
            prompt=prompt,
            content=cleaned,
            error_code=GenerationErrorCode.REVISION_CONFLICT.value,
        )
        return GenerationAttemptStatus.FAILED.value
    cited = [str(chunk_id) for chunk_id in parse_cite_ids(cleaned)]
    await _record(
        context,
        section_number,
        GenerationAttemptStatus.SUCCEEDED.value,
        model=completed.model,
        prompt=prompt,
        content=cleaned,
        citation_ids=cited,
    )
    return GenerationAttemptStatus.SUCCEEDED.value


async def generate_sections_pipeline(context: JobContext) -> None:
    """Draft every requested section that still matches its expected revision."""

    if context.gateway is None or context.evidence is None or context.generate is None:
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    requested = parse_generate_request(context.parameters)
    failed = False
    total = len(requested)
    await context.report(10)
    for index, (section_number, expected_revision) in enumerate(requested):
        await context.check_cancelled()
        outcome = await generate_one_section(
            context,
            section_number,
            expected_revision,
        )
        if outcome == GenerationAttemptStatus.FAILED.value:
            failed = True
        if total:
            await context.report(10 + int(80 * (index + 1) / total))
    if failed:
        raise GenerateSectionError
    await context.report(100)


def bind_generate_stores(context: JobContext, session: object, chroma_index: ChromaIndex) -> None:
    """Attach tenant-scoped stores for one database session."""

    context.evidence = EvidenceIndex(EvidenceChunkRepository(session), chroma_index)  # type: ignore[arg-type]
    context.generate = SimpleNamespace(
        sections=M11SectionStore(session),  # type: ignore[arg-type]
        memory=ConversationMemoryStore(session),  # type: ignore[arg-type]
        attempts=SectionGenerationAttemptRepository(session),  # type: ignore[arg-type]
    )


async def run_generate_sections_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
) -> None:
    """Load, generate, and save each section without holding SQL across chat."""

    if not isinstance(context.gateway, ProviderGateway):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    requested = parse_generate_request(context.parameters)
    failed = False
    total = len(requested)
    await context.report(10)
    for index, (section_number, expected_revision) in enumerate(requested):
        await context.check_cancelled()
        outcome = await _run_one_section_job(
            context,
            runtime,
            chroma_index,
            section_number,
            expected_revision,
        )
        if outcome == GenerationAttemptStatus.FAILED.value:
            failed = True
        if total:
            await context.report(10 + int(80 * (index + 1) / total))
    if failed:
        raise GenerateSectionError
    await context.report(100)


async def _run_one_section_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
    section_number: str,
    expected_revision: int,
) -> str:
    settings = WorkerSettings()
    async with runtime.transaction() as session:
        bind_generate_stores(context, session, chroma_index)
        record = await context.generate.sections.get_scoped(  # type: ignore[union-attr]
            context.organization_id,
            context.conversation_id,
            section_number,
        )
        if record is None:
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.FAILED.value,
                error_code=GenerationErrorCode.MISSING_SECTION.value,
            )
            return GenerationAttemptStatus.FAILED.value
        if record.status == M11_SECTION_DONE_STATUS:
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.SKIPPED.value,
            )
            return GenerationAttemptStatus.SKIPPED.value
        if record.current_revision != expected_revision:
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.SKIPPED.value,
                error_code=GenerationErrorCode.REVISION_CONFLICT.value,
            )
            return GenerationAttemptStatus.SKIPPED.value
        turns = await context.generate.memory.recent(  # type: ignore[union-attr]
            context.organization_id,
            context.conversation_id,
            GENERATE_MEMORY_TURN_LIMIT,
        )
        query = record.title
        if record.instructions.strip():
            query = f"{record.title}\n{record.instructions}"
        title = record.title
        instructions = record.instructions
        loaded_number = record.section_number
    try:
        async with runtime.transaction() as session:
            bind_generate_stores(context, session, chroma_index)
            retriever = ConversationRetriever(
                context.gateway,
                context.evidence,  # type: ignore[arg-type]
                settings,
            )
            retrieved = await retriever.retrieve(
                organization_id=context.organization_id,
                conversation_id=context.conversation_id,
                query=query,
                job_id=context.job_id,
                account_id=context.account_id,
                k=settings.retrieve_k,
            )
        messages = section_generation_messages(
            section_number=loaded_number,
            title=title,
            instructions=instructions,
            trial_passages=[
                chunk.text
                for chunk in retrieved
                if chunk.source_kind == EVIDENCE_SOURCE_TRIAL_DATA
            ],
            evidence=list(retrieved),
            memory=list(turns),
        )
        prompt = "\n\n".join(message.content for message in messages)
        completed = await context.gateway.complete(
            ChatRequest(
                messages=messages,
                model=settings.chat_model,
                organization_id=context.organization_id,
                conversation_id=context.conversation_id,
                job_id=context.job_id,
                account_id=context.account_id,
                idempotency_key=(
                    f"{context.job_id}:{context.attempt}:generate:{section_number}"
                ),
                thinking=False,
            )
        )
    except _PROVIDER_ERRORS:
        async with runtime.transaction() as session:
            bind_generate_stores(context, session, chroma_index)
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.FAILED.value,
                error_code=GenerationErrorCode.PROVIDER_FAILED.value,
            )
        return GenerationAttemptStatus.FAILED.value
    allowed = {chunk.id for chunk in retrieved}
    cleaned = apply_citations(completed.text, allowed).strip()
    if not cleaned:
        async with runtime.transaction() as session:
            bind_generate_stores(context, session, chroma_index)
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.FAILED.value,
                model=completed.model,
                prompt=prompt,
                error_code=GenerationErrorCode.EMPTY_OUTPUT.value,
            )
        return GenerationAttemptStatus.FAILED.value
    async with runtime.transaction() as session:
        bind_generate_stores(context, session, chroma_index)
        saved = await context.generate.sections.revise_draft(  # type: ignore[union-attr]
            context.organization_id,
            context.conversation_id,
            section_number,
            expected_revision=expected_revision,
            content=cleaned,
            author_account_id=context.account_id,
            now=datetime.now(UTC),
        )
        if not saved:
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.FAILED.value,
                model=completed.model,
                prompt=prompt,
                content=cleaned,
                error_code=GenerationErrorCode.REVISION_CONFLICT.value,
            )
            return GenerationAttemptStatus.FAILED.value
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.SUCCEEDED.value,
            model=completed.model,
            prompt=prompt,
            content=cleaned,
            citation_ids=[str(chunk_id) for chunk_id in parse_cite_ids(cleaned)],
        )
    return GenerationAttemptStatus.SUCCEEDED.value
