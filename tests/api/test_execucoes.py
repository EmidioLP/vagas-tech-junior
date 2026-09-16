"""Integracao: guarda de intervalo e resiliencia por fonte, no schema das migrations.

A coleta e o relogio sao substituidos: os testes simulam dias passando e portais
falhando sem tocar a rede. Cada execucao com banco vira uma linha em
`collection_runs`. O intervalo e o do projeto: a cada 2 dias.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import main as cli
from api.database import make_engine
from api.models import CollectionRun, JobRecord
from scraper import pipeline
from scraper.config import Settings
from scraper.models import Job, SourceStats
from scraper.sources import DEFAULT_SOURCES

INICIO = datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc)
X = 2


class Coleta:
    """Substitui `pipeline.collect`: duas vagas por fonte, exceto as que falham."""

    def __init__(self, falham=()):
        self.falham = set(falham)
        self.chamadas = 0

    def __call__(self, settings):
        self.chamadas += 1
        jobs: list[Job] = []
        stats: list[SourceStats] = []
        for fonte in settings.sources:
            if fonte in self.falham:
                # Portal bloqueado: a sessao desistiu de todas as requisicoes.
                stats.append(SourceStats(source=fonte, requests_made=3, requests_failed=3))
                continue
            # Empresas com um token unico cada: a dedupe junta nomes em que um
            # conjunto de palavras contem o outro, e ignora tokens curtos.
            vagas = [
                Job(source=fonte, external_id=str(i), title="Desenvolvedor Backend Júnior",
                    company=f"{fonte}{sufixo}", description="APIs REST em Java com Spring Boot.")
                for i, sufixo in enumerate(("alfa", "beta"))
            ]
            jobs.extend(vagas)
            stats.append(SourceStats(source=fonte, requests_made=1, raw_jobs=len(vagas)))
        return jobs, stats, sum(s.requests_made for s in stats)


@pytest.fixture
def relogio(monkeypatch):
    agora = {"valor": INICIO}
    monkeypatch.setattr(pipeline, "_agora", lambda: agora["valor"])
    return agora


def _rodar(monkeypatch, banco, coleta=None, settings=None, **kwargs):
    coleta = coleta or Coleta()
    monkeypatch.setattr(pipeline, "collect", coleta)
    kwargs.setdefault("intervalo_dias", X)
    resultado = pipeline.run(settings or Settings(), destino_db=banco, **kwargs)
    return resultado, coleta


def _execucoes(banco) -> list[CollectionRun]:
    engine = make_engine(banco)
    try:
        with Session(engine, expire_on_commit=False) as db:
            return list(db.scalars(select(CollectionRun).order_by(CollectionRun.id)))
    finally:
        engine.dispose()


def _vagas_por_fonte(banco) -> dict[str, int]:
    engine = make_engine(banco)
    try:
        with Session(engine) as db:
            linhas = db.execute(
                select(JobRecord.source, func.count()).group_by(JobRecord.source)
            ).all()
            return dict(linhas)
    finally:
        engine.dispose()


def test_primeira_execucao_agendada_coleta_registra_e_agenda(monkeypatch, relogio, banco_historico):
    resultado, coleta = _rodar(monkeypatch, banco_historico,
                               respeitar_intervalo=True, gatilho="schedule")

    assert coleta.chamadas == 1
    assert (resultado.status, resultado.exit_code) == ("success", 0)
    assert resultado.agenda.frase() == "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026"

    [execucao] = _execucoes(banco_historico)
    assert (execucao.status, execucao.triggered_by, execucao.full_scope,
            execucao.interval_days, execucao.next_run_on) == (
        "success", "schedule", True, X, date(2026, 9, 17))
    assert execucao.jobs_count == 2 * len(DEFAULT_SOURCES)
    assert execucao.summary["fontes"]["gupy"]["status"] == "ok"
    assert execucao.summary["fontes"]["gupy"]["jobs_criados"] == 2


def test_dentro_do_intervalo_a_execucao_e_pulada_sem_coletar(monkeypatch, relogio, banco_historico):
    _rodar(monkeypatch, banco_historico, respeitar_intervalo=True, gatilho="schedule")

    relogio["valor"] = INICIO + timedelta(days=1)
    resultado, coleta = _rodar(monkeypatch, banco_historico,
                               respeitar_intervalo=True, gatilho="schedule")

    assert coleta.chamadas == 0
    assert resultado.pulada
    assert resultado.exit_code == 0
    assert resultado.decisao.proxima_em == date(2026, 9, 17)
    assert resultado.agenda.frase() == "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026"
    pulada = _execucoes(banco_historico)[-1]
    assert (pulada.status, pulada.jobs_count, pulada.next_run_on) == (
        "skipped", 0, date(2026, 9, 17))
    assert "15/09/2026" in pulada.reason


def test_depois_de_x_dias_coleta_de_novo(monkeypatch, relogio, banco_historico):
    _rodar(monkeypatch, banco_historico, respeitar_intervalo=True, gatilho="schedule")

    # O cron acordou minutos antes do horario da coleta anterior.
    relogio["valor"] = (INICIO + timedelta(days=X)).replace(hour=9, minute=0)
    resultado, coleta = _rodar(monkeypatch, banco_historico,
                               respeitar_intervalo=True, gatilho="schedule")

    assert coleta.chamadas == 1
    assert resultado.status == "success"
    assert resultado.agenda.frase() == "Última coleta: dia 17/09/2026 e próxima: dia 19/09/2026"
    assert [e.status for e in _execucoes(banco_historico)] == ["success", "success"]


def test_disparo_manual_forcado_ignora_o_intervalo(monkeypatch, relogio, banco_historico):
    _rodar(monkeypatch, banco_historico, respeitar_intervalo=True, gatilho="schedule")

    relogio["valor"] = INICIO + timedelta(days=1)
    resultado, coleta = _rodar(monkeypatch, banco_historico, gatilho="manual")

    assert coleta.chamadas == 1
    assert resultado.status == "success"
    # A coleta forcada vira a ultima: a contagem dos 2 dias recomeca.
    assert resultado.agenda.frase() == "Última coleta: dia 16/09/2026 e próxima: dia 18/09/2026"
    ultima = _execucoes(banco_historico)[-1]
    assert (ultima.triggered_by, ultima.interval_days, ultima.status) == ("manual", None, "success")


def test_fonte_com_falha_nao_impede_as_demais_de_gravar(monkeypatch, relogio, banco_historico):
    resultado, _ = _rodar(monkeypatch, banco_historico, coleta=Coleta(falham={"linkedin"}),
                          respeitar_intervalo=True)

    assert (resultado.status, resultado.exit_code) == ("partial", 0)
    assert resultado.status_fontes["linkedin"] == "failed"
    assert resultado.status_fontes["gupy"] == "ok"
    por_fonte = _vagas_por_fonte(banco_historico)
    assert "linkedin" not in por_fonte
    assert por_fonte["gupy"] == 2

    execucao = _execucoes(banco_historico)[-1]
    assert execucao.status == "partial"
    assert "linkedin (failed)" in execucao.reason
    assert execucao.summary["fontes"]["linkedin"] == {
        "status": "failed", "requests": 3, "requests_falhos": 3,
        "vagas_brutas": 0, "erros": 0,
    }

    # Parcial conta como coleta: no dia seguinte, dentro do intervalo, pula.
    relogio["valor"] = INICIO + timedelta(days=1)
    seguinte, coleta = _rodar(monkeypatch, banco_historico, respeitar_intervalo=True)
    assert seguinte.pulada
    assert coleta.chamadas == 0


def test_todas_as_fontes_falhando_da_status_claro_e_nao_conta_para_a_guarda(
    monkeypatch, relogio, banco_historico,
):
    resultado, _ = _rodar(monkeypatch, banco_historico, coleta=Coleta(falham=DEFAULT_SOURCES),
                          respeitar_intervalo=True)

    assert (resultado.status, resultado.exit_code) == ("failed", 1)
    assert set(resultado.status_fontes.values()) == {"failed"}
    # Sem coleta completa registrada, o cron tenta de novo amanha.
    assert resultado.agenda.frase() == "Última coleta: nenhuma registrada e próxima: dia 16/09/2026"
    execucao = _execucoes(banco_historico)[-1]
    assert (execucao.status, execucao.reason, execucao.jobs_count) == (
        "failed", "todas as fontes falharam", 0)

    relogio["valor"] = INICIO + timedelta(hours=1)
    seguinte, coleta = _rodar(monkeypatch, banco_historico, respeitar_intervalo=True)
    assert coleta.chamadas == 1
    assert seguinte.status == "success"


class ColetaComFonteZerada(Coleta):
    """Portal que mudou o HTML: nenhuma requisicao falha, e nenhuma vaga aparece."""

    def __init__(self, zerada):
        super().__init__()
        self.zerada = zerada

    def __call__(self, settings):
        jobs, stats, requests = super().__call__(settings)
        jobs = [j for j in jobs if j.source != self.zerada]
        for s in stats:
            if s.source == self.zerada:
                s.raw_jobs = 0
        return jobs, stats, requests


def test_fonte_zerada_sem_erro_vira_parcial_com_exit_1_e_alerta_registrado(
    monkeypatch, relogio, banco_historico,
):
    resultado, _ = _rodar(monkeypatch, banco_historico, coleta=ColetaComFonteZerada("gupy"),
                          respeitar_intervalo=True)

    assert (resultado.status, resultado.exit_code) == ("partial", 1)
    assert resultado.status_fontes["gupy"] == "partial"
    assert resultado.status_fontes["linkedin"] == "ok"

    execucao = _execucoes(banco_historico)[-1]
    assert execucao.status == "partial"
    assert "alertas de qualidade: fonte_zerada (gupy)" in execucao.reason
    assert execucao.summary["fontes"]["gupy"]["status"] == "partial"
    [alerta] = execucao.summary["qualidade"]
    assert (alerta["regra"], alerta["severidade"], alerta["fonte"]) == ("fonte_zerada", "alta", "gupy")

    # Os dados foram gravados e a execucao conta para a guarda de intervalo.
    assert _vagas_por_fonte(banco_historico)["linkedin"] == 2
    relogio["valor"] = INICIO + timedelta(days=1)
    seguinte, coleta = _rodar(monkeypatch, banco_historico, respeitar_intervalo=True)
    assert seguinte.pulada and coleta.chamadas == 0


def test_coleta_normal_registra_qualidade_sem_alertas(monkeypatch, relogio, banco_historico):
    resultado, _ = _rodar(monkeypatch, banco_historico)
    assert resultado.alertas == []
    assert _execucoes(banco_historico)[-1].summary["qualidade"] == []


def test_historico_de_vagas_brutas_so_usa_coletas_completas_que_contam(
    monkeypatch, relogio, banco_historico,
):
    from persistence.execucoes import historico_vagas_brutas

    _rodar(monkeypatch, banco_historico)                                      # completa, success
    relogio["valor"] = INICIO + timedelta(days=2)
    _rodar(monkeypatch, banco_historico, coleta=Coleta(falham={"gupy"}))      # completa, partial
    relogio["valor"] = INICIO + timedelta(days=4)
    _rodar(monkeypatch, banco_historico, coleta=Coleta(falham=DEFAULT_SOURCES))  # failed
    relogio["valor"] = INICIO + timedelta(days=5)
    _rodar(monkeypatch, banco_historico, settings=Settings(sources=["gupy"]))  # parcial de escopo

    engine = make_engine(banco_historico)
    try:
        historico = historico_vagas_brutas(engine)
        assert historico["gupy"] == [2]         # o dia em que falhou nao entra
        assert historico["linkedin"] == [2, 2]
        assert historico_vagas_brutas(engine, limite=1)["linkedin"] == [2]
    finally:
        engine.dispose()


def test_coleta_de_escopo_parcial_nao_adia_a_completa(monkeypatch, relogio, banco_historico):
    parcial, _ = _rodar(monkeypatch, banco_historico, settings=Settings(sources=["gupy"]),
                        respeitar_intervalo=True)
    assert parcial.status == "success"
    assert parcial.agenda.ultima is None
    assert _execucoes(banco_historico)[-1].full_scope is False

    completa, coleta = _rodar(monkeypatch, banco_historico, respeitar_intervalo=True)
    assert coleta.chamadas == 1
    assert not completa.pulada


def test_execucao_forcada_sem_intervalo_configurado_nao_informa_agenda(
    monkeypatch, relogio, banco_historico,
):
    monkeypatch.setattr(pipeline, "collect", Coleta())
    resultado = pipeline.run(Settings(), destino_db=banco_historico, gatilho="manual")
    assert resultado.status == "success"
    assert resultado.agenda is None
    assert _execucoes(banco_historico)[-1].next_run_on is None


def test_cli_agendada_informa_ultima_e_proxima_coleta(
    monkeypatch, relogio, banco_historico, tmp_path, capsys,
):
    monkeypatch.setenv("COLLECTION_INTERVAL_DAYS", str(X))
    monkeypatch.setattr(pipeline, "collect", Coleta())
    argumentos = ["--db", str(banco_historico), "--trigger", "schedule", "--respect-interval"]
    agenda = "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026 (a cada 2 dias)."

    assert cli.main(argumentos) == 0
    assert agenda in capsys.readouterr().out

    relogio["valor"] = INICIO + timedelta(days=1)
    destino = tmp_path / "resumo.md"
    assert cli.main([*argumentos, "--resumo", str(destino)]) == 0

    saida = capsys.readouterr().out
    assert "Coleta pulada" in saida
    assert agenda in saida
    texto = destino.read_text(encoding="utf-8")
    assert "pulada (exit 0)" in texto
    assert "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026" in texto
    assert [e.status for e in _execucoes(banco_historico)] == ["success", "skipped"]
