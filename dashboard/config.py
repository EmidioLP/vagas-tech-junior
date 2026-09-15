"""Conexao do dashboard: a mesma configuracao do projeto, sempre somente leitura.

A URL sai de `api.database.database_url`, que le DATABASE_URL na ordem ambiente >
`.env.local` > `.env`. Nada de segredo no codigo nem em `st.secrets`.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from api.database import database_url

# Destino alternativo (URL ou arquivo SQLite) para uso local e testes. Vence a
# DATABASE_URL, como o `--db` da CLI.
VARIAVEL_DESTINO = "DASHBOARD_DB"

# A coleta roda no maximo uma vez por dia: 10 minutos de cache bastam.
TTL_SEGUNDOS = 600


def destino_configurado() -> str | None:
    return (os.environ.get(VARIAVEL_DESTINO) or "").strip() or None


def criar_engine(destino: str | Path | None = None) -> Engine:
    """Engine que so le. Sem destino nem DATABASE_URL: `ConfiguracaoError`."""
    url = database_url(destino if destino is not None else destino_configurado())

    if url.startswith("sqlite"):
        engine = create_engine(url)

        @event.listens_for(engine, "connect")
        def _somente_leitura(conexao, _registro):
            conexao.execute("PRAGMA query_only = ON")

        return engine

    # O psycopg abre cada transacao como READ ONLY. Funciona atras do pooler do
    # Neon, que opera em modo transacao e nao preserva configuracao de sessao.
    return create_engine(url, pool_pre_ping=True).execution_options(postgresql_readonly=True)
