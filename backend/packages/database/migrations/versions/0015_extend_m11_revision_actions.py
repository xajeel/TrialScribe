"""Allow generated and restored revision actions, and invalid_selection."""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_m11_revision_actions"
down_revision: str | None = "0014_section_generation_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_m11_section_revisions_action_status"),
        "m11_section_revisions",
        schema="trialscribe",
    )
    op.drop_constraint(
        op.f("ck_m11_section_revisions_action"),
        "m11_section_revisions",
        schema="trialscribe",
    )
    op.create_check_constraint(
        op.f("ck_m11_section_revisions_action"),
        "m11_section_revisions",
        "action IN ('revised', 'done', 'reopened', 'generated', 'restored')",
        schema="trialscribe",
    )
    op.create_check_constraint(
        op.f("ck_m11_section_revisions_action_status"),
        "m11_section_revisions",
        "(action = 'done' AND status = 'done') "
        "OR (action IN ('revised', 'reopened', 'generated', 'restored') "
        "AND status = 'draft')",
        schema="trialscribe",
    )
    op.drop_constraint(
        op.f("ck_section_generation_attempts_error_code"),
        "section_generation_attempts",
        schema="trialscribe",
    )
    op.create_check_constraint(
        op.f("ck_section_generation_attempts_error_code"),
        "section_generation_attempts",
        "error_code IS NULL OR error_code IN ("
        "'missing_section', 'empty_output', 'provider_failed', "
        "'revision_conflict', 'invalid_selection')",
        schema="trialscribe",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_section_generation_attempts_error_code"),
        "section_generation_attempts",
        schema="trialscribe",
    )
    op.create_check_constraint(
        op.f("ck_section_generation_attempts_error_code"),
        "section_generation_attempts",
        "error_code IS NULL OR error_code IN ("
        "'missing_section', 'empty_output', 'provider_failed', 'revision_conflict')",
        schema="trialscribe",
    )
    op.drop_constraint(
        op.f("ck_m11_section_revisions_action_status"),
        "m11_section_revisions",
        schema="trialscribe",
    )
    op.drop_constraint(
        op.f("ck_m11_section_revisions_action"),
        "m11_section_revisions",
        schema="trialscribe",
    )
    op.create_check_constraint(
        op.f("ck_m11_section_revisions_action"),
        "m11_section_revisions",
        "action IN ('revised', 'done', 'reopened')",
        schema="trialscribe",
    )
    op.create_check_constraint(
        op.f("ck_m11_section_revisions_action_status"),
        "m11_section_revisions",
        "(action = 'done' AND status = 'done') "
        "OR (action IN ('revised', 'reopened') AND status = 'draft')",
        schema="trialscribe",
    )
