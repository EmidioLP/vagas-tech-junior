"""Frescor dos dados (`persistence/frescor.py`) e `/health/dados`."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import app
from api.database import get_db, make_engine
from api.models import CollectionRun
from persistence import frescor as regra

AGORA = datetime(2026, 9, 20, 9, 5, tzinfo=timezone.utc)


def _dias_atras(dias: int, hora: int = 9) -> datetime:
    return (AGORA - timedelta(days=dias)).replace(hour=hora)


def _avaliar(coleta_dias=1, execucao_dias=0, intervalo=2, status="success"):
    coleta = (_dias_atras(coleta_dias), status) if coleta_dias is not None else None
    execucao = (_dias_atras(execucao_dias), "skipped") if execucao_dias is not None else None
    return regra.avaliar(coleta, execucao, intervalo, date(2026, 9, 21), AGORA)


# --- regra pura -----------------------------------------------------------------


def test_coleta_recente_esta_em_dia():
    frescor = _avaliar()
    assert (frescor.estado, frescor.saudavel, frescor.com_problema) == ("em_dia", True, False)
    assert (frescor.dias_desde_ultima_coleta, frescor.limite_dias) == (1, 4)


def test_exatamente_no_limite_ainda_esta_em_dia():
    """X = 2: 4 dias sem coleta completa e o limite; 5 ja vence."""
    assert _avaliar(coleta_dias=4).estado == "em_dia"
    assert _avaliar(coleta_dias=5).estado == "vencido"


def test_dias_contados_por_data_utc_e_nao_por_horas():
    coleta = (datetime(2026, 9, 16, 23, 59, tzinfo=timezone.utc), "success")
    execucao = (datetime(2026, 9, 20, 0, 1, tzinfo=timezone.utc), "skipped")
    frescor = regra.avaliar(coleta, execucao, 2, None, AGORA)
    assert (frescor.dias_desde_ultima_coleta, frescor.estado) == (4, "em_dia")


def test_sem_coleta_completa():
    frescor = _avaliar(coleta_dias=None)
    assert (frescor.estado, frescor.com_problema) == ("sem_coleta", True)


def test_sem_intervalo_registrado_nao_tem_regua():
    frescor = _avaliar(coleta_dias=30, intervalo=None)
    assert (frescor.estado, frescor.com_problema) == ("sem_intervalo", False)


def test_coleta_parada_aparece_antes_de_o_dado_vencer():
    """Dado ainda dentro do limite, mas nenhuma execucao (nem pulada) ha 3 dias."""
    frescor = _avaliar(coleta_dias=3, execucao_dias=3)
    assert (frescor.estado, frescor.com_problema) == ("coleta_parada", True)
    assert _avaliar(coleta_dias=2, execucao_dias=2).estado == "em_dia"


def test_vencido_tem_prioridade_sobre_coleta_parada():
    assert _avaliar(coleta_dias=9, execucao_dias=9).estado == "vencido"


def test_datetime_sem_fuso_do_sqlite_e_utc():
    coleta = (datetime(2026, 9, 19, 9, 5), "partial")
    frescor = regra.avaliar(coleta, coleta, 2, None, AGORA)
    assert frescor.ultima_coleta.tzinfo is not None
    assert frescor.estado == "em_dia"


# --- consulta -------------------------------------------------------------------


def _execucao(dias: int, status="success", full_scope=True, intervalo=2, proxima=None):
    inicio = _dias_atras(dias)
    return CollectionRun(started_at=inicio, finished_at=inicio, triggered_by="schedule",
                         status=status, full_scope=full_scope, interval_days=intervalo,
                         next_run_on=proxima, jobs_count=1, failures=0, summary={})


def _gravar(banco, *execucoes) -> None:
    engine = make_engine(banco)
    try:
        with Session(engine) as db, db.begin():
            db.add_all(execucoes)
    finally:
        engine.dispose()


def _estado(banco) -> regra.Frescor:
    engine = make_engine(banco)
    try:
        with Session(engine) as db:
            return regra.estado_das_coletas(db, AGORA)
    finally:
        engine.dispose()


def test_consulta_segue_a_regra_da_guarda(banco_historico):
    _gravar(
        banco_historico,
        _execucao(6, "success", proxima=date(2026, 9, 16)),
        _execucao(3, "partial", proxima=date(2026, 9, 19)),
        _execucao(2, "failed", intervalo=None),                 # falha nao conta
        _execucao(1, "success", full_scope=False, intervalo=None),  # amostra nao conta
        _execucao(0, "skipped", proxima=date(2026, 9, 21)),
    )
    frescor = _estado(banco_historico)
    assert frescor.estado == "em_dia"
    assert (frescor.dias_desde_ultima_coleta, frescor.status_ultima_coleta) == (3, "partial")
    assert (frescor.status_ultima_execucao, frescor.dias_desde_ultima_execucao) == ("skipped", 0)
    assert (frescor.intervalo_dias, frescor.proxima_coleta) == (2, date(2026, 9, 21))


def test_banco_sem_execucoes(banco_historico):
    assert _estado(banco_historico).estado == "sem_coleta"


# --- endpoint -------------------------------------------------------------------


@pytest.fixture
def cliente(banco_historico, monkeypatch):
    engine = make_engine(banco_historico)

    def sessao():
        with Session(engine) as db:
            yield db

    monkeypatch.setattr("api.app.init_db", lambda: None)
    monkeypatch.setattr(regra, "datetime", _RelogioFixo)
    app.dependency_overrides[get_db] = sessao
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


class _RelogioFixo(datetime):
    @classmethod
    def now(cls, tz=None):
        return AGORA


def test_dados_em_dia_respondem_200(cliente, banco_historico):
    _gravar(banco_historico, _execucao(1), _execucao(0, "skipped"))
    resposta = cliente.get("/health/dados")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["estado"], corpo["saudavel"], corpo["limite_dias"]) == ("em_dia", True, 4)
    assert corpo["ultima_coleta"].startswith("2026-09-19T09:05")


@pytest.mark.parametrize("execucoes, estado", [
    ([], "sem_coleta"),
    ([(9, "success")], "vencido"),
    ([(3, "success")], "coleta_parada"),
])
def test_problema_de_frescor_responde_503(cliente, banco_historico, execucoes, estado):
    if execucoes:
        _gravar(banco_historico, *(_execucao(d, s) for d, s in execucoes))
    resposta = cliente.get("/health/dados")
    assert resposta.status_code == 503
    assert resposta.json()["estado"] == estado


def test_health_continua_200_com_dado_vencido(cliente, banco_historico):
    """O Render usa /health: dado velho nao pode derrubar uma API saudavel."""
    _gravar(banco_historico, _execucao(30))
    assert cliente.get("/health/dados").status_code == 503
    assert cliente.get("/health").status_code == 200


def test_banco_indisponivel_responde_503_sem_detalhes(monkeypatch):
    from sqlalchemy.exc import OperationalError

    class _SessaoQuebrada:
        def execute(self, *_a, **_k):
            raise OperationalError("SELECT", {}, Exception("host=db.segredo.neon.tech senha=x"))

    monkeypatch.setattr("api.app.init_db", lambda: None)
    app.dependency_overrides[get_db] = lambda: _SessaoQuebrada()
    try:
        with TestClient(app) as client:
            resposta = client.get("/health/dados")
    finally:
        app.dependency_overrides.clear()
    assert resposta.status_code == 503
    assert resposta.json()["estado"] == "indisponivel"
    assert "segredo" not in resposta.text and "senha" not in resposta.text


def test_endpoint_documentado_no_openapi(cliente):
    caminho = cliente.get("/openapi.json").json()["paths"]["/health/dados"]["get"]
    assert {"200", "503"} <= set(caminho["responses"])
