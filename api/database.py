"""Conexao e sessao do SQLAlchemy.

O banco e configurado por uma unica variavel, DATABASE_URL, resolvida em
`scraper.config.obter_database_url` (ambiente > .env.local > .env). Sem ela, a
API e o importador falham com mensagem clara em vez de cair num banco padrao.

Um destino passado como argumento ainda vence a variavel. E o que os testes e o
`import_csv.py --db` usam, e aceita caminho de arquivo SQLite.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session

from scraper.config import obter_database_url

logger = logging.getLogger(__name__)


def _normalizar(url: str) -> str:
    """Ajusta prefixos de Postgres para o driver que o projeto instala.

    Provedores gerenciados (Render, Heroku, Railway) ainda entregam a URL com
    o prefixo historico `postgres://`, que o SQLAlchemy nao aceita mais.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _como_url(destino: str | Path) -> str:
    """Aceita tanto uma URL de banco quanto um caminho de arquivo SQLite."""
    texto = str(destino)
    if "://" in texto:
        return _normalizar(texto)
    return f"sqlite:///{Path(texto).as_posix()}"


def database_url(destino: str | Path | None = None) -> str:
    if destino is not None:
        return _como_url(destino)
    return _normalizar(obter_database_url())


def url_sem_senha(url: str) -> str:
    """URL segura para log: esconde a senha, que aparece na do Postgres."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover - URL malformada nao deve derrubar log
        return url


class Base(DeclarativeBase):
    pass


def make_engine(destino: str | Path | None = None):
    url = database_url(destino)
    opcoes: dict = {"future": True}

    if url.startswith("sqlite"):
        # check_same_thread: o uvicorn atende requisicoes em threads diferentes.
        opcoes["connect_args"] = {"check_same_thread": False}
        caminho = url.replace("sqlite:///", "")
        if caminho and caminho != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    else:
        # pool_pre_ping: no compose a API sobe junto com o banco, e a conexao
        # pode ter morrido enquanto o container do Postgres reiniciava.
        opcoes["pool_pre_ping"] = True

    return create_engine(url, **opcoes)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Engine da aplicacao, criado no primeiro uso.

    Criar no import exigiria DATABASE_URL ate de quem so importa o modulo
    passando um destino explicito (testes, `import_csv.py --db`).
    """
    return make_engine()


def init_db(bind=None) -> None:
    if bind is None:
        bind = get_engine()
        logger.info("Banco: %s", bind.url.render_as_string(hide_password=True))
    Base.metadata.create_all(bind=bind)


def get_db() -> Iterator[Session]:
    """Dependencia do FastAPI: uma sessao por requisicao."""
    db = Session(get_engine(), autoflush=False, expire_on_commit=False)
    try:
        yield db
    finally:
        db.close()
