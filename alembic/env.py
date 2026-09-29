from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.models.base import Base
from app.core.settings import settings
from app.models.reserved import include_object

# Every model module must be imported here, not just the ones that happen to be
# needed. `target_metadata` is `Base.metadata`, and a model that nobody imports
# never registers its table on it. Autogenerate then sees a table in the database
# that is missing from the models and emits `drop_table` for it, so a forgotten
# import is a destructive migration rather than a cosmetic one.
#
# Until 2026-09-27 this file imported only `fsm_user` and `token_blacklist`, so
# `target_metadata` described a two-table database. Measured against a database
# built from deploy/schema.sql, autogenerate then emitted `remove_table` for 20 of
# the 23 live tables: everything except the two it knew about and alembic_version.
# See TICKET-019.
#
# Guarded by tests/test_alembic_env.py.
import app.models.audit_mixin
import app.models.base
import app.models.cancellation
import app.models.fsm_user
import app.models.maintenance
import app.models.master
import app.models.photo
import app.models.registry
import app.models.reserved
import app.models.ticket
import app.models.token_blacklist
import app.models.upload
import app.models.worksheet

config = context.config

config.set_main_option("sqlalchemy.url", settings.pg_dsn)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
