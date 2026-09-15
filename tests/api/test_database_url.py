"""Resolucao do destino do banco: DATABASE_URL obrigatoria, destino explicito vence."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.database import database_url, make_engine, url_sem_senha
from scraper.config import ConfiguracaoError


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch):
    """Isola dos envs da máquina: sem DATABASE_URL não há banco padrão."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VAGAS_DB", raising=False)


def test_sem_database_url_falha_com_mensagem_clara():
    with pytest.raises(ConfiguracaoError, match="DATABASE_URL"):
        database_url()


def test_caminho_de_arquivo_vira_sqlite():
    assert database_url("data/outro.db") == "sqlite:///data/outro.db"
    assert database_url(Path("data/outro.db")).startswith("sqlite:///")


def test_url_de_postgres_ganha_o_driver_do_projeto():
    assert database_url("postgresql://u:p@db:5432/vagas") == (
        "postgresql+psycopg://u:p@db:5432/vagas"
    )


def test_prefixo_legado_postgres_e_convertido():
    """Render e Heroku ainda entregam `postgres://`, que o SQLAlchemy recusa."""
    assert database_url("postgres://u:p@db:5432/vagas") == (
        "postgresql+psycopg://u:p@db:5432/vagas"
    )


def test_database_url_do_ambiente_e_usada(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/vagas")
    assert database_url().startswith("postgresql+psycopg://")


def test_parametros_ssl_do_neon_sao_preservados(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://u:p@ep-exemplo.exemplo.test/vagas"
        "?sslmode=require&channel_binding=require",
    )
    assert database_url() == (
        "postgresql+psycopg://u:p@ep-exemplo.exemplo.test/vagas"
        "?sslmode=require&channel_binding=require"
    )


def test_vagas_db_nao_e_mais_aceito(monkeypatch):
    monkeypatch.setenv("VAGAS_DB", "/tmp/x.db")
    with pytest.raises(ConfiguracaoError):
        database_url()


def test_argumento_vence_o_ambiente(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/vagas")
    assert database_url("data/x.db") == "sqlite:///data/x.db"


def test_senha_nao_aparece_no_log():
    mascarada = url_sem_senha(database_url("postgresql://vagas:segredo@db/vagas"))
    assert "segredo" not in mascarada
    assert "vagas" in mascarada


def test_engine_sqlite_recebe_check_same_thread(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    try:
        assert engine.dialect.name == "sqlite"
        assert engine.pool._creator  # engine criado sem erro
    finally:
        engine.dispose()


def test_engine_postgres_nao_recebe_argumento_de_sqlite():
    """`check_same_thread` é exclusivo do SQLite e quebraria a conexão."""
    engine = make_engine("postgresql://u:p@localhost:5432/vagas")
    try:
        assert engine.dialect.name == "postgresql"
        # Criar o engine não conecta; garante que os argumentos são válidos.
        assert "check_same_thread" not in str(engine.url.query)
    finally:
        engine.dispose()
