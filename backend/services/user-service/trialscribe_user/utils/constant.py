"""Stable user-service constants."""

from trialscribe_user.utils.enum import MembershipRole, OrganizationAction

APP_TITLE = "TrialScribe User"
APP_VERSION = "0.1.0"
SERVICE_NAME = "user-service"
LIVENESS_STATUS = "ok"
READINESS_STATUS = "ready"

ACCESS_TOKEN_ALGORITHM = "EdDSA"
ACCESS_TOKEN_REQUIRED_CLAIMS = (
    "sub",
    "iss",
    "aud",
    "iat",
    "nbf",
    "exp",
    "jti",
    "type",
)

INVALID_AUTHENTICATION_DETAIL = "Invalid authentication credentials"
ORGANIZATION_NOT_FOUND_DETAIL = "Organization not found"
PERMISSION_DENIED_DETAIL = "Organization permission denied"
MEMBERSHIP_CONFLICT_DETAIL = "Membership change conflicts with organization state"
INVITATION_CONFLICT_DETAIL = "Invitation conflicts with organization state"
INVALID_ORGANIZATION_DETAIL = "Invalid organization input"
INVALID_INVITATION_DETAIL = "Invalid organization invitation"
SERVICE_UNAVAILABLE_DETAIL = "Service unavailable"

ORGANIZATION_PERMISSIONS: dict[MembershipRole, frozenset[OrganizationAction]] = {
    MembershipRole.OWNER: frozenset(OrganizationAction),
    MembershipRole.ADMIN: frozenset(
        {
            OrganizationAction.READ,
            OrganizationAction.INVITE_MEMBER,
            OrganizationAction.REVOKE_MEMBER_INVITATION,
            OrganizationAction.REMOVE_MEMBER,
        }
    ),
    MembershipRole.MEMBER: frozenset({OrganizationAction.READ}),
}
