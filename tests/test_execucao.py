"""Politica de execucao: intervalo entre coletas, status por fonte e falhas isoladas."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import requests

from scraper import pipeline
from scraper.config import ConfiguracaoError, Settings, obter_intervalo_dias
from scraper.execucao import (
    FAILED,
    OK,
    PARTIAL,
    SUCCESS,
    Agenda,
    calcular_agenda,
    decidir,
    escopo_completo,
    status_execucao,
    status_fonte,
)
from scraper.http_client import PoliteSession
from scraper.models import Job, SourceStats
from scraper.sources.base import JobSource

ULTIMA = datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc)


# --- COLLECTION_INTERVAL_DAYS ------------------------------------------------

@pytest.mark.parametrize("valor", ["", "   ", "0", "-1", "2.5", "tres", "+3", "1e2"])
def test_intervalo_invalido_ou_ausente_e_recusado(valor):
    with pytest.raises(ConfiguracaoError, match="COLLECTION_INTERVAL_DAYS"):
        obter_intervalo_dias({"COLLECTION_INTERVAL_DAYS": valor}, arquivos=())


def test_intervalo_valido():
    assert obter_intervalo_dias({"COLLECTION_INTERVAL_DAYS": " 3 "}, arquivos=()) == 3


def test_intervalo_do_ambiente_vence_o_arquivo(tmp_path):
    arquivo = tmp_path / ".env.local"
    arquivo.write_text("COLLECTION_INTERVAL_DAYS=7\n", encoding="utf-8")
    assert obter_intervalo_dias({"COLLECTION_INTERVAL_DAYS": "2"}, [arquivo]) == 2
    assert obter_intervalo_dias({}, [arquivo]) == 7


def test_guarda_sem_banco_e_recusada_antes_de_coletar(monkeypatch):
    monkeypatch.setattr(pipeline, "collect", lambda _s: pytest.fail("não deveria coletar"))
    with pytest.raises(ConfiguracaoError, match="banco"):
        pipeline.run(Settings(), persistir=False, exportar_csv=True,
                     respeitar_intervalo=True, intervalo_dias=3)


def test_guarda_sem_intervalo_configurado_falha_antes_do_banco(monkeypatch):
    monkeypatch.setattr(pipeline, "preparar_banco", lambda _d: pytest.fail("não deveria conectar"))
    with pytest.raises(ConfiguracaoError, match="COLLECTION_INTERVAL_DAYS"):
        pipeline.run(Settings(), respeitar_intervalo=True)


# --- Guarda de intervalo ------------------------------------------------------

def test_sem_coleta_anterior_executa():
    decisao = decidir(None, ULTIMA, 3)
    assert decisao.executar
    assert decisao.proxima_em is None


def test_dentro_do_intervalo_pula_com_motivo_e_data_prevista():
    decisao = decidir(ULTIMA, datetime(2026, 9, 17, 23, 59, tzinfo=timezone.utc), 3)
    assert not decisao.executar
    assert decisao.proxima_em == date(2026, 9, 18)
    assert "15/09/2026" in decisao.motivo
    assert "3 dia(s)" in decisao.motivo


def test_no_dia_previsto_executa_mesmo_antes_do_horario_da_ultima():
    """O cron pode acordar alguns minutos antes do horario da coleta anterior."""
    assert decidir(ULTIMA, datetime(2026, 9, 18, 9, 2, tzinfo=timezone.utc), 3).executar


def test_dias_sao_contados_em_utc():
    brasilia = timezone(timedelta(hours=-3))
    # 22:30 do dia 17 em Brasilia ja e dia 18 em UTC.
    assert decidir(ULTIMA, datetime(2026, 9, 17, 22, 30, tzinfo=brasilia), 3).executar
    # 20:00 do dia 17 em Brasilia ainda e dia 17 em UTC.
    assert not decidir(ULTIMA, datetime(2026, 9, 17, 20, 0, tzinfo=brasilia), 3).executar


def test_intervalo_de_um_dia():
    assert not decidir(ULTIMA, ULTIMA.replace(hour=23), 1).executar
    assert decidir(ULTIMA, datetime(2026, 9, 16, 0, 1, tzinfo=timezone.utc), 1).executar


def test_data_sem_fuso_do_sqlite_e_tratada_como_utc():
    decisao = decidir(ULTIMA.replace(tzinfo=None), ULTIMA + timedelta(days=1), 3)
    assert decisao.proxima_em == date(2026, 9, 18)


# --- Agenda: ultima e proxima coleta -----------------------------------------

def test_coleta_de_hoje_agenda_a_proxima_para_daqui_a_x_dias():
    agenda = calcular_agenda(ULTIMA, ULTIMA, 2)
    assert (agenda.ultima, agenda.proxima) == (date(2026, 9, 15), date(2026, 9, 17))
    assert agenda.frase() == "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026"
    assert agenda.periodicidade == "a cada 2 dias"


def test_execucao_pulada_repete_a_data_da_guarda():
    agora = ULTIMA + timedelta(days=1)
    assert calcular_agenda(ULTIMA, agora, 2).proxima == decidir(ULTIMA, agora, 2).proxima_em


def test_proxima_ja_vencida_vira_amanha():
    """A ultima coleta completa foi ha 5 dias e a de hoje falhou: o cron tenta amanha."""
    agenda = calcular_agenda(ULTIMA, ULTIMA + timedelta(days=5), 2)
    assert (agenda.ultima, agenda.proxima) == (date(2026, 9, 15), date(2026, 9, 21))


def test_sem_coleta_registrada_a_proxima_e_amanha():
    agenda = calcular_agenda(None, ULTIMA, 2)
    assert agenda == Agenda(None, date(2026, 9, 16), 2)
    assert agenda.frase() == "Última coleta: nenhuma registrada e próxima: dia 16/09/2026"


def test_periodicidade_no_singular():
    assert calcular_agenda(ULTIMA, ULTIMA, 1).periodicidade == "a cada 1 dia"


def test_escopo_completo():
    assert escopo_completo(Settings())
    assert not escopo_completo(Settings(sources=["gupy"]))
    assert not escopo_completo(Settings(search_terms=["estagio dados"]))
    assert not escopo_completo(Settings(max_pages_per_term=1))
    assert not escopo_completo(Settings(only_junior=False))


# --- Status por fonte e da execucao -------------------------------------------

def _stats(brutas: int = 0, erros: int = 0, falhas: int = 0) -> SourceStats:
    return SourceStats(source="gupy", requests_made=5, raw_jobs=brutas,
                       errors=["erro"] * erros, requests_failed=falhas)


def _gravacao(gravadas: int = 0, falhas: int = 0) -> SimpleNamespace:
    return SimpleNamespace(jobs_criados=gravadas, jobs_atualizados=0, falhas=falhas)


@pytest.mark.parametrize("stats, gravacao, esperado", [
    (_stats(brutas=10), _gravacao(gravadas=10), OK),
    (_stats(), None, OK),                                        # sem vagas, sem falha
    (_stats(brutas=10, falhas=1), _gravacao(gravadas=10), PARTIAL),  # uma pagina bloqueada
    (_stats(brutas=10, erros=1), None, PARTIAL),                 # um termo quebrou
    (_stats(brutas=10), _gravacao(gravadas=9, falhas=1), PARTIAL),
    (_stats(falhas=3), None, FAILED),                            # portal bloqueado
    (_stats(erros=2), None, FAILED),
    (_stats(brutas=10), _gravacao(falhas=10), FAILED),           # transacao desfeita
])
def test_status_da_fonte(stats, gravacao, esperado):
    assert status_fonte(stats, gravacao) == esperado


@pytest.mark.parametrize("fontes, vagas, falhas, esperado", [
    ({"gupy": OK, "vagas": OK}, 10, 0, (SUCCESS, 0)),
    ({"gupy": OK, "linkedin": FAILED}, 10, 0, (PARTIAL, 0)),
    ({"gupy": PARTIAL}, 10, 0, (PARTIAL, 0)),
    ({"gupy": OK}, 10, 2, (PARTIAL, 1)),
    ({"gupy": FAILED, "vagas": FAILED}, 0, 0, (FAILED, 1)),
    ({"gupy": OK}, 0, 0, (FAILED, 1)),
])
def test_status_da_execucao(fontes, vagas, falhas, esperado):
    assert status_execucao(fontes, vagas, falhas) == esperado


@pytest.mark.parametrize("fontes, vagas, esperado", [
    ({"gupy": PARTIAL, "vagas": OK}, 10, (PARTIAL, 1)),  # fonte rebaixada pelo alerta
    ({"gupy": OK}, 10, (PARTIAL, 1)),                     # alerta global (sem fonte)
    ({"gupy": FAILED}, 0, (FAILED, 1)),                   # falha continua falha
])
def test_alerta_de_qualidade_alto_sempre_sai_com_exit_1(fontes, vagas, esperado):
    assert status_execucao(fontes, vagas, 0, alertas_altos=1) == esperado


# --- Falhas visiveis na coleta --------------------------------------------------

class _Resposta:
    def __init__(self, status_code: int, corpo=None):
        self.status_code = status_code
        self._corpo = corpo
        self.headers = {"content-type": "text/html"}

    def json(self):
        if self._corpo is None:
            raise ValueError("não é JSON")
        return self._corpo


def test_sessao_conta_as_requisicoes_em_que_desistiu(monkeypatch):
    sessao = PoliteSession(user_agent="teste", delay_seconds=0)
    respostas = [requests.ConnectionError("sem rede"), _Resposta(503),
                 _Resposta(200, {"data": []}), _Resposta(200)]

    def _get(_url, **_kwargs):
        resposta = respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr(sessao.session, "get", _get)
    try:
        assert sessao.get("https://exemplo.test/a") is None
        assert sessao.get("https://exemplo.test/b") is None
        assert sessao.get_json("https://exemplo.test/c") == {"data": []}
        assert sessao.get_json("https://exemplo.test/d") is None
    finally:
        sessao.close()
    assert (sessao.request_count, sessao.failed_count) == (4, 3)


class _FonteQuebrada(JobSource):
    name = "quebrada"
    label = "Quebrada"

    def fetch_term(self, term):
        return []

    def fetch(self, terms):
        raise RuntimeError("sitemap mudou de formato")


class _FonteBoa(JobSource):
    name = "boa"
    label = "Boa"

    def fetch_term(self, term):
        return [Job(source=self.name, external_id=term, title="Desenvolvedor Júnior")]


def test_fonte_que_quebra_nao_derruba_as_outras(monkeypatch):
    monkeypatch.setitem(pipeline.SOURCE_REGISTRY, "quebrada", _FonteQuebrada)
    monkeypatch.setitem(pipeline.SOURCE_REGISTRY, "boa", _FonteBoa)
    settings = Settings(sources=["quebrada", "boa"], search_terms=["a", "b"], delay_seconds=0)

    jobs, stats, _ = pipeline.collect(settings)

    assert [job.external_id for job in jobs] == ["a", "b"]
    por_fonte = {s.source: s for s in stats}
    assert por_fonte["quebrada"].raw_jobs == 0
    assert "RuntimeError" in por_fonte["quebrada"].errors[0]
    assert status_fonte(por_fonte["quebrada"]) == FAILED
    assert status_fonte(por_fonte["boa"]) == OK
