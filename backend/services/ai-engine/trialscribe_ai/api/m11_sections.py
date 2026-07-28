"""HTTP routes for conversation-scoped ICH M11 section workspaces."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_ai.api.dependencies import (
    get_current_account_id,
    get_current_organization_id,
    get_database_runtime,
    get_now,
)
from trialscribe_ai.config.m11_catalog import (
    M11_CATALOG_VERSION,
    M11_SECTION_CATALOG,
)
from trialscribe_ai.repositories.conversations import ConversationRepository
from trialscribe_ai.repositories.m11_section_revisions import (
    M11SectionRevisionRepository,
)
from trialscribe_ai.repositories.m11_sections import M11SectionRepository
from trialscribe_ai.schemas.m11_section import (
    M11CatalogResponse,
    M11CatalogSectionResponse,
    M11RevisionPageQuery,
    M11SectionResponse,
    M11SectionReviseRequest,
    M11SectionRevisionPageResponse,
    M11SectionRevisionResponse,
    M11SectionTransitionRequest,
    M11SectionWorkspaceResponse,
)
from trialscribe_ai.services.m11_sections import M11SectionService

router = APIRouter(tags=["m11-sections"])

AccountId = Annotated[UUID, Depends(get_current_account_id)]
OrganizationId = Annotated[UUID, Depends(get_current_organization_id)]
Runtime = Annotated[DatabaseRuntime, Depends(get_database_runtime)]
Now = Annotated[datetime, Depends(get_now)]


def _service(runtime_session: AsyncSession) -> M11SectionService:
    return M11SectionService(
        ConversationRepository(runtime_session),
        M11SectionRepository(runtime_session),
        M11SectionRevisionRepository(runtime_session),
    )


def _section_response(section: object) -> M11SectionResponse:
    return M11SectionResponse.model_validate(section)


def _workspace_response(sections: list[object]) -> M11SectionWorkspaceResponse:
    return M11SectionWorkspaceResponse(
        catalog_version=M11_CATALOG_VERSION,
        items=[_section_response(section) for section in sections],
    )


@router.get("/m11/sections/catalog", response_model=M11CatalogResponse)
async def get_m11_catalog() -> M11CatalogResponse:
    return M11CatalogResponse(
        version=M11_CATALOG_VERSION,
        items=[
            M11CatalogSectionResponse(
                number=definition.number,
                title=definition.title,
                position=definition.position,
            )
            for definition in M11_SECTION_CATALOG
        ],
    )


@router.put(
    "/conversations/{conversation_id}/m11-sections",
    response_model=M11SectionWorkspaceResponse,
)
async def initialize_m11_workspace(
    conversation_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> M11SectionWorkspaceResponse:
    async with runtime.transaction() as session:
        sections = await _service(session).initialize_workspace(
            organization_id,
            account_id,
            conversation_id,
        )
    return _workspace_response(sections)


@router.get(
    "/conversations/{conversation_id}/m11-sections",
    response_model=M11SectionWorkspaceResponse,
)
async def list_m11_sections(
    conversation_id: UUID,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> M11SectionWorkspaceResponse:
    async with runtime.transaction() as session:
        sections = await _service(session).list_sections(
            organization_id,
            account_id,
            conversation_id,
        )
    return _workspace_response(sections)


@router.get(
    "/conversations/{conversation_id}/m11-sections/{section_number}",
    response_model=M11SectionResponse,
)
async def get_m11_section(
    conversation_id: UUID,
    section_number: str,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> M11SectionResponse:
    async with runtime.transaction() as session:
        section = await _service(session).get_section(
            organization_id,
            account_id,
            conversation_id,
            section_number,
        )
    return _section_response(section)


@router.patch(
    "/conversations/{conversation_id}/m11-sections/{section_number}",
    response_model=M11SectionResponse,
)
async def revise_m11_section(
    conversation_id: UUID,
    section_number: str,
    body: M11SectionReviseRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    now: Now,
) -> M11SectionResponse:
    async with runtime.transaction() as session:
        section = await _service(session).revise_section(
            organization_id,
            account_id,
            conversation_id,
            section_number,
            expected_revision=body.expected_revision,
            instructions=body.instructions,
            content=body.content,
            now=now,
        )
    return _section_response(section)


@router.post(
    "/conversations/{conversation_id}/m11-sections/{section_number}/done",
    response_model=M11SectionResponse,
)
async def mark_m11_section_done(
    conversation_id: UUID,
    section_number: str,
    body: M11SectionTransitionRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    now: Now,
) -> M11SectionResponse:
    async with runtime.transaction() as session:
        section = await _service(session).mark_done(
            organization_id,
            account_id,
            conversation_id,
            section_number,
            expected_revision=body.expected_revision,
            now=now,
        )
    return _section_response(section)


@router.post(
    "/conversations/{conversation_id}/m11-sections/{section_number}/reopen",
    response_model=M11SectionResponse,
)
async def reopen_m11_section(
    conversation_id: UUID,
    section_number: str,
    body: M11SectionTransitionRequest,
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
    now: Now,
) -> M11SectionResponse:
    async with runtime.transaction() as session:
        section = await _service(session).reopen(
            organization_id,
            account_id,
            conversation_id,
            section_number,
            expected_revision=body.expected_revision,
            now=now,
        )
    return _section_response(section)


@router.get(
    "/conversations/{conversation_id}/m11-sections/{section_number}/revisions",
    response_model=M11SectionRevisionPageResponse,
)
async def list_m11_section_revisions(
    conversation_id: UUID,
    section_number: str,
    query: Annotated[M11RevisionPageQuery, Depends()],
    account_id: AccountId,
    organization_id: OrganizationId,
    runtime: Runtime,
) -> M11SectionRevisionPageResponse:
    async with runtime.transaction() as session:
        revisions, next_after_revision = await _service(session).list_revisions(
            organization_id,
            account_id,
            conversation_id,
            section_number,
            after_revision=query.after_revision,
            limit=query.limit,
        )
    return M11SectionRevisionPageResponse(
        items=[
            M11SectionRevisionResponse.model_validate(revision)
            for revision in revisions
        ],
        next_after_revision=next_after_revision,
    )
