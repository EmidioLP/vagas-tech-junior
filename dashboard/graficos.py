"""Graficos do dashboard: cada funcao recebe dados prontos e devolve um `alt.Chart`.

A forma de cada grafico segue a tarefa do leitor, e nao um estilo unico. O estudo
com o metodo e a bibliografia esta em `docs/graficos.md`; em resumo:

- **ranking de categorias** (area, fonte, tecnologia): barra horizontal ordenada,
  uma cor so (comprimento e o canal mais preciso; a cor repetiria o comprimento);
- **parte-todo com poucas partes** (modalidade): uma barra 100% empilhada, tons de
  um azul na ordem Remoto -> Hibrido -> Presencial e "Não informado" em cinza,
  porque e ausencia de dado e nao uma modalidade;
- **estoque ao longo do tempo** (vagas abertas): linha com ponto em cada dia de coleta;
- **contagem por dia** (vagas novas, snapshots): colunas, um evento discreto por dia;
- **muitas series no tempo** (abertas por area): small multiples, nao 17 cores.

Sem acesso ao banco e sem Streamlit: as paginas chamam `st.altair_chart` com o
retorno, e os testes inspecionam `chart.to_dict()`.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from dashboard.consultas import Contagem, PontoSerie, RankingTecnologias
from scraper.models import NAO_INFORMADO, WORKPLACE_ORDER

# Serie unica: o mesmo azul dos PNGs (`scraper/charts.py`).
AZUL = "#2a78d6"
# Rotulos de valor: cinza medio, legivel no tema claro e no escuro do Streamlit.
TINTA_ROTULO = "#898781"
# Modalidade: rampa ordinal de um azul, validada nos dois temas (claro: fundo
# #fcfcfb, escuro: #0e1117). "Não informado" fica no cinza, fora da rampa.
CORES_MODALIDADE = {
    WORKPLACE_ORDER[0]: "#184f95",  # Remoto
    WORKPLACE_ORDER[1]: "#3987e5",  # Híbrido
    WORKPLACE_ORDER[2]: "#86b6ef",  # Presencial
    NAO_INFORMADO: "#898781",
}
# Modalidade fora do dominio (a checagem de qualidade ja alerta): cinza escuro,
# para nao se confundir com "Não informado".
COR_MODALIDADE_DESCONHECIDA = "#52514e"
# Texto dentro do segmento: escuro so no azul claro, onde o branco nao contrasta.
TEXTO_NO_SEGMENTO = {WORKPLACE_ORDER[2]: "#0b0b0b"}
# Segmento menor que isso nao ganha rotulo (nao cabe); o valor fica no tooltip.
FRACAO_MINIMA_ROTULO = 0.06
VAO_SEGMENTO = 0.004  # fracao da barra, ~2px numa coluna do dashboard

ALTURA_BARRA = 24  # px por categoria nas barras horizontais
FORMATO_DIA = "%d/%m"


def _percentual(parte: float, total: float) -> str:
    return f"{100 * parte / total:.0f}%" if total else "—"


def ranking(contagens: list[Contagem], rotulo: str, valor: str = "Vagas") -> alt.LayerChart:
    """Barras horizontais ordenadas, com "N (P%)" na ponta de cada barra."""
    total = sum(c.vagas for c in contagens)
    tabela = pd.DataFrame({
        rotulo: [c.rotulo for c in contagens],
        valor: [c.vagas for c in contagens],
        "Rótulo": [f"{c.vagas} ({_percentual(c.vagas, total)})" for c in contagens],
    })
    base = alt.Chart(tabela).encode(
        y=alt.Y(f"{rotulo}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X(f"{valor}:Q", title=None, axis=None,
                # folga a direita para o rotulo nao ser cortado
                scale=alt.Scale(domain=[0, max(tabela[valor].max(), 1) * 1.25])),
        tooltip=[rotulo, valor],
    )
    barras = base.mark_bar(color=AZUL, cornerRadiusEnd=4)
    textos = base.mark_text(align="left", dx=4, color=TINTA_ROTULO).encode(text="Rótulo:N")
    return (barras + textos).properties(height=ALTURA_BARRA * len(tabela) + 10)


def composicao_modalidade(contagens: list[Contagem]) -> alt.LayerChart:
    """Uma barra 100% empilhada: Remoto, Híbrido, Presencial e, por ultimo, Não informado."""
    ordem = [m for m in WORKPLACE_ORDER if m != NAO_INFORMADO]
    ordem += sorted(c.rotulo for c in contagens if c.rotulo not in WORKPLACE_ORDER)
    ordem.append(NAO_INFORMADO)
    vagas = {c.rotulo: c.vagas for c in contagens}
    total = sum(vagas.values())

    linhas, inicio = [], 0.0
    for modalidade in ordem:
        quantidade = vagas.get(modalidade, 0)
        if not quantidade:
            continue
        fracao = quantidade / total
        linhas.append({
            "Modalidade": modalidade,
            "Vagas": quantidade,
            "Percentual": _percentual(quantidade, total),
            "inicio": inicio,
            # vao entre segmentos pelo proprio fundo, nos temas claro e escuro
            "fim": inicio + fracao - VAO_SEGMENTO,
            "meio": inicio + fracao / 2,
            "rotulo": _percentual(quantidade, total) if fracao >= FRACAO_MINIMA_ROTULO else "",
            "cor_texto": TEXTO_NO_SEGMENTO.get(modalidade, "#ffffff"),
        })
        inicio += fracao
    linhas[-1]["fim"] = 1.0  # o ultimo segmento fecha a barra
    tabela = pd.DataFrame(linhas)

    presentes = list(tabela["Modalidade"])
    cores = alt.Scale(domain=presentes,
                      range=[CORES_MODALIDADE.get(m, COR_MODALIDADE_DESCONHECIDA)
                             for m in presentes])
    base = alt.Chart(tabela)
    segmentos = base.mark_bar().encode(
        x=alt.X("inicio:Q", title=None, scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%", tickCount=5)),
        x2="fim:Q",
        color=alt.Color("Modalidade:N", scale=cores, sort=presentes,
                        legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Modalidade", "Vagas", "Percentual"],
    )
    textos = base.mark_text(fontWeight="bold").encode(
        x="meio:Q",
        text="rotulo:N",
        color=alt.Color("cor_texto:N", scale=None),
    )
    return (segmentos + textos).properties(height=48)


def _eixo_dia() -> alt.X:
    # Marcas so em dias inteiros (sem o "meio-dia" que o Vega-Lite interpola) e,
    # nos paineis estreitos, rotulos que se sobrepoem sao omitidos.
    return alt.X("Dia:T", title=None, axis=alt.Axis(
        format=FORMATO_DIA, tickCount="day", labelOverlap="greedy", labelSeparation=8,
        grid=False))


def _eixo_contagem(campo: str, **axis) -> alt.Y:
    # Contagem de vagas: sem rotulo fracionario (0,5 vaga) nas escalas pequenas.
    # `tickMinStep` nao vale nos small multiples de escala independente, dai o
    # `labelExpr`, que apaga o rotulo de marca nao inteira.
    return alt.Y(f"{campo}:Q", title=None, axis=alt.Axis(
        format="d", tickMinStep=1, labelExpr="datum.value % 1 ? '' : datum.label", **axis))


def linha_estoque(tabela: pd.DataFrame, y: str) -> alt.Chart:
    """Estoque no tempo: linha, com um ponto em cada dia que teve coleta."""
    return alt.Chart(tabela).mark_line(
        color=AZUL, strokeWidth=2, point=alt.OverlayMarkDef(color=AZUL, size=50),
    ).encode(
        x=_eixo_dia(),
        y=_eixo_contagem(y),
        tooltip=[alt.Tooltip("Dia:T", format="%d/%m/%Y"), y],
    )


def colunas_por_dia(tabela: pd.DataFrame, y: str) -> alt.Chart:
    """Contagem de eventos no dia: colunas, uma por dia de coleta."""
    return alt.Chart(tabela).mark_bar(
        color=AZUL, cornerRadiusTopLeft=3, cornerRadiusTopRight=3,
    ).encode(
        x=alt.X("yearmonthdate(Dia):O", title=None,
                axis=alt.Axis(format=FORMATO_DIA, labelAngle=0)),
        y=_eixo_contagem(y),
        tooltip=[alt.Tooltip("Dia:T", format="%d/%m/%Y"), y],
    )


def tabela_por_area(serie: list[PontoSerie]) -> pd.DataFrame:
    """Uma linha por (dia, area), com zero onde a area nao tinha vaga aberta."""
    areas = sorted({a for p in serie for a in p.abertas_por_area})
    return pd.DataFrame(
        [{"Dia": pd.Timestamp(p.dia), "Área": area, "Vagas": p.abertas_por_area.get(area, 0)}
         for p in serie for area in areas],
        columns=["Dia", "Área", "Vagas"],
    )


def multiplos_por_area(serie: list[PontoSerie], colunas: int = 3) -> alt.FacetChart:
    """Small multiples: um painel por area, na ordem das vagas abertas no ultimo dia.

    O eixo vertical e proprio de cada painel: a pergunta aqui e a forma da tendencia
    de cada area (o tamanho de cada uma esta na Overview). Com escala comum, as areas
    pequenas virariam uma linha reta no chao do painel.
    """
    tabela = tabela_por_area(serie)
    ultimo: dict[str, int] = serie[-1].abertas_por_area if serie else {}
    ordem = sorted(tabela["Área"].unique(), key=lambda a: (-ultimo.get(a, 0), a))
    return alt.Chart(tabela).mark_line(
        color=AZUL, strokeWidth=2, point=alt.OverlayMarkDef(color=AZUL, size=24),
    ).encode(
        x=_eixo_dia(),
        y=_eixo_contagem("Vagas"),
        tooltip=["Área", alt.Tooltip("Dia:T", format="%d/%m/%Y"), "Vagas"],
    ).properties(width=190, height=100).facet(
        facet=alt.Facet("Área:N", sort=ordem, title=None,
                        header=alt.Header(labelAnchor="start", labelFontWeight="bold")),
        columns=colunas,
    ).resolve_scale(y="independent")


def barras_percentuais(ranking_tecnologias: RankingTecnologias) -> alt.LayerChart:
    """Barras de % sobre a base, com eixo fixo de 0 a 100% para comparar paineis."""
    base_vagas = ranking_tecnologias.base
    tabela = pd.DataFrame({
        "Tecnologia": [c.rotulo for c in ranking_tecnologias.itens],
        "% das vagas": [round(100 * c.vagas / base_vagas, 1) for c in ranking_tecnologias.itens],
        "Vagas": [c.vagas for c in ranking_tecnologias.itens],
    })
    tabela["Rótulo"] = [f"{p:.0f}% ({v})" for p, v in zip(tabela["% das vagas"], tabela["Vagas"])]
    base = alt.Chart(tabela).encode(
        x=alt.X("% das vagas:Q", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("Tecnologia:N", sort="-x", title=None),
        tooltip=["Tecnologia", "% das vagas", "Vagas"],
    )
    barras = base.mark_bar(color=AZUL, cornerRadiusEnd=4)
    textos = base.mark_text(align="left", dx=4, color=TINTA_ROTULO).encode(text="Rótulo:N")
    return (barras + textos).properties(height=28 * len(tabela) + 40)

