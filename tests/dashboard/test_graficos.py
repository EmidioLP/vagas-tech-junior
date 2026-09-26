"""A forma de cada grafico do dashboard (docs/graficos.md), pela especificacao Vega-Lite.

Cada construtor de `dashboard/graficos.py` e inspecionado por `to_dict()`: marca,
codificacao e ordem. Nao renderiza nada.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("altair")
pytest.importorskip("sqlalchemy")

import pandas as pd  # noqa: E402

from dashboard import graficos  # noqa: E402
from dashboard.consultas import Contagem, PontoSerie, RankingTecnologias  # noqa: E402

SERIE = [
    PontoSerie(date(2026, 9, 20), 10, 10, 10, {"Backend": 2, "Data": 8}),
    PontoSerie(date(2026, 9, 21), 12, 3, 5, {"Backend": 7, "Data": 5}),
]


def _tabela() -> pd.DataFrame:
    return pd.DataFrame({
        "Dia": pd.to_datetime([p.dia for p in SERIE]),
        "Vagas abertas": [p.abertas for p in SERIE],
        "Vagas novas": [p.novas for p in SERIE],
    })


def _marca(camada: dict) -> str:
    marca = camada["mark"]
    return marca["type"] if isinstance(marca, dict) else marca


def _dados(spec: dict) -> list[dict]:
    return next(iter(spec["datasets"].values()))


def test_ranking_barra_horizontal_ordenada_com_rotulo_de_valor():
    spec = graficos.ranking([Contagem("Backend", 30), Contagem("Data", 10)], "Área").to_dict()

    barras, textos = spec["layer"]
    assert (_marca(barras), _marca(textos)) == ("bar", "text")
    assert barras["encoding"]["y"]["field"] == "Área"
    assert barras["encoding"]["y"]["sort"] == "-x"
    assert [linha["Rótulo"] for linha in _dados(spec)] == ["30 (75%)", "10 (25%)"]


def test_modalidade_e_uma_barra_empilhada_com_nao_informado_em_cinza_por_ultimo():
    contagens = [Contagem("Não informado", 50), Contagem("Presencial", 20),
                 Contagem("Remoto", 25), Contagem("Híbrido", 5)]
    spec = graficos.composicao_modalidade(contagens).to_dict()

    segmentos = spec["layer"][0]
    assert _marca(segmentos) == "bar"
    # uma barra so, numa banda de y com altura por passo (ver o teste abaixo)
    assert segmentos["encoding"]["y"]["field"] == "barra"
    assert {linha["barra"] for linha in _dados(spec)} == {"modalidade"}
    cor = segmentos["encoding"]["color"]["scale"]
    assert cor["domain"] == ["Remoto", "Híbrido", "Presencial", "Não informado"]
    assert cor["range"][-1] == graficos.CORES_MODALIDADE["Não informado"]
    linhas = _dados(spec)
    assert [linha["Modalidade"] for linha in linhas] == cor["domain"]
    assert linhas[0]["inicio"] == 0 and linhas[-1]["fim"] == pytest.approx(1)
    # 5% nao cabe no segmento: o valor fica so no tooltip
    assert [linha["rotulo"] for linha in linhas] == ["25%", "", "20%", "50%"]


@pytest.mark.parametrize("construtor", [
    lambda: graficos.composicao_modalidade([Contagem("Remoto", 1), Contagem("Não informado", 1)]),
    lambda: graficos.ranking([Contagem("Backend", 1)], "Área"),
    lambda: graficos.barras_percentuais(
        RankingTecnologias(base=1, vagas_ativas=1, itens=(Contagem("SQL", 1),))),
])
def test_barras_tem_altura_por_passo_e_nao_altura_total(construtor):
    """Com width="stretch" o Streamlit poe eixo e legenda dentro da altura total:
    com `height=48` a barra da modalidade sumia (so os rotulos apareciam)."""
    assert isinstance(construtor().to_dict()["height"], dict)  # {"step": N}


def test_modalidade_desconhecida_entra_antes_do_nao_informado():
    spec = graficos.composicao_modalidade(
        [Contagem("Não informado", 1), Contagem("Outra", 1), Contagem("Remoto", 1)]).to_dict()

    assert [linha["Modalidade"] for linha in _dados(spec)] == ["Remoto", "Outra", "Não informado"]


def test_vagas_abertas_e_linha_com_pontos():
    spec = graficos.linha_estoque(_tabela(), "Vagas abertas").to_dict()

    assert spec["mark"]["type"] == "line"
    assert "point" in spec["mark"]
    assert spec["encoding"]["x"]["type"] == "temporal"


def test_contagem_por_dia_e_coluna():
    spec = graficos.colunas_por_dia(_tabela(), "Vagas novas").to_dict()

    assert spec["mark"]["type"] == "bar"
    assert spec["encoding"]["x"]["type"] == "ordinal"
    assert spec["encoding"]["y"]["field"] == "Vagas novas"


def test_abertas_por_area_sao_small_multiples_com_escala_propria():
    spec = graficos.multiplos_por_area(SERIE).to_dict()

    assert spec["facet"]["field"] == "Área"
    # ordem pelo ultimo dia: Backend (7) antes de Data (5)
    assert spec["facet"]["sort"] == ["Backend", "Data"]
    assert spec["resolve"]["scale"]["y"] == "independent"
    assert spec["spec"]["mark"]["type"] == "line"
    assert "color" not in spec["spec"]["encoding"]  # nada de uma cor por area


def test_tabela_por_area_preenche_zero():
    serie = [PontoSerie(date(2026, 9, 20), 1, 1, 1, {"Backend": 1}),
             PontoSerie(date(2026, 9, 21), 1, 0, 0, {"Data": 1})]

    tabela = graficos.tabela_por_area(serie)

    assert len(tabela) == 4
    assert tabela["Vagas"].sum() == 2


def test_tecnologias_em_percentual_com_eixo_de_0_a_100():
    ranking = RankingTecnologias(base=40, vagas_ativas=50,
                                 itens=(Contagem("SQL", 20), Contagem("Python", 10)))
    spec = graficos.barras_percentuais(ranking).to_dict()

    barras = spec["layer"][0]
    assert _marca(barras) == "bar"
    assert barras["encoding"]["x"]["scale"]["domain"] == [0, 100]
    assert [linha["Rótulo"] for linha in _dados(spec)] == ["50% (20)", "25% (10)"]


CAMPOS_INTERNOS = {"inicio", "fim", "meio", "barra", "cor_texto", "rotulo", "Rótulo"}
CONSTRUTORES = {
    "ranking": lambda: graficos.ranking([Contagem("Backend", 1)], "Área"),
    "modalidade": lambda: graficos.composicao_modalidade(
        [Contagem("Remoto", 1), Contagem("Não informado", 1)]),
    "linha": lambda: graficos.linha_estoque(_tabela(), "Vagas abertas"),
    "colunas": lambda: graficos.colunas_por_dia(_tabela(), "Vagas novas"),
    "por_area": lambda: graficos.multiplos_por_area(SERIE),
    "percentuais": lambda: graficos.barras_percentuais(
        RankingTecnologias(base=1, vagas_ativas=1, itens=(Contagem("SQL", 1),))),
}


def _camadas(spec: dict) -> list[dict]:
    spec = spec.get("spec", spec)  # faceta
    return spec.get("layer", [spec])


@pytest.mark.parametrize("nome", CONSTRUTORES)
def test_toda_camada_tem_tooltip_so_com_campos_legiveis(nome):
    """Camada sem `tooltip` ganha o padrao do Streamlit, que lista todos os campos
    da marca: no rotulo da modalidade apareciam `meio`, `barra`, `cor_texto`..."""
    spec = CONSTRUTORES[nome]().to_dict()

    for camada in _camadas(spec):
        tooltip = camada["encoding"].get("tooltip")
        assert tooltip, f"camada {_marca(camada)} sem tooltip"
        campos = {t["field"] for t in (tooltip if isinstance(tooltip, list) else [tooltip])}
        assert not campos & CAMPOS_INTERNOS
