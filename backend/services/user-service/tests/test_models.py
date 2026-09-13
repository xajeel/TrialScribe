from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from trialscribe_user.models.identity import OrganizationIdentityLink
from trialscribe_user.models.invitation import Invitation
from trialscribe_user.models.membership import Membership
from trialscribe_user.models.organization import Organization


def named_constraints(
    model: type[Organization | Membership | Invitation | OrganizationIdentityLink],
) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name is not None
    }


def foreign_keys(
    model: type[Membership | Invitation | OrganizationIdentityLink],
) -> dict[str, tuple[str, str | None]]:
    return {
        constraint.name: (
            next(iter(constraint.elements)).target_fullname,
            constraint.ondelete,
        )
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name is not None
    }


def test_organization_is_uuid_identified_with_a_bounded_trimmed_name() -> None:
    columns = Organization.__table__.columns

    assert Organization.__table__.schema == "trialscribe"
    assert columns.id.primary_key is True
    assert columns.name.nullable is False
    assert columns.name.type.length == 120
    assert "ck_organizations_name_length" in named_constraints(Organization)
    assert not any(constraint.name.startswith("uq_") for constraint in Organization.__table__.constraints if constraint.name)


def test_membership_is_unique_and_scoped_to_accounts_and_organizations() -> None:
    columns = Membership.__table__.columns
    constraints = named_constraints(Membership)

    assert columns.organization_id.nullable is False
    assert columns.account_id.nullable is False
    assert columns.role.nullable is False
    assert "ck_organization_memberships_role" in constraints
    assert "uq_organization_memberships_organization_id_account_id" in constraints
    assert {index.name for index in Membership.__table__.indexes} == {
        "ix_organization_memberships_account_id",
        "ix_organization_memberships_organization_id",
    }
    assert foreign_keys(Membership) == {
        "fk_organization_memberships_account_id_accounts": (
            "trialscribe.accounts.id",
            "CASCADE",
        ),
        "fk_organization_memberships_organization_id_organizations": (
            "trialscribe.organizations.id",
            "CASCADE",
        ),
    }
    assert next(iter(columns.account_id.foreign_keys)).use_alter is True


def test_invitation_stores_only_hash_and_single_pending_email_index() -> None:
    columns = Invitation.__table__.columns
    indexes = {index.name: index for index in Invitation.__table__.indexes}

    assert columns.email.type.length == 320
    assert columns.token_hash.type.length == 64
    assert columns.expires_at.type.timezone is True
    assert columns.accepted_at.nullable is True
    assert columns.revoked_at.nullable is True
    assert "ck_organization_invitations_role" in named_constraints(Invitation)
    assert "uq_organization_invitations_token_hash" in named_constraints(Invitation)
    pending = indexes["uq_organization_invitations_pending_email"]
    assert pending.unique is True
    assert str(pending.dialect_options["postgresql"]["where"]) == (
        "accepted_at IS NULL AND revoked_at IS NULL"
    )
    assert "token" not in columns
    assert "accept_url" not in columns
    assert next(iter(columns.invited_by_account_id.foreign_keys)).use_alter is True


def test_identity_link_is_unique_scoped_and_contains_no_account_data() -> None:
    columns = OrganizationIdentityLink.__table__.columns

    assert columns.id.primary_key is True
    assert columns.organization_id.nullable is False
    assert columns.account_id.nullable is False
    assert "email" not in columns
    assert "is_active" not in columns
    assert (
        "uq_organization_identity_links_organization_id_account_id"
        in named_constraints(OrganizationIdentityLink)
    )
    assert {index.name for index in OrganizationIdentityLink.__table__.indexes} == {
        "ix_organization_identity_links_account_id",
        "ix_organization_identity_links_organization_id",
    }
    assert foreign_keys(OrganizationIdentityLink) == {
        "fk_organization_identity_links_account_id_accounts": (
            "trialscribe.accounts.id",
            "CASCADE",
        ),
        "fk_organization_identity_links_organization_id_organizations": (
            "trialscribe.organizations.id",
            "CASCADE",
        ),
    }
    assert next(iter(columns.account_id.foreign_keys)).use_alter is True


def test_every_organization_foreign_key_is_deterministically_named() -> None:
    assert foreign_keys(Invitation) == {
        "fk_organization_invitations_invited_by_account_id_accounts": (
            "trialscribe.accounts.id",
            "CASCADE",
        ),
        "fk_organization_invitations_organization_id_organizations": (
            "trialscribe.organizations.id",
            "CASCADE",
        ),
    }
    assert all(
        isinstance(constraint, (CheckConstraint, UniqueConstraint))
        for table in (
            Organization.__table__,
            Membership.__table__,
            Invitation.__table__,
            OrganizationIdentityLink.__table__,
        )
        for constraint in table.constraints
        if constraint.name and constraint.name.startswith(("ck_", "uq_"))
    )
