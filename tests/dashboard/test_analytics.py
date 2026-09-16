"""Analises do dashboard com dados conhecidos (cenario em tests/dashboard/cenario_historico.py).

Contra o schema das migrations (SQLite), sem rede e sem Streamlit.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("sqlalchemy")

from dashboard import config, consultas  # noqa: E402
from dashboard.consultas import Contagem, Filtros, PontoSerie  # noqa: E402

from cenario_historico import D1, D2, D3, D4  # noqa: E402

SEM_FILTRO = Filtros()


@pytest.fixture
def leitor(banco_com_historico):
    engine = config.criar_engine(banco_com_historico)
    yield engine
    engine.dispose()


@pytest.fixture
def leitor_vazio(banco_historico):
    engine = config.criar_engine(banco_historico)
    yield engine
    engine.dispose()


# --- fotografia atual ------------------------------------------------------


def test_indicadores_contam_vagas_unicas_ativas(leitor):
    indicadores = consultas.indicadores_atuais(leitor, SEM_FILTRO)

    # A (3 snapshots), C e D; B esta encerrada.
    assert indicadores == consultas.Indicadores(
        vagas_ativas=3, empresas=2, remotas=1, sem_modalidade=1, fontes=2)
    assert indicadores.percentual_remoto == pytest.approx(100 / 3)


def test_empresas_ignoram_maiusculas_e_espacos(leitor):
    # "Acme" (A) e " ACME" (D) sao a mesma empresa; "Beta" (C) e outra.
    assert consultas.indicadores_atuais(leitor, SEM_FILTRO).empresas == 2
    assert consultas.indicadores_atuais(leitor, Filtros(fontes=("gupy",))).empresas == 1


def test_distribuicao_usa_o_estado_atual_e_conta_cada_vaga_uma_vez(leitor):
    assert consultas.distribuicao(leitor, SEM_FILTRO, "area") == [
        Contagem("Data", 1), Contagem("Frontend", 1), Contagem("Suporte/Infra", 1),
    ]
    assert consultas.distribuicao(leitor, SEM_FILTRO, "modalidade") == [
        Contagem("Híbrido", 1), Contagem("Não informado", 1), Contagem("Remoto", 1),
    ]
    assert consultas.distribuicao(leitor, SEM_FILTRO, "fonte") == [
        Contagem("gupy", 2), Contagem("vagas", 1),
    ]


def test_dimensao_desconhecida_e_recusada(leitor):
    with pytest.raises(ValueError):
        consultas.distribuicao(leitor, SEM_FILTRO, "title")


@pytest.mark.parametrize("filtros, esperado", [
    (Filtros(fontes=("gupy",)), 2),
    (Filtros(fontes=("linkedin",)), 0),  # so tem a vaga encerrada
    (Filtros(areas=("Data",)), 1),
    (Filtros(areas=("Backend",)), 0),  # A ja nao e Backend
    (Filtros(modalidades=("Não informado",)), 1),
    (Filtros(fontes=("gupy",), modalidades=("Remoto",)), 1),
    (Filtros(fontes=("gupy", "vagas"), areas=("Data", "Suporte/Infra")), 2),
    (Filtros(fontes=("gupy' OR '1'='1",)), 0),
])
def test_cada_filtro_muda_a_fotografia(leitor, filtros, esperado):
    assert consultas.indicadores_atuais(leitor, filtros).vagas_ativas == esperado
    assert sum(c.vagas for c in consultas.distribuicao(leitor, filtros, "area")) == esperado


def test_periodo_nao_muda_a_fotografia_atual(leitor):
    assert (consultas.indicadores_atuais(leitor, Filtros(inicio=D1, fim=D1))
            == consultas.indicadores_atuais(leitor, SEM_FILTRO))


def test_opcoes_de_filtro_vem_do_banco(leitor):
    assert consultas.opcoes_filtro(leitor) == consultas.OpcoesFiltro(
        fontes=("gupy", "linkedin", "vagas"),
        areas=("Backend", "Data", "Frontend", "Suporte/Infra"),
        modalidades=("Remoto", "Híbrido", "Presencial", "Não informado"),
        primeiro_dia=D1,
        ultimo_dia=D3,  # a execucao que falhou em D4 nao conta
    )


# --- serie historica ---------------------------------------------------------


def test_serie_por_dia_de_coleta(leitor):
    assert consultas.serie_historica(leitor, SEM_FILTRO) == [
        PontoSerie(D1, abertas=2, novas=2, snapshots=2,
                   abertas_por_area={"Backend": 1, "Data": 1}),
        PontoSerie(D2, abertas=3, novas=1, snapshots=2,
                   abertas_por_area={"Backend": 1, "Data": 1, "Suporte/Infra": 1}),
        # B foi encerrada em D3; A virou Data.
        PontoSerie(D3, abertas=3, novas=1, snapshots=2,
                   abertas_por_area={"Data": 1, "Suporte/Infra": 1, "Frontend": 1}),
    ]


def test_serie_diferencia_vagas_unicas_de_snapshots(leitor):
    serie = consultas.serie_historica(leitor, Filtros(fontes=("gupy",), areas=("Backend", "Data")))
    # Só a vaga A: aberta nos três dias, nova uma vez, com um snapshot por dia.
    assert [(p.abertas, p.novas, p.snapshots) for p in serie] == [(1, 1, 1), (1, 0, 1), (1, 0, 1)]


def test_serie_usa_o_estado_vigente_em_cada_dia(leitor):
    backend = consultas.serie_historica(leitor, Filtros(areas=("Backend",)))
    assert [(p.dia, p.abertas, p.snapshots) for p in backend] == [(D1, 1, 1), (D2, 1, 1), (D3, 0, 0)]

    data = consultas.serie_historica(leitor, Filtros(areas=("Data",)))
    # D1 e D2: B; D3: A mudou para Data e B foi encerrada.
    assert [(p.dia, p.abertas, p.snapshots) for p in data] == [(D1, 1, 1), (D2, 1, 0), (D3, 1, 1)]


def test_serie_filtra_fonte_e_modalidade(leitor):
    linkedin = consultas.serie_historica(leitor, Filtros(fontes=("linkedin",)))
    assert [p.abertas for p in linkedin] == [1, 1, 0]

    sem_modalidade = consultas.serie_historica(leitor, Filtros(modalidades=("Não informado",)))
    assert [(p.abertas, p.novas, p.snapshots) for p in sem_modalidade] == [(0, 0, 0), (1, 1, 1), (1, 0, 0)]


def test_periodo_recorta_os_dias_de_coleta(leitor):
    assert [p.dia for p in consultas.serie_historica(leitor, Filtros(inicio=D2, fim=D3))] == [D2, D3]
    assert consultas.serie_historica(leitor, Filtros(inicio=D2, fim=D2)) == [
        PontoSerie(D2, 3, 1, 2, {"Backend": 1, "Data": 1, "Suporte/Infra": 1}),
    ]


@pytest.mark.parametrize("inicio, fim", [
    (D4, D4),  # so a execucao que falhou
    (date(2026, 10, 1), date(2026, 10, 31)),
    (date(2026, 9, 11), date(2026, 9, 11)),  # dia entre coletas
])
def test_periodo_sem_coleta_devolve_serie_vazia(leitor, inicio, fim):
    assert consultas.serie_historica(leitor, Filtros(inicio=inicio, fim=fim)) == []


# --- vagas -------------------------------------------------------------------


def test_listar_vagas_ativas_paginado(leitor):
    primeira = consultas.listar_vagas(leitor, SEM_FILTRO, pagina=1, por_pagina=2)
    assert primeira.total == 3
    assert primeira.paginas == 2
    assert [v.titulo for v in primeira.linhas] == ["Engenheiro de Dados Jr", "Suporte N1"]

    segunda = consultas.listar_vagas(leitor, SEM_FILTRO, pagina=2, por_pagina=2)
    assert [v.titulo for v in segunda.linhas] == ["Dev Frontend Jr"]

    alem = consultas.listar_vagas(leitor, SEM_FILTRO, pagina=5, por_pagina=2)
    assert alem.total == 3 and alem.linhas == ()


def test_listar_vagas_traz_estado_atual_e_ultimo_avistamento(leitor):
    todas = consultas.listar_vagas(leitor, SEM_FILTRO, somente_ativas=False)
    assert todas.total == 4
    ultima = todas.linhas[-1]  # B, vista por ultimo em D2
    assert (ultima.titulo, ultima.ativa, ultima.ultimo_avistamento.date()) == (
        "Analista de Dados Jr", False, D2)
    assert ultima.url is None  # javascript: nunca vira link

    vaga_a = todas.linhas[0]
    assert (vaga_a.area, vaga_a.modalidade, vaga_a.url) == (
        "Data", "Remoto", "https://portal.exemplo/vagas/a")
    assert vaga_a.primeiro_avistamento.tzinfo is not None


@pytest.mark.parametrize("filtros, somente_ativas, esperado", [
    (Filtros(inicio=D1, fim=D1), False, {"A", "B"}),
    (Filtros(inicio=D1, fim=D1), True, {"A"}),
    (Filtros(inicio=D3, fim=D3), True, {"A", "C", "D"}),
    (Filtros(inicio=D4, fim=D4), True, set()),
    (Filtros(areas=("Data",)), False, {"A", "B"}),
    (Filtros(fontes=("vagas",), modalidades=("Não informado",)), True, {"C"}),
])
def test_filtros_da_lista_de_vagas(leitor, filtros, somente_ativas, esperado):
    titulos = {"Engenheiro de Dados Jr": "A", "Analista de Dados Jr": "B",
               "Suporte N1": "C", "Dev Frontend Jr": "D"}
    pagina = consultas.listar_vagas(leitor, filtros, somente_ativas=somente_ativas)
    assert {titulos[v.titulo] for v in pagina.linhas} == esperado
    assert pagina.total == len(esperado)


@pytest.mark.parametrize("url, esperado", [
    ("https://portal.exemplo/v/1", "https://portal.exemplo/v/1"),
    ("  http://portal.exemplo/v/1 ", "http://portal.exemplo/v/1"),
    ("javascript:alert(1)", None),
    ("JavaScript:alert(1)", None),
    ("data:text/html,<script>alert(1)</script>", None),
    ("/vagas/1", None),
    ("https:///sem-host", None),
    ("", None),
    (None, None),
])
def test_url_segura(url, esperado):
    assert consultas.url_segura(url) == esperado


# --- tecnologias ---------------------------------------------------------------


def test_tecnologias_do_estado_atual_das_ativas(leitor):
    ranking = consultas.top_tecnologias(leitor, SEM_FILTRO)
    # Java so aparece num snapshot antigo de A e na vaga encerrada B.
    assert ranking == consultas.RankingTecnologias(
        base=2, vagas_ativas=3, itens=(Contagem("SQL", 2), Contagem("Python", 1)))
    assert not ranking.confiavel


def test_tecnologias_respeitam_filtros(leitor):
    ranking = consultas.top_tecnologias(leitor, Filtros(fontes=("gupy",)))
    assert (ranking.base, ranking.vagas_ativas) == (1, 2)
    assert ranking.itens == (Contagem("Python", 1), Contagem("SQL", 1))


def test_ranking_confiavel_a_partir_da_base_minima():
    base = consultas.BASE_MINIMA_TECNOLOGIAS
    assert consultas.RankingTecnologias(base, base, ()).confiavel
    assert not consultas.RankingTecnologias(base - 1, base, ()).confiavel


# --- zero dados --------------------------------------------------------------------


def test_banco_vazio_da_estado_vazio_em_todas_as_analises(leitor_vazio):
    indicadores = consultas.indicadores_atuais(leitor_vazio, SEM_FILTRO)
    assert indicadores == consultas.Indicadores(0, 0, 0, 0, 0)
    assert indicadores.percentual_remoto is None

    assert consultas.distribuicao(leitor_vazio, SEM_FILTRO, "area") == []
    assert consultas.serie_historica(leitor_vazio, SEM_FILTRO) == []
    assert consultas.listar_vagas(leitor_vazio, SEM_FILTRO).total == 0
    assert consultas.top_tecnologias(leitor_vazio, SEM_FILTRO) == consultas.RankingTecnologias(0, 0, ())
    assert consultas.opcoes_filtro(leitor_vazio) == consultas.OpcoesFiltro((), (), (), None, None)


def test_analises_sem_schema_viram_dados_indisponiveis(tmp_path):
    arquivo = tmp_path / "vazio.db"
    arquivo.touch()
    engine = config.criar_engine(arquivo)
    try:
        for chamada in (
            lambda: consultas.opcoes_filtro(engine),
            lambda: consultas.indicadores_atuais(engine, SEM_FILTRO),
            lambda: consultas.serie_historica(engine, SEM_FILTRO),
            lambda: consultas.listar_vagas(engine, SEM_FILTRO),
            lambda: consultas.top_tecnologias(engine, SEM_FILTRO),
        ):
            with pytest.raises(consultas.DadosIndisponiveis) as erro:
                chamada()
            assert "vazio.db" not in str(erro.value)
    finally:
        engine.dispose()
