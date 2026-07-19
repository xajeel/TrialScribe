"""Versioned organization, membership, and invitation routes."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_user.api.dependencies import (
    get_current_account_id,
    get_database_runtime,
    get_now,
    get_settings,
)
from trialscribe_user.config import UserSettings
from trialscribe_user.models.membership import Membership
from trialscribe_user.models.organization import Organization
from trialscribe_user.repositories.invitations import InvitationRepository
from trialscribe_user.repositories.memberships import MembershipRepository
from trialscribe_user.repositories.organizations import OrganizationRepository
from trialscribe_user.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationCreatedResponse,
    InvitationResponse,
)
from trialscribe_user.schemas.organization import (
    MembershipResponse,
    MembershipRoleUpdateRequest,
    OrganizationCreateRequest,
    OrganizationResponse,
)
from trialscribe_user.services.authorization import (
    OrganizationNotFoundError,
    PermissionDeniedError,
)
from trialscribe_user.services.invitations import (
    InvalidInvitationError,
    InvalidInvitationInput,
    InvitationConflictError,
    InvitationService,
)
from trialscribe_user.services.organizations import (
    InvalidOrganizationInput,
    MembershipConflictError,
    OrganizationService,
)
from trialscribe_user.utils.constant import (
    INVALID_INVITATION_DETAIL,
    INVALID_ORGANIZATION_DETAIL,
    INVITATION_CONFLICT_DETAIL,
    MEMBERSHIP_CONFLICT_DETAIL,
    ORGANIZATION_NOT_FOUND_DETAIL,
    PERMISSION_DENIED_DETAIL,
    SERVICE_UNAVAILABLE_DETAIL,
)

router = APIRouter(tags=["organizations"])


def _organization_response(
    organization: Organization,
    membership: Membership,
) -> OrganizationResponse:
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        role=membership.role,
        created_at=organization.created_at,
    )


def _translate_service_error(error: Exception) -> HTTPException:
    if isinstance(error, OrganizationNotFoundError):
        return HTTPException(status_code=404, detail=ORGANIZATION_NOT_FOUND_DETAIL)
    if isinstance(error, PermissionDeniedError):
        return HTTPException(status_code=403, detail=PERMISSION_DENIED_DETAIL)
    if isinstance(error, MembershipConflictError):
        return HTTPException(status_code=409, detail=MEMBERSHIP_CONFLICT_DETAIL)
    if isinstance(error, InvitationConflictError):
        return HTTPException(status_code=409, detail=INVITATION_CONFLICT_DETAIL)
    if isinstance(error, InvalidOrganizationInput):
        return HTTPException(status_code=422, detail=INVALID_ORGANIZATION_DETAIL)
    if isinstance(error, (InvalidInvitationInput, InvalidInvitationError)):
        return HTTPException(status_code=422, detail=INVALID_INVITATION_DETAIL)
    return HTTPException(status_code=500, detail=SERVICE_UNAVAILABLE_DETAIL)


@router.post("/v1/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    body: OrganizationCreateRequest,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> OrganizationResponse:
    try:
        async with database.transaction() as session:
            organization, membership = await OrganizationService(
                OrganizationRepository(session),
                MembershipRepository(session),
            ).create_organization(account_id, body.name)
    except Exception as error:
        raise _translate_service_error(error) from None
    return _organization_response(organization, membership)


@router.get("/v1/organizations", response_model=list[OrganizationResponse])
async def list_organizations(
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> list[OrganizationResponse]:
    async with database.transaction() as session:
        records = await OrganizationService(
            OrganizationRepository(session),
            MembershipRepository(session),
        ).list_organizations(account_id)
    return [
        _organization_response(organization, membership)
        for organization, membership in records
    ]


@router.get(
    "/v1/organizations/{organization_id}",
    response_model=OrganizationResponse,
)
async def get_organization(
    organization_id: UUID,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> OrganizationResponse:
    try:
        async with database.transaction() as session:
            organization, membership = await OrganizationService(
                OrganizationRepository(session),
                MembershipRepository(session),
            ).get_organization(account_id, organization_id)
    except Exception as error:
        raise _translate_service_error(error) from None
    return _organization_response(organization, membership)


@router.get(
    "/v1/organizations/{organization_id}/members",
    response_model=list[MembershipResponse],
)
async def list_members(
    organization_id: UUID,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> list[MembershipResponse]:
    try:
        async with database.transaction() as session:
            memberships = await OrganizationService(
                OrganizationRepository(session),
                MembershipRepository(session),
            ).list_members(account_id, organization_id)
    except Exception as error:
        raise _translate_service_error(error) from None
    return [MembershipResponse.model_validate(item) for item in memberships]


@router.patch(
    "/v1/organizations/{organization_id}/members/{target_account_id}",
    response_model=MembershipResponse,
)
async def change_membership_role(
    organization_id: UUID,
    target_account_id: UUID,
    body: MembershipRoleUpdateRequest,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> MembershipResponse:
    try:
        async with database.transaction() as session:
            membership = await OrganizationService(
                OrganizationRepository(session),
                MembershipRepository(session),
            ).change_role(account_id, organization_id, target_account_id, body.role)
    except Exception as error:
        raise _translate_service_error(error) from None
    return MembershipResponse.model_validate(membership)


@router.delete(
    "/v1/organizations/{organization_id}/members/{target_account_id}",
    status_code=204,
)
async def remove_member(
    organization_id: UUID,
    target_account_id: UUID,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> Response:
    try:
        async with database.transaction() as session:
            await OrganizationService(
                OrganizationRepository(session),
                MembershipRepository(session),
            ).remove_member(account_id, organization_id, target_account_id)
    except Exception as error:
        raise _translate_service_error(error) from None
    return Response(status_code=204)


@router.post(
    "/v1/organizations/{organization_id}/invitations",
    response_model=InvitationCreatedResponse,
    status_code=201,
)
async def create_invitation(
    organization_id: UUID,
    body: InvitationCreateRequest,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[UserSettings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
) -> InvitationCreatedResponse:
    try:
        async with database.transaction() as session:
            invitation, accept_url = await InvitationService(
                InvitationRepository(session),
                MembershipRepository(session),
                settings,
            ).create_invitation(account_id, organization_id, body.email, body.role, now)
    except Exception as error:
        raise _translate_service_error(error) from None
    return InvitationCreatedResponse(
        **InvitationResponse.model_validate(invitation).model_dump(),
        accept_url=accept_url,
    )


@router.get(
    "/v1/organizations/{organization_id}/invitations",
    response_model=list[InvitationResponse],
)
async def list_invitations(
    organization_id: UUID,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[UserSettings, Depends(get_settings)],
) -> list[InvitationResponse]:
    try:
        async with database.transaction() as session:
            invitations = await InvitationService(
                InvitationRepository(session),
                MembershipRepository(session),
                settings,
            ).list_invitations(account_id, organization_id)
    except Exception as error:
        raise _translate_service_error(error) from None
    return [InvitationResponse.model_validate(item) for item in invitations]


@router.delete(
    "/v1/organizations/{organization_id}/invitations/{invitation_id}",
    status_code=204,
)
async def revoke_invitation(
    organization_id: UUID,
    invitation_id: UUID,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[UserSettings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    try:
        async with database.transaction() as session:
            await InvitationService(
                InvitationRepository(session),
                MembershipRepository(session),
                settings,
            ).revoke_invitation(
                account_id,
                organization_id,
                invitation_id,
                now,
            )
    except Exception as error:
        raise _translate_service_error(error) from None
    return Response(status_code=204)


@router.post(
    "/v1/organization-invitations/accept",
    response_model=MembershipResponse,
)
async def accept_invitation(
    body: InvitationAcceptRequest,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    settings: Annotated[UserSettings, Depends(get_settings)],
    now: Annotated[datetime, Depends(get_now)],
) -> MembershipResponse:
    try:
        async with database.transaction() as session:
            membership = await InvitationService(
                InvitationRepository(session),
                MembershipRepository(session),
                settings,
            ).accept_invitation(body.token, account_id, now)
    except Exception as error:
        raise _translate_service_error(error) from None
    return MembershipResponse.model_validate(membership)
