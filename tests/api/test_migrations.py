"""Alembic: configuracao sem segredo, metadata descoberta e baseline reversivel."""

from __future__ import annotations

import configparser
import io
import re

import pytest

pytest.importorskip("alembic", reason="Alembic não instalado; testes de migration pulados.")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

import api.models  # noqa: E402,F401  -- registra as tabelas em Base.metadata
from api.database import Base  # noqa: E402
from scraper.config import PROJECT_ROOT, ConfiguracaoError  # noqa: E402

INI = PROJECT_ROOT / "alembic.ini"
TABELAS = {"vagas", "tecnologias", "vaga_tecnologia"}


def _config(url: str | None = None, saida: io.StringIO | None = None) -> Config:
    cfg = Config(str(INI), output_buffer=saida)
    if url:
        cfg.attributes["database_url"] = url
    return cfg


def _sqlite(tmp_path, nome: str = "migracoes.db") -> str:
    return f"sqlite:///{(tmp_path / nome).as_posix()}"


def test_alembic_ini_nao_define_url():
    ini = configparser.RawConfigParser()
    ini.read(INI, encoding="utf-8")
    assert not ini.get("alembic", "sqlalchemy.url", fallback="").strip()


def test_migrations_nao_contem_credenciais():
    credencial = re.compile(r"://[^\s/'\"]+:[^\s@'\"]+@")
    arquivos = list((PROJECT_ROOT / "migrations").rglob("*.py"))
    assert arquivos
    for arquivo in arquivos:
        assert not credencial.search(arquivo.read_text(encoding="utf-8")), arquivo.name


def test_sem_url_falha_antes_de_conectar():
    with pytest.raises(ConfiguracaoError):
        command.upgrade(_config(saida=io.StringIO()), "head", sql=True)


def test_url_vem_da_configuracao_central(monkeypatch):
    """Modo --sql: gera o DDL do PostgreSQL sem conexao e sem vazar a senha."""
    monkeypatch.setenv(
        "DATABASE_URL_UNPOOLED",
        "postgresql://usuario:senha-ficticia@direto.exemplo.test/vagas",
    )
    saida = io.StringIO()
    command.upgrade(_config(saida=saida), "head", sql=True)
    sql = saida.getvalue()
    for tabela in TABELAS:
        assert f"CREATE TABLE {tabela}" in sql
    assert "senha-ficticia" not in sql


def test_baseline_sobe_confere_e_desce(tmp_path):
    url = _sqlite(tmp_path)
    cfg = _config(url)
    engine = create_engine(url)
    try:
        command.upgrade(cfg, "head")

        inspetor = inspect(engine)
        assert TABELAS <= set(inspetor.get_table_names())
        assert {i["name"] for i in inspetor.get_indexes("vagas")} >= {
            "ix_vagas_area", "ix_vagas_source", "ix_vagas_workplace_type",
        }
        assert "uq_vaga_source_external_id" in {
            u["name"] for u in inspetor.get_unique_constraints("vagas")
        }
        fks = inspetor.get_foreign_keys("vaga_tecnologia")
        assert {fk["referred_table"] for fk in fks} == {"vagas", "tecnologias"}
        assert all(fk["options"].get("ondelete") == "CASCADE" for fk in fks)

        command.check(cfg)  # modelos e migrations sem diferenca

        command.downgrade(cfg, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()


def test_banco_criado_por_create_all_aceita_stamp(tmp_path):
    """Caminho documentado para bancos legados: create_all -> stamp head -> check."""
    url = _sqlite(tmp_path, "legado.db")
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    cfg = _config(url)
    command.stamp(cfg, "head")
    command.check(cfg)
