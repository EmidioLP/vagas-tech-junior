"""Consultas do dashboard contra o schema das migrations (SQLite), sem rede."""

from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.database import make_engine  # noqa: E402
from api.models import CollectionRun, JobRecord  # noqa: E402
from dashboard import config, consultas  # noqa: E402
from scraper.config import PROJECT_ROOT, ConfiguracaoError  # noqa: E402

INICIO = datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc)


def _execucao(dias: float = 0, **campos) -> CollectionRun:
    momento = INICIO + timedelta(days=dias)
    valores = dict(started_at=momento, finished_at=momento, triggered_by="schedule",
                   status="success", full_scope=True, jobs_count=10, failures=0, summary={})
    valores.update(campos)
    return CollectionRun(**valores)


def _vaga(externo: str, ativa: bool = True) -> JobRecord:
    return JobRecord(source="gupy", external_id=externo, first_seen_at=INICIO,
                     last_seen_at=INICIO, is_active=ativa)


def _gravar(banco, *objetos) -> None:
    """Grava com o engine normal: o do dashboard nao escreve."""
    engine = make_engine(banco)
    try:
        with Session(engine) as db, db.begin():
            db.add_all(objetos)
    finally:
        engine.dispose()


@pytest.fixture
def leitor(banco_historico):
    engine = config.criar_engine(banco_historico)
    yield engine
    engine.dispose()


def test_banco_sem_coleta_devolve_estado_vazio(leitor):
    resumo = consultas.resumo_geral(leitor)
    assert resumo == consultas.ResumoGeral(None, None, None, 0)
    assert resumo.vazio


def test_ultima_coleta_segue_a_regra_da_guarda(banco_historico, leitor):
    _gravar(
        banco_historico,
        _execucao(0, status="success"),
        _execucao(2, status="partial", jobs_count=8),
        _execucao(4, status="failed", jobs_count=0),
        _execucao(5, status="skipped", jobs_count=0),
        _execucao(6, status="success", full_scope=False, triggered_by="manual"),
    )

    coleta = consultas.ultima_coleta(leitor)
    assert coleta == consultas.Coleta(INICIO + timedelta(days=2), "partial", 8)

    execucao = consultas.ultima_execucao(leitor)
    assert execucao == consultas.Execucao(INICIO + timedelta(days=6), "success", "manual")


def test_proxima_coleta_e_a_mais_recente_informada(banco_historico, leitor):
    _gravar(
        banco_historico,
        _execucao(0, next_run_on=date(2026, 9, 17)),
        _execucao(1, status="skipped", next_run_on=date(2026, 9, 17)),
        _execucao(2, next_run_on=date(2026, 9, 19)),
        _execucao(3, triggered_by="manual"),  # forcada sem X: nao informa
    )
    assert consultas.proxima_coleta(leitor) == date(2026, 9, 19)


def test_vagas_ativas_ignoram_as_encerradas(banco_historico, leitor):
    _gravar(banco_historico, _vaga("1"), _vaga("2"), _vaga("3"),
            _vaga("4", ativa=False), _vaga("5", ativa=False))
    assert consultas.vagas_ativas(leitor) == 3


def test_engine_do_dashboard_nao_grava(leitor):
    with leitor.connect() as conexao, pytest.raises(OperationalError):
        conexao.execute(text(
            "INSERT INTO jobs (source, external_id, first_seen_at, last_seen_at) "
            "VALUES ('gupy', '1', '2026-09-15', '2026-09-15')"
        ))


def test_banco_sem_schema_vira_dados_indisponiveis_sem_caminho(tmp_path):
    arquivo = tmp_path / "vazio.db"
    arquivo.touch()
    engine = config.criar_engine(arquivo)
    try:
        with pytest.raises(consultas.DadosIndisponiveis) as erro:
            consultas.resumo_geral(engine)
    finally:
        engine.dispose()

    mensagem = str(erro.value)
    assert "OperationalError" in mensagem
    assert "vazio.db" not in mensagem
    assert str(tmp_path) not in mensagem


def test_sem_database_url_e_erro_de_configuracao():
    with pytest.raises(ConfiguracaoError):
        config.criar_engine()


def test_dashboard_db_vence_database_url(monkeypatch, banco_historico):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:senha-ficticia@exemplo.test/vagas")
    monkeypatch.setenv("DASHBOARD_DB", str(banco_historico))
    engine = config.criar_engine()
    try:
        assert engine.dialect.name == "sqlite"
        assert consultas.resumo_geral(engine).vazio
    finally:
        engine.dispose()


def test_camada_de_dados_nao_puxa_fontes_nem_fastapi():
    """O deploy do dashboard (requirements-dashboard.txt) nao instala essas bibliotecas."""
    codigo = (
        "import sys; import dashboard.config, dashboard.consultas; "
        "print(','.join(m for m in ('requests', 'bs4', 'yaml', 'fastapi') if m in sys.modules))"
    )
    saida = subprocess.run([sys.executable, "-c", codigo], cwd=PROJECT_ROOT,
                           capture_output=True, text=True, check=True)
    assert saida.stdout.strip() == ""
