"""Checagens de plausibilidade da coleta (`scraper/qualidade.py`).

Cada regra tem um caso que dispara e um caso normal que nao dispara.
"""

from __future__ import annotations

from datetime import date

import pytest

from scraper import qualidade
from scraper.models import Job, SourceStats
from scraper.sources import DEFAULT_SOURCES

HOJE = date(2026, 9, 15)


def _vaga(fonte="gupy", i=0, **campos) -> Job:
    base = dict(
        source=fonte, external_id=str(i), title="Desenvolvedor Backend Júnior",
        company="ACME", url=f"https://portal.exemplo/{fonte}/{i}",
        description="APIs REST em Java.", workplace_type="Remoto",
        published_date="2026-09-10", area="Backend", skills=["Java"],
    )
    base.update(campos)
    return Job(**base)


def _vagas(fonte="gupy", n=25, **campos) -> list[Job]:
    return [_vaga(fonte, i, **campos) for i in range(n)]


def _stats(**brutas) -> list[SourceStats]:
    return [SourceStats(source=f, requests_made=5, raw_jobs=n) for f, n in brutas.items()]


def _regras(alertas) -> list[tuple[str, str | None]]:
    return [(a.regra, a.fonte) for a in alertas]


def _verificar(jobs=(), stats=(), escopo_completo=True, historico=None):
    return qualidade.verificar(list(jobs), list(stats), escopo_completo=escopo_completo,
                               historico=historico, hoje=HOJE)


def test_coleta_normal_nao_gera_alerta():
    assert _verificar(_vagas(), _stats(gupy=159), historico={"gupy": [150, 160, 170]}) == []


# --- fonte zerada ------------------------------------------------------------


def test_fonte_padrao_com_zero_vagas_sem_erro_e_alerta_alto():
    alertas = _verificar(stats=_stats(gupy=0, linkedin=647))
    assert _regras(alertas) == [("fonte_zerada", "gupy")]
    assert alertas[0].severidade == qualidade.ALTA


def test_fonte_com_erro_e_zero_vagas_ja_e_failed_e_nao_duplica():
    bloqueada = SourceStats(source="gupy", requests_made=3, requests_failed=3)
    quebrada = SourceStats(source="linkedin", errors=["linkedin: ValueError: x"])
    assert _verificar(stats=[bloqueada, quebrada]) == []


def test_fonte_fora_da_coleta_padrao_zerada_nao_alerta():
    assert "programathor" not in DEFAULT_SOURCES
    assert _verificar(stats=_stats(programathor=0)) == []


def test_escopo_parcial_nao_avalia_fonte_zerada():
    assert _verificar(stats=_stats(gupy=0), escopo_completo=False) == []


# --- queda brusca ------------------------------------------------------------


def test_queda_abaixo_de_30_por_cento_da_mediana_e_alerta_alto():
    alertas = _verificar(stats=_stats(linkedin=100), historico={"linkedin": [640, 650, 700]})
    assert _regras(alertas) == [("queda_brusca", "linkedin")]
    assert (alertas[0].valor, alertas[0].limite) == (100, 195)


def test_variacao_normal_nao_e_queda():
    assert _verificar(stats=_stats(linkedin=400), historico={"linkedin": [640, 650, 700]}) == []


@pytest.mark.parametrize("historico", [None, {}, {"linkedin": [650]}, {"linkedin": [650, 640]}])
def test_sem_historico_suficiente_nao_avalia_queda(historico):
    """A primeira execucao (e as duas seguintes) nunca geram falso positivo."""
    assert _verificar(stats=_stats(linkedin=10), historico=historico) == []


def test_fonte_pequena_nao_avalia_queda():
    """Trampos.co listou 24 vagas em 15/09: oscila demais para comparar."""
    assert _verificar(stats=_stats(trampos=2), historico={"trampos": [24, 20, 26]}) == []


def test_escopo_parcial_nao_avalia_queda():
    assert _verificar(stats=_stats(linkedin=10), escopo_completo=False,
                      historico={"linkedin": [640, 650, 700]}) == []


# --- dominios ----------------------------------------------------------------


def test_area_fora_do_dominio_e_alerta_alto():
    alertas = _verificar([_vaga(area="Blockchain"), _vaga(i=1)])
    assert _regras(alertas) == [("area_fora_do_dominio", "gupy")]
    assert alertas[0].valor == 1


def test_modalidade_fora_do_dominio_e_alerta_alto():
    alertas = _verificar([_vaga(workplace_type="Meio remoto")])
    assert _regras(alertas) == [("modalidade_fora_do_dominio", "gupy")]


def test_modalidade_vazia_e_legitima():
    """A ProgramaThor devolve vazio; a persistencia grava nulo."""
    assert _verificar([_vaga("programathor", workplace_type="")]) == []


def test_url_que_nao_e_http_e_alerta_baixo():
    alertas = _verificar([_vaga(url="javascript:alert(1)"), _vaga(i=1, url="")])
    assert _regras(alertas) == [("url_invalida", "gupy")]
    assert alertas[0].severidade == qualidade.BAIXA


def test_data_no_futuro_e_alerta_baixo():
    alertas = _verificar([_vaga(published_date="2026-10-01"), _vaga(i=1, published_date="Ontem")])
    assert _regras(alertas) == [("data_no_futuro", "gupy")]


# --- vazios por fonte --------------------------------------------------------


def test_descricao_vazia_acima_do_limite_e_alerta_alto():
    jobs = _vagas(n=15) + _vagas(n=10, description="")
    for i, job in enumerate(jobs):
        job.external_id = str(i)
    alertas = _verificar(jobs)
    assert _regras(alertas) == [("campo_vazio", "gupy")]
    assert (alertas[0].severidade, alertas[0].valor, alertas[0].limite) == ("alta", 0.4, 0.2)


def test_linkedin_e_isento_de_descricao_modalidade_e_tecnologias():
    jobs = _vagas("linkedin", description="", workplace_type="Não informado", skills=[])
    assert _verificar(jobs) == []


def test_vagas_com_e_isento_de_modalidade_e_tecnologias():
    assert _verificar(_vagas("vagas", workplace_type="Não informado", skills=[])) == []


def test_mesmo_campo_vazio_alerta_em_fonte_que_nao_e_isenta():
    alertas = _verificar(_vagas("gupy", workplace_type="Não informado", skills=[]))
    assert {(a.regra, a.fonte, a.severidade) for a in alertas} == {("campo_vazio", "gupy", "baixa")}
    assert len(alertas) == 2


def test_fonte_com_poucas_vagas_nao_avalia_vazios():
    assert _verificar(_vagas("vagas", n=19, description="", company="")) == []


# --- classificacao -----------------------------------------------------------


def test_classificacao_degenerada_e_alerta_baixo():
    jobs = [_vaga(i=i, area="Outros/TI Geral") for i in range(40)] + \
           [_vaga(i=100 + i) for i in range(20)]
    alertas = _verificar(jobs)
    assert _regras(alertas) == [("classificacao_degenerada", None)]
    assert alertas[0].valor == 0.67


def test_classificacao_com_poucas_vagas_nao_e_avaliada():
    assert _verificar([_vaga(i=i, area="Outros/TI Geral") for i in range(49)]) == []


# --- ordem, status e calibragem ---------------------------------------------


def test_alertas_altos_vem_primeiro():
    jobs = [_vaga(url="ftp://x"), _vaga(i=1, area="Blockchain")]
    alertas = _verificar(jobs, _stats(linkedin=0))
    assert [a.severidade for a in alertas] == ["alta", "alta", "baixa"]


def test_alerta_alto_torna_a_fonte_parcial_sem_rebaixar_falha():
    alertas = [
        qualidade.Alerta("fonte_zerada", qualidade.ALTA, "gupy", 0, "> 0", "x"),
        qualidade.Alerta("queda_brusca", qualidade.ALTA, "linkedin", 1, 2, "x"),
        qualidade.Alerta("url_invalida", qualidade.BAIXA, "vagas", 1, 0, "x"),
        qualidade.Alerta("classificacao_degenerada", qualidade.ALTA, None, 1, 0, "x"),
    ]
    status = {"gupy": "ok", "linkedin": "failed", "vagas": "ok"}
    assert qualidade.ajustar_status(status, alertas) == {
        "gupy": "partial", "linkedin": "failed", "vagas": "ok",
    }
    assert status["gupy"] == "ok"  # nao altera o dict recebido


def test_alerta_nunca_carrega_url_nem_dado_de_vaga():
    alertas = _verificar([_vaga(url="javascript:segredo", title="Título secreto")])
    assert "segredo" not in str([a.como_dict() for a in alertas])


def test_coleta_real_de_15_09_nao_gera_alertas():
    """Calibragem: o seed (coleta completa de 15/09/2026) e o comportamento normal."""
    pytest.importorskip("sqlalchemy")
    from scripts.carregar_seed import SEED, ler_vagas

    brutas = {"gupy": 159, "vagas": 662, "trampos": 24, "linkedin": 647,
              "querovagastech": 194, "geekhunter": 47}
    alertas = _verificar(ler_vagas(SEED), _stats(**brutas),
                         historico={f: [n, n, n] for f, n in brutas.items()})
    assert alertas == []
