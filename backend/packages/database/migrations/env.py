"""Alembic environment for the shared TrialScribe database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from trialscribe_db.base import Base
from trialscribe_db.config import DatabaseSettings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def configure_context(connection: Connection | None = None, *, url: str | None = None) -> None:
    """Apply the shared comparison and transaction settings."""

    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else None,
    )


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""

    settings = DatabaseSettings()
    configure_context(url=settings.connection_url())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through a short-lived synchronous Psycopg connection."""

    settings = DatabaseSettings()
    connectable = create_engine(settings.connection_url(), poolclass=NullPool)
    try:
        with connectable.begin() as connection:
            connection.execute(text("SET TIME ZONE 'UTC'"))
            configure_context(connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
