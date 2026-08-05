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
from trialscribe_user.models.invitation import Invitation
from trialscribe_user.models.membership import Membership
from trialscribe_user.models.organization import Organization
from trialscribe_user.repositories.identities import (
    IdentityRepository,
    OrganizationIdentity,
)
from trialscribe_user.repositories.invitations import InvitationRepository
from trialscribe_user.repositories.memberships import MembershipRepository
from trialscribe_user.repositories.organizations import OrganizationRepository
from trialscribe_user.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationCreatedResponse,
    InvitationResponse,
)
from trialscribe_user.schemas.identity import (
    IdentityResolutionRequest,
    OrganizationIdentitySummary,
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
from trialscribe_user.services.directory import IdentityDirectoryService
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


def _identity_response(identity: OrganizationIdentity) -> OrganizationIdentitySummary:
    return OrganizationIdentitySummary(
        account_id=identity.account_id,
        email=identity.email,
        is_active=identity.is_active,
    )


def _required_identity(
    identities: dict[UUID, OrganizationIdentity],
    account_id: UUID,
) -> OrganizationIdentity:
    identity = identities.get(account_id)
    if identity is None:
        raise RuntimeError("required organization identity is unavailable")
    return identity


def _membership_response(
    membership: Membership,
    identities: dict[UUID, OrganizationIdentity],
) -> MembershipResponse:
    return MembershipResponse(
        id=membership.id,
        organization_id=membership.organization_id,
        account_id=membership.account_id,
        identity=_identity_response(
            _required_identity(identities, membership.account_id)
        ),
        role=membership.role,
        created_at=membership.created_at,
    )


def _invitation_response(
    invitation: Invitation,
    identities: dict[UUID, OrganizationIdentity],
) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        organization_id=invitation.organization_id,
        email=invitation.email,
        role=invitation.role,
        invited_by_account_id=invitation.invited_by_account_id,
        invited_by=_identity_response(
            _required_identity(identities, invitation.invited_by_account_id)
        ),
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
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
                IdentityRepository(session),
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
            identity_repository = IdentityRepository(session)
            identities = await identity_repository.resolve_many(
                organization_id,
                [item.account_id for item in memberships],
            )
    except Exception as error:
        raise _translate_service_error(error) from None
    try:
        return [_membership_response(item, identities) for item in memberships]
    except Exception as error:
        raise _translate_service_error(error) from None


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
            identities = await IdentityRepository(session).resolve(
                organization_id,
                [membership.account_id],
            )
    except Exception as error:
        raise _translate_service_error(error) from None
    return _membership_response(membership, identities)


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
                IdentityRepository(session),
            ).create_invitation(account_id, organization_id, body.email, body.role, now)
            identities = await IdentityRepository(session).resolve(
                organization_id,
                [invitation.invited_by_account_id],
            )
    except Exception as error:
        raise _translate_service_error(error) from None
    return InvitationCreatedResponse(
        **_invitation_response(invitation, identities).model_dump(),
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
            identities = await IdentityRepository(session).resolve_many(
                organization_id,
                [item.invited_by_account_id for item in invitations],
            )
    except Exception as error:
        raise _translate_service_error(error) from None
    try:
        return [_invitation_response(item, identities) for item in invitations]
    except Exception as error:
        raise _translate_service_error(error) from None


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
                IdentityRepository(session),
            ).accept_invitation(body.token, account_id, now)
            identities = await IdentityRepository(session).resolve(
                membership.organization_id,
                [membership.account_id],
            )
    except Exception as error:
        raise _translate_service_error(error) from None
    return _membership_response(membership, identities)


@router.post(
    "/v1/organizations/{organization_id}/identity-summaries/resolve",
    response_model=list[OrganizationIdentitySummary],
)
async def resolve_identities(
    organization_id: UUID,
    body: IdentityResolutionRequest,
    account_id: Annotated[UUID, Depends(get_current_account_id)],
    database: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> list[OrganizationIdentitySummary]:
    try:
        async with database.transaction() as session:
            identities = await IdentityDirectoryService(
                MembershipRepository(session),
                IdentityRepository(session),
            ).resolve(account_id, organization_id, body.account_ids)
    except Exception as error:
        raise _translate_service_error(error) from None
    return [
        _identity_response(identities[item])
        for item in body.account_ids
        if item in identities
    ]
