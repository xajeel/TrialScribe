"""User-service enums."""

from enum import StrEnum


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class OrganizationAction(StrEnum):
    READ = "read"
    INVITE_MEMBER = "invite_member"
    INVITE_ADMIN = "invite_admin"
    REVOKE_MEMBER_INVITATION = "revoke_member_invitation"
    REVOKE_ADMIN_INVITATION = "revoke_admin_invitation"
    REMOVE_MEMBER = "remove_member"
    REMOVE_PRIVILEGED = "remove_privileged"
    CHANGE_ROLES = "change_roles"
