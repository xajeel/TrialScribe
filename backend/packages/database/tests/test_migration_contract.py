from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = PACKAGE_ROOT / "migrations"


def migration_scripts() -> ScriptDirectory:
    config = Config(PACKAGE_ROOT / "alembic.ini")
    return ScriptDirectory.from_config(config)


def test_migration_history_is_linear_with_one_head() -> None:
    scripts = migration_scripts()
    revisions = list(scripts.walk_revisions(base="base", head="heads"))

    assert scripts.get_heads() == ["0015_m11_revision_actions"]
    assert [revision.revision for revision in revisions] == [
        "0015_m11_revision_actions",
        "0014_section_generation_attempts",
        "0013_evidence_chunks",
        "0012_provider_calls",
        "0011_event_outbox",
        "0010_jobs",
        "0009_processed_events",
        "0008_organization_identities",
        "0007_m11_sections",
        "0006_document_sources",
        "0005_conversation_workspaces",
        "0004_organization_rbac",
        "0003_auth_tables",
        "0002_create_trialscribe_schema",
        "0001_enable_vector",
    ]


def test_every_revision_has_upgrade_and_downgrade_contracts() -> None:
    for revision in migration_scripts().walk_revisions(base="base", head="heads"):
        assert callable(revision.module.upgrade)
        assert callable(revision.module.downgrade)


def test_revision_files_stay_in_versions_directory() -> None:
    assert list(MIGRATIONS.glob("[0-9]*.py")) == []
    assert sorted(path.name for path in (MIGRATIONS / "versions").glob("*.py")) == [
        "0001_enable_vector.py",
        "0002_create_trialscribe_schema.py",
        "0003_create_authentication_tables.py",
        "0004_create_organization_rbac_tables.py",
        "0005_create_conversation_workspace_tables.py",
        "0006_create_document_tables.py",
        "0007_create_m11_section_workspace_tables.py",
        "0008_create_organization_identity_links.py",
        "0009_create_processed_events_table.py",
        "0010_create_jobs_table.py",
        "0011_create_event_outbox_table.py",
        "0012_create_provider_calls_table.py",
        "0013_create_evidence_chunks_table.py",
        "0014_create_section_generation_attempts_table.py",
        "0015_extend_m11_revision_actions.py",
    ]


def test_migration_environment_uses_utc_and_model_comparisons() -> None:
    environment_source = (MIGRATIONS / "env.py").read_text()

    assert "SET TIME ZONE 'UTC'" in environment_source
    assert "compare_type=True" in environment_source
    assert "compare_server_default=True" in environment_source
    assert "sqlalchemy.url" not in (PACKAGE_ROOT / "alembic.ini").read_text()
