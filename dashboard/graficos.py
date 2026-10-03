"""Graficos do dashboard: cada funcao recebe dados prontos e devolve um `alt.Chart`.

A forma de cada grafico segue a tarefa do leitor, e nao um estilo unico. O estudo
com o metodo e a bibliografia esta em `docs/graficos.md`; em resumo:

- **ranking de categorias** (area, fonte, tecnologia): barra horizontal ordenada,
  uma cor so (comprimento e o canal mais preciso; a cor repetiria o comprimento);
- **parte-todo com poucas partes** (modalidade): uma barra 100% empilhada, tons de
  um azul na ordem Remoto -> Hibrido -> Presencial e "Não informado" em cinza,
  porque e ausencia de dado e nao uma modalidade;
- **parte-todo por grupo** (modalidade por fonte): uma barra 100% por fonte, com
  as mesmas cores, ordenada pela fracao de "Não informado";
- **estoque ao longo do tempo** (vagas abertas): linha com ponto em cada dia de coleta;
- **contagem por dia** (vagas novas, snapshots): colunas, um evento discreto por dia;
- **muitas series no tempo** (abertas por area): small multiples, nao 17 cores.

Sem acesso ao banco e sem Streamlit: as paginas chamam `st.altair_chart` com o
retorno, passando o tema do leitor ("claro" ou "escuro", que escolhe a `Paleta`),
e os testes inspecionam `chart.to_dict()`.
"""

from __future__ import annotations

from dataclasses import dataclass

import altair as alt
import pandas as pd

from dashboard.consultas import Contagem, ContagemCruzada, PontoSerie, RankingTecnologias
from scraper.models import NAO_INFORMADO, WORKPLACE_ORDER

# Cores por tema (docs/graficos.md, secao "Cor"). O dashboard nao fixa tema: o
# leitor ve o fundo claro ou o escuro do Streamlit, e o fundo limita a claridade
# que cada cor pode ter (Datawrapper, "colors for data vis style guides"). Uma
# paleta so para os dois fundos ficaria presa entre L* 41 e 62, estreito demais
# para tres tons e um cinza; dai uma paleta por tema. Regras, travadas em
# `tests/dashboard/test_graficos.py`: marca com >= 3:1 contra o fundo, texto com
# >= 4,5:1, vizinhos da rampa a >= 10 L* e cinzas a >= 8 L* de cada tom, para
# continuarem distintos em tons de cinza e para daltonicos.
FUNDOS = {"claro": "#ffffff", "escuro": "#0e1117"}
TINTAS_TEXTO = ("#ffffff", "#0b0b0b")


@dataclass(frozen=True)
class Paleta:
    serie: str  # serie unica
    rotulo: str  # valor escrito na ponta da barra (e texto: >= 4,5:1)
    # Rampa ordinal de um azul, do maior para o menor contraste com o fundo:
    # Remoto > Híbrido > Presencial. "Não informado" fica no cinza, fora da rampa,
    # porque e ausencia de dado e nao uma modalidade.
    modalidade: dict[str, str]
    # Modalidade fora do dominio (a checagem de qualidade ja alerta): outro cinza,
    # para nao se confundir com "Não informado".
    modalidade_desconhecida: str

    def cor_modalidade(self, modalidade: str) -> str:
        return self.modalidade.get(modalidade, self.modalidade_desconhecida)


PALETAS = {
    # A serie unica e o mesmo azul dos PNGs (`scraper/charts.py`): 4,4:1 no claro
    # e 4,3:1 no escuro, entao nao precisa de versao por tema.
    "claro": Paleta(
        serie="#2a78d6",
        rotulo="#5f5d58",
        modalidade={
            WORKPLACE_ORDER[0]: "#0d3b73",  # Remoto
            WORKPLACE_ORDER[1]: "#18539c",  # Híbrido
            WORKPLACE_ORDER[2]: "#2f74c8",  # Presencial
            NAO_INFORMADO: "#8f8d86",
        },
        modalidade_desconhecida="#4d4c48",
    ),
    # No escuro a rampa se inverte: o Remoto continua o tom de maior contraste,
    # agora o mais claro. O azul escuro do tema claro sumiria no fundo (2,3:1).
    "escuro": Paleta(
        serie="#2a78d6",
        rotulo="#a8a6a0",
        modalidade={
            WORKPLACE_ORDER[0]: "#c3dcfa",  # Remoto
            WORKPLACE_ORDER[1]: "#86b6ef",  # Híbrido
            WORKPLACE_ORDER[2]: "#4d8fe0",  # Presencial
            NAO_INFORMADO: "#77756f",
        },
        modalidade_desconhecida="#a3a19b",
    ),
}


def paleta(tema: str | None) -> Paleta:
    """A paleta do tema; sem tema conhecido, a clara (o padrao do Streamlit)."""
    return PALETAS.get(tema or "", PALETAS["claro"])


def _luminancia(cor: str) -> float:
    """Luminancia relativa da WCAG 2.1."""
    canais = (int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canais)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(cor_a: str, cor_b: str) -> float:
    """Razao de contraste da WCAG 2.1, de 1 a 21."""
    clara, escura = sorted((_luminancia(cor_a), _luminancia(cor_b)), reverse=True)
    return (clara + 0.05) / (escura + 0.05)


def tinta_sobre(cor: str) -> str:
    """Branco ou quase preto, o que contrastar mais com a cor do segmento."""
    return max(TINTAS_TEXTO, key=lambda tinta: contraste(tinta, cor))


# Segmento menor que isso nao ganha rotulo (nao cabe); o valor fica no tooltip.
FRACAO_MINIMA_ROTULO = 0.06
VAO_SEGMENTO = 0.004  # fracao da barra, ~2px numa coluna do dashboard

# Alturas por passo (px por categoria), nunca altura total: com `width="stretch"` o
# Streamlit encaixa eixos e legenda DENTRO da altura total declarada, e o que sobra
# para as barras pode chegar a zero (ver `composicao_modalidade`).
ALTURA_BARRA = 24  # px por categoria nas barras horizontais
ALTURA_BARRA_TECNOLOGIA = 28
ALTURA_BARRA_MODALIDADE = 36  # px da banda da barra empilhada
ALTURA_BARRA_FONTE = 30  # px por fonte na modalidade por fonte
FORMATO_DIA = "%d/%m"


def _percentual(parte: float, total: float) -> str:
    return f"{100 * parte / total:.0f}%" if total else "—"


def ranking(contagens: list[Contagem], rotulo: str, valor: str = "Vagas",
            tema: str | None = None) -> alt.LayerChart:
    """Barras horizontais ordenadas, com "N (P%)" na ponta de cada barra."""
    cores = paleta(tema)
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
    barras = base.mark_bar(color=cores.serie, cornerRadiusEnd=4)
    textos = base.mark_text(align="left", dx=4, color=cores.rotulo).encode(text="Rótulo:N")
    return (barras + textos).properties(height=alt.Step(ALTURA_BARRA))


def _ordem_modalidades(presentes) -> list[str]:
    """Remoto, Híbrido, Presencial, as fora do dominio e, por ultimo, Não informado."""
    ordem = [m for m in WORKPLACE_ORDER if m != NAO_INFORMADO]
    ordem += sorted(m for m in presentes if m not in WORKPLACE_ORDER)
    ordem.append(NAO_INFORMADO)
    return ordem


def _segmentos(vagas: dict[str, int], barra: str, cores: Paleta) -> list[dict]:
    """Segmentos de uma barra 100%: inicio, fim e rotulo de cada modalidade presente."""
    total = sum(vagas.values())
    linhas, inicio = [], 0.0
    for modalidade in _ordem_modalidades(vagas):
        quantidade = vagas.get(modalidade, 0)
        if not quantidade:
            continue
        fracao = quantidade / total
        linhas.append({
            "barra": barra,
            "Modalidade": modalidade,
            "Vagas": quantidade,
            "Percentual": _percentual(quantidade, total),
            "inicio": inicio,
            # vao entre segmentos pelo proprio fundo, nos temas claro e escuro
            "fim": inicio + fracao - VAO_SEGMENTO,
            "meio": inicio + fracao / 2,
            "rotulo": _percentual(quantidade, total) if fracao >= FRACAO_MINIMA_ROTULO else "",
            "cor_texto": tinta_sobre(cores.cor_modalidade(modalidade)),
        })
        inicio += fracao
    if linhas:
        linhas[-1]["fim"] = 1.0  # o ultimo segmento fecha a barra
    return linhas


def _barras_100(tabela: pd.DataFrame, y: alt.Y, tooltip: list, altura: int,
                cores: Paleta) -> alt.LayerChart:
    """Barras 100% empilhadas por modalidade, uma por valor de `y`, com % no segmento."""
    presentes = [m for m in _ordem_modalidades(set(tabela["Modalidade"]))
                 if m in set(tabela["Modalidade"])]
    escala = alt.Scale(domain=presentes, range=[cores.cor_modalidade(m) for m in presentes])
    # A barra ocupa uma banda de `y` com altura por passo, e nao uma altura total
    # fixa: com `width="stretch"` o Streamlit encaixa eixo e legenda DENTRO da
    # altura declarada, e com `height=48` a area da barra ficava com ~0 px -- so
    # os rotulos apareciam (visto no Streamlit; o vl-convert nao reproduz).
    # O tooltip fica no base para valer tambem no rotulo: sem ele, o Streamlit
    # mostra ao passar o mouse todos os campos internos da marca (meio, cor_texto...).
    base = alt.Chart(tabela).encode(y=y, tooltip=tooltip)
    segmentos = base.mark_bar().encode(
        x=alt.X("inicio:Q", title=None, scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%", tickCount=5)),
        x2="fim:Q",
        color=alt.Color("Modalidade:N", scale=escala, sort=presentes,
                        legend=alt.Legend(orient="bottom", title=None)),
    )
    textos = base.mark_text(fontWeight="bold").encode(
        x="meio:Q",
        text="rotulo:N",
        color=alt.Color("cor_texto:N", scale=None),
    )
    return (segmentos + textos).properties(height=alt.Step(altura))


def composicao_modalidade(contagens: list[Contagem], tema: str | None = None) -> alt.LayerChart:
    """Uma barra 100% empilhada: Remoto, Híbrido, Presencial e, por ultimo, Não informado."""
    cores = paleta(tema)
    tabela = pd.DataFrame(_segmentos({c.rotulo: c.vagas for c in contagens}, "modalidade", cores))
    return _barras_100(
        tabela,
        y=alt.Y("barra:N", title=None, axis=None),
        tooltip=["Modalidade", "Vagas", "Percentual"],
        altura=ALTURA_BARRA_MODALIDADE,
        cores=cores,
    )


def modalidade_por_fonte(contagens: list[ContagemCruzada],
                         tema: str | None = None) -> alt.LayerChart:
    """Uma barra 100% por fonte, da que mais deixa de informar modalidade para a que menos.

    A pergunta e "de onde vem o Não informado", entao a ordem e a fracao dele, e
    nao o tamanho da fonte (que esta no ranking "Por fonte"). O total de cada
    fonte vai no rotulo do eixo, ja que a barra 100% o esconde.
    """
    cores = paleta(tema)
    por_fonte: dict[str, dict[str, int]] = {}
    for c in contagens:
        por_fonte.setdefault(c.grupo, {})[c.rotulo] = c.vagas

    def _chave(fonte: str) -> tuple[float, int, str]:
        vagas = por_fonte[fonte]
        total = sum(vagas.values())
        return (-vagas.get(NAO_INFORMADO, 0) / total, -total, fonte)

    linhas = []
    for fonte in sorted(por_fonte, key=_chave):
        rotulo = f"{fonte} (n={sum(por_fonte[fonte].values())})"
        linhas += [dict(linha, Fonte=fonte) for linha in _segmentos(por_fonte[fonte], rotulo, cores)]
    tabela = pd.DataFrame(linhas)
    ordem = list(dict.fromkeys(tabela["barra"]))
    return _barras_100(
        tabela,
        y=alt.Y("barra:N", title=None, sort=ordem, axis=alt.Axis(labelLimit=220)),
        tooltip=["Fonte", "Modalidade", "Vagas", "Percentual"],
        altura=ALTURA_BARRA_FONTE,
        cores=cores,
    )


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


def linha_estoque(tabela: pd.DataFrame, y: str, tema: str | None = None) -> alt.Chart:
    """Estoque no tempo: linha, com um ponto em cada dia que teve coleta."""
    azul = paleta(tema).serie
    return alt.Chart(tabela).mark_line(
        color=azul, strokeWidth=2, point=alt.OverlayMarkDef(color=azul, size=50),
    ).encode(
        x=_eixo_dia(),
        y=_eixo_contagem(y),
        tooltip=[alt.Tooltip("Dia:T", format="%d/%m/%Y"), y],
    )


def colunas_por_dia(tabela: pd.DataFrame, y: str, tema: str | None = None) -> alt.Chart:
    """Contagem de eventos no dia: colunas, uma por dia de coleta."""
    return alt.Chart(tabela).mark_bar(
        color=paleta(tema).serie, cornerRadiusTopLeft=3, cornerRadiusTopRight=3,
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


def multiplos_por_area(serie: list[PontoSerie], colunas: int = 3,
                       tema: str | None = None) -> alt.FacetChart:
    """Small multiples: um painel por area, na ordem das vagas abertas no ultimo dia.

    O eixo vertical e proprio de cada painel: a pergunta aqui e a forma da tendencia
    de cada area (o tamanho de cada uma esta na Overview). Com escala comum, as areas
    pequenas virariam uma linha reta no chao do painel.
    """
    tabela = tabela_por_area(serie)
    ultimo: dict[str, int] = serie[-1].abertas_por_area if serie else {}
    ordem = sorted(tabela["Área"].unique(), key=lambda a: (-ultimo.get(a, 0), a))
    azul = paleta(tema).serie
    return alt.Chart(tabela).mark_line(
        color=azul, strokeWidth=2, point=alt.OverlayMarkDef(color=azul, size=24),
    ).encode(
        x=_eixo_dia(),
        y=_eixo_contagem("Vagas"),
        tooltip=["Área", alt.Tooltip("Dia:T", format="%d/%m/%Y"), "Vagas"],
    ).properties(width=190, height=100).facet(
        facet=alt.Facet("Área:N", sort=ordem, title=None,
                        header=alt.Header(labelAnchor="start", labelFontWeight="bold")),
        columns=colunas,
    ).resolve_scale(y="independent")


def barras_percentuais(ranking_tecnologias: RankingTecnologias,
                       tema: str | None = None) -> alt.LayerChart:
    """Barras de % sobre a base, com eixo fixo de 0 a 100% para comparar paineis."""
    cores = paleta(tema)
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
    barras = base.mark_bar(color=cores.serie, cornerRadiusEnd=4)
    textos = base.mark_text(align="left", dx=4, color=cores.rotulo).encode(text="Rótulo:N")
    return (barras + textos).properties(height=alt.Step(ALTURA_BARRA_TECNOLOGIA))

