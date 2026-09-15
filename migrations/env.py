"""Ambiente do Alembic.

A URL nunca vem do alembic.ini: sai de `scraper.config.obter_url_migrations`,
que prefere a conexao direta do Neon. Testes injetam uma URL propria em
`config.attributes["database_url"]`.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

import api.models  # noqa: F401  -- registra as tabelas em Base.metadata
from api.database import Base, database_url, url_sem_senha
from scraper.config import obter_url_migrations

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

logger = logging.getLogger("alembic.env")
target_metadata = Base.metadata


def _url() -> str:
    return database_url(config.attributes.get("database_url") or obter_url_migrations())


def run_migrations_offline() -> None:
    """Gera o SQL (`alembic upgrade head --sql`) sem conectar ao banco."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    logger.info("Banco: %s", url_sem_senha(url))
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                # SQLite nao tem ALTER completo; so e usado em testes locais.
                render_as_batch=connection.dialect.name == "sqlite",
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
