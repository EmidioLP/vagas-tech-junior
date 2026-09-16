"""Paginas do dashboard. So apresentam: os dados vem de `dashboard.consultas`.

Cada pagina recebe um `Dados`, com as consultas ja embrulhadas em cache pelo
`app.py`. Assim as paginas nao conhecem o engine, e os testes trocam as consultas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from dashboard.consultas import (
    BASE_MINIMA_TECNOLOGIAS,
    Contagem,
    DadosIndisponiveis,
    Filtros,
    Indicadores,
    OpcoesFiltro,
    PaginaVagas,
    PontoSerie,
    RankingTecnologias,
    ResumoGeral,
)

# Horario de Brasilia fixo: o Brasil nao tem horario de verao desde 2019, e
# `zoneinfo` no Windows exigiria o pacote tzdata.
BRASILIA = timezone(timedelta(hours=-3), "BRT")

ROTULOS_STATUS = {
    "success": "sucesso",
    "partial": "parcial",
    "failed": "falhou",
    "skipped": "pulada",
}
ROTULOS_GATILHO = {"schedule": "agendada", "manual": "manual", "local": "local"}

# Chaves fixas no session_state: a selecao sobrevive a troca de pagina (app.py).
CHAVE_FONTES = "filtro_fontes"
CHAVE_AREAS = "filtro_areas"
CHAVE_MODALIDADES = "filtro_modalidades"
CHAVE_PERIODO = "filtro_periodo"
CHAVE_SOMENTE_ATIVAS = "filtro_somente_ativas"
CHAVE_PAGINA = "vagas_pagina"
CHAVES_FILTRO = (CHAVE_FONTES, CHAVE_AREAS, CHAVE_MODALIDADES, CHAVE_PERIODO, CHAVE_SOMENTE_ATIVAS)

VAGAS_POR_PAGINA = 50

LEGENDA_HISTORICO = """
- **Vaga única** é uma linha de `jobs`: a mesma vaga do mesmo portal, contada uma
  vez, não importa em quantas coletas apareceu.
- **Snapshot** é uma observação gravada em `job_snapshots`. O pipeline só grava
  quando algo na vaga muda (título, área, modalidade, descrição, tecnologias…).
  Por isso, **snapshots por dia contam mudanças, não vagas vistas**: uma vaga que
  segue igual não gera snapshot novo.
- **Vagas abertas** num dia: vistas pela primeira vez até aquele dia e não
  encerradas até o fim dele. Uma vaga é encerrada quando some da listagem em duas
  coletas completas seguidas, em dias diferentes.
- **Área e modalidade** de cada vaga num dia vêm do snapshot vigente naquele dia.
  Uma vaga que mudou de Backend para Data conta em Backend antes da mudança e em
  Data depois.
- **Dias de coleta** são dias em UTC com execução bem-sucedida ou parcial. Dias sem
  coleta não aparecem, e a linha liga um dia de coleta ao seguinte.
- **Limitação:** se uma vaga encerrada reaparece, o encerramento anterior não fica
  registrado, e ela aparece aberta o tempo todo.
"""


@dataclass(frozen=True)
class Dados:
    resumo: Callable[[], ResumoGeral]
    opcoes: Callable[[], OpcoesFiltro]
    indicadores: Callable[[Filtros], Indicadores]
    distribuicao: Callable[[Filtros, str], list[Contagem]]
    serie: Callable[[Filtros], list[PontoSerie]]
    vagas: Callable[[Filtros, bool, int], PaginaVagas]
    tecnologias: Callable[[Filtros], RankingTecnologias]


def formatar_data(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def formatar_data_hora(momento: datetime) -> str:
    local = momento.astimezone(BRASILIA)
    return f"{local:%d/%m/%Y} às {local:%H:%M}"


def formatar_inteiro(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def formatar_percentual(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"{valor:.1f}%".replace(".", ",")


def frase_agenda(resumo: ResumoGeral) -> str | None:
    """O mesmo texto da CLI. Datas da agenda em UTC, como `next_run_on`."""
    if resumo.proxima_coleta is None:
        return None
    if resumo.ultima_coleta is None:
        ultima = "nenhuma registrada"
    else:
        ultima = f"dia {formatar_data(resumo.ultima_coleta.iniciada_em.astimezone(timezone.utc).date())}"
    return f"Última coleta: {ultima} e próxima: dia {formatar_data(resumo.proxima_coleta)}"


def _aviso_indisponivel(exc: DadosIndisponiveis) -> None:
    st.warning("Dados indisponíveis no momento. Tente de novo em alguns minutos.")
    st.caption(str(exc))


def _intervalo_coletas(opcoes: OpcoesFiltro) -> str:
    if opcoes.primeiro_dia is None:
        return "Ainda não há coleta registrada."
    return (f"Há coletas de {formatar_data(opcoes.primeiro_dia)} "
            f"a {formatar_data(opcoes.ultimo_dia)}.")


def _selecao(rotulo: str, chave: str, opcoes: tuple[str, ...]) -> tuple[str, ...]:
    # Um valor que sumiu do banco quebraria o multiselect: fica so o que existe.
    if chave in st.session_state:
        st.session_state[chave] = [v for v in st.session_state[chave] if v in opcoes]
    return tuple(st.sidebar.multiselect(rotulo, opcoes, key=chave, placeholder="Todas"))


def _periodo(opcoes: OpcoesFiltro) -> tuple[date | None, date | None]:
    if opcoes.primeiro_dia is None:
        st.sidebar.caption("Período: ainda não há coleta registrada.")
        return None, None
    if CHAVE_PERIODO not in st.session_state:
        st.session_state[CHAVE_PERIODO] = (opcoes.primeiro_dia, opcoes.ultimo_dia)
    valor = st.sidebar.date_input(
        "Período (dias em UTC)", key=CHAVE_PERIODO, format="DD/MM/YYYY",
        help="Os dois dias entram inteiros.",
    )
    st.sidebar.caption(_intervalo_coletas(opcoes))
    if isinstance(valor, date):
        return valor, valor
    if len(valor) == 2:
        return valor[0], valor[1]
    if len(valor) == 1:  # o usuario ainda esta escolhendo o fim
        return valor[0], valor[0]
    return None, None


def filtros_barra_lateral(opcoes: OpcoesFiltro, com_periodo: bool) -> Filtros:
    st.sidebar.header("Filtros")
    fontes = _selecao("Fonte", CHAVE_FONTES, opcoes.fontes)
    areas = _selecao("Área", CHAVE_AREAS, opcoes.areas)
    modalidades = _selecao("Modalidade", CHAVE_MODALIDADES, opcoes.modalidades)
    inicio, fim = _periodo(opcoes) if com_periodo else (None, None)
    if not com_periodo:
        st.sidebar.caption("O período não se aplica aqui: esta página é a fotografia atual.")
    return Filtros(fontes, areas, modalidades, inicio, fim)


def _barras(contagens: list[Contagem], rotulo: str, valor: str = "Vagas") -> None:
    tabela = pd.DataFrame({rotulo: [c.rotulo for c in contagens],
                           valor: [c.vagas for c in contagens]})
    st.bar_chart(tabela, x=rotulo, y=valor, horizontal=True, sort=f"-{valor}")


def overview(dados: Dados) -> None:
    st.title("Vagas Tech Júnior")
    st.write(
        "Qual área de tecnologia mais contrata júnior no Brasil, com dados "
        "coletados de portais públicos de vagas."
    )

    try:
        resumo = dados.resumo()
    except DadosIndisponiveis as exc:
        _aviso_indisponivel(exc)
        return

    if resumo.vazio:
        st.info(
            "Ainda não há coleta registrada. Os números aparecem depois da "
            "primeira coleta completa."
        )
        return

    st.metric(
        "Última coleta",
        formatar_data_hora(resumo.ultima_coleta.iniciada_em) if resumo.ultima_coleta else "—",
    )
    frase = frase_agenda(resumo)
    if frase:
        st.markdown(f"**{frase}**")

    execucao = resumo.ultima_execucao
    if execucao is not None:
        st.caption(
            f"Última execução: {ROTULOS_STATUS.get(execucao.status, execucao.status)} "
            f"({ROTULOS_GATILHO.get(execucao.gatilho, execucao.gatilho)}) em "
            f"{formatar_data_hora(execucao.iniciada_em)}."
        )
    st.caption(
        "Horários de Brasília; datas da agenda de coleta em UTC. "
        "Os números são atualizados a cada 10 minutos."
    )

    st.header("Fotografia atual")
    st.caption(
        "Vagas únicas ativas agora, com a área e a modalidade da observação mais "
        "recente. Para a evolução ao longo das coletas, veja **Histórico**."
    )
    try:
        filtros = filtros_barra_lateral(dados.opcoes(), com_periodo=False)
        indicadores = dados.indicadores(filtros)
        if indicadores.vagas_ativas:
            distribuicoes = {d: dados.distribuicao(filtros, d) for d in ("area", "modalidade", "fonte")}
    except DadosIndisponiveis as exc:
        _aviso_indisponivel(exc)
        return

    if indicadores.vagas_ativas == 0:
        st.info("Nenhuma vaga ativa com esses filtros. Remova algum filtro na barra lateral.")
        return

    kpi_vagas, kpi_empresas, kpi_remoto, kpi_fontes = st.columns(4)
    kpi_vagas.metric(
        "Vagas ativas", formatar_inteiro(indicadores.vagas_ativas),
        help="Vagas únicas (`jobs`) ainda abertas. Cada vaga conta uma vez, "
             "não importa quantos snapshots tenha.",
    )
    kpi_empresas.metric(
        "Empresas", formatar_inteiro(indicadores.empresas),
        help="Empresas distintas entre as vagas ativas (nome sem diferença de "
             "maiúsculas). Vagas sem empresa informada não contam.",
    )
    kpi_remoto.metric(
        "Remoto", formatar_percentual(indicadores.percentual_remoto),
        help="Vagas ativas com modalidade Remoto sobre todas as vagas ativas, "
             "inclusive as que não informam modalidade.",
    )
    kpi_fontes.metric(
        "Fontes", formatar_inteiro(indicadores.fontes),
        help="Portais com pelo menos uma vaga ativa.",
    )
    st.caption(
        f"{formatar_inteiro(indicadores.sem_modalidade)} das "
        f"{formatar_inteiro(indicadores.vagas_ativas)} vagas ativas não informam modalidade."
    )

    coluna_area, coluna_modalidade, coluna_fonte = st.columns(3)
    with coluna_area:
        st.subheader("Por área")
        _barras(distribuicoes["area"], "Área")
    with coluna_modalidade:
        st.subheader("Por modalidade")
        _barras(distribuicoes["modalidade"], "Modalidade")
    with coluna_fonte:
        st.subheader("Por fonte")
        _barras(distribuicoes["fonte"], "Fonte")
    st.caption("Contagens de vagas únicas ativas, não de snapshots.")


def historico(dados: Dados) -> None:
    st.title("Histórico")
    st.write(
        "Como as vagas evoluíram entre as coletas. Só é possível porque cada "
        "coleta preserva o que foi observado."
    )

    try:
        opcoes = dados.opcoes()
        filtros = filtros_barra_lateral(opcoes, com_periodo=True)
        serie = dados.serie(filtros)
    except DadosIndisponiveis as exc:
        _aviso_indisponivel(exc)
        return

    if not serie:
        st.info(f"Nenhuma coleta no período selecionado. {_intervalo_coletas(opcoes)}")
    elif not any(p.abertas or p.novas or p.snapshots for p in serie):
        st.info("Há coletas no período, mas nenhuma vaga com esses filtros. "
                "Remova algum filtro na barra lateral.")
    elif len(serie) == 1:
        ponto = serie[0]
        st.info(
            f"Só há um dia de coleta no período ({formatar_data(ponto.dia)}): uma "
            "tendência precisa de pelo menos dois. Os números desse dia:"
        )
        abertas, novas, snapshots = st.columns(3)
        abertas.metric("Vagas abertas (únicas)", formatar_inteiro(ponto.abertas))
        novas.metric("Vagas novas (únicas)", formatar_inteiro(ponto.novas))
        snapshots.metric("Snapshots gravados", formatar_inteiro(ponto.snapshots))
    else:
        _graficos_historico(serie)

    with st.expander("Como ler estes números"):
        st.markdown(LEGENDA_HISTORICO)


def _graficos_historico(serie: list[PontoSerie]) -> None:
    dias = pd.to_datetime([p.dia for p in serie])
    tabela = pd.DataFrame({
        "Dia": dias,
        "Vagas abertas": [p.abertas for p in serie],
        "Vagas novas": [p.novas for p in serie],
        "Snapshots": [p.snapshots for p in serie],
    })

    st.subheader("Vagas abertas (únicas)")
    st.line_chart(tabela, x="Dia", y="Vagas abertas")

    st.subheader("Vagas abertas por área (únicas)")
    por_area = pd.DataFrame(
        [{"Dia": dia, "Área": area, "Vagas": p.abertas_por_area.get(area, 0)}
         for dia, p in zip(dias, serie)
         for area in sorted({a for q in serie for a in q.abertas_por_area})]
    )
    st.line_chart(por_area, x="Dia", y="Vagas", color="Área")

    coluna_novas, coluna_snapshots = st.columns(2)
    with coluna_novas:
        st.subheader("Vagas novas (únicas)")
        st.line_chart(tabela, x="Dia", y="Vagas novas")
        st.caption("Vagas vistas pela primeira vez no dia.")
    with coluna_snapshots:
        st.subheader("Snapshots gravados")
        st.line_chart(tabela, x="Dia", y="Snapshots")
        st.caption("Mudanças de estado observadas no dia. Não são vagas.")


def vagas(dados: Dados) -> None:
    st.title("Vagas")
    st.write("Cada linha é uma vaga única, com o estado da observação mais recente.")

    try:
        opcoes = dados.opcoes()
        filtros = filtros_barra_lateral(opcoes, com_periodo=True)
        somente_ativas = st.sidebar.toggle("Só vagas ativas", value=True, key=CHAVE_SOMENTE_ATIVAS)
        cabecalho = st.empty()
        pagina = st.number_input("Página", min_value=1, step=1, key=CHAVE_PAGINA)
        resultado = dados.vagas(filtros, somente_ativas, int(pagina))
    except DadosIndisponiveis as exc:
        _aviso_indisponivel(exc)
        return

    if resultado.total == 0:
        cabecalho.info(
            "Nenhuma vaga com esses filtros no período. O período seleciona vagas "
            f"vistas pelo menos uma vez nele. {_intervalo_coletas(opcoes)}"
        )
        return
    if not resultado.linhas:
        cabecalho.info(f"A página {resultado.pagina} passou do fim: há {resultado.paginas} páginas.")
        return

    cabecalho.caption(
        f"{formatar_inteiro(resultado.total)} vagas únicas · página {resultado.pagina} de "
        f"{resultado.paginas} · {resultado.por_pagina} por página, das vistas mais "
        "recentemente para as mais antigas."
    )
    tabela = pd.DataFrame([
        {
            "Título": linha.titulo,
            "Empresa": linha.empresa,
            "Área": linha.area,
            "Modalidade": linha.modalidade,
            "Fonte": linha.fonte,
            "Ativa": linha.ativa,
            "Primeiro avistamento": linha.primeiro_avistamento.astimezone(BRASILIA),
            "Último avistamento": linha.ultimo_avistamento.astimezone(BRASILIA),
            "Link": linha.url,
        }
        for linha in resultado.linhas
    ])
    st.dataframe(
        tabela,
        hide_index=True,
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="abrir"),
            "Primeiro avistamento": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            "Último avistamento": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        },
    )
    st.caption(
        "Horários de Brasília. Último avistamento é a coleta mais recente que listou "
        "a vaga. O link só aparece para endereços http(s) do portal."
    )


def tecnologias(dados: Dados) -> None:
    st.title("Tecnologias")
    st.write("Tecnologias citadas nas vagas únicas ativas.")

    try:
        filtros = filtros_barra_lateral(dados.opcoes(), com_periodo=False)
        ranking = dados.tecnologias(filtros)
    except DadosIndisponiveis as exc:
        _aviso_indisponivel(exc)
        return

    if ranking.vagas_ativas == 0:
        st.info("Nenhuma vaga ativa com esses filtros. Remova algum filtro na barra lateral.")
    elif not ranking.confiavel:
        st.info(
            f"Só {formatar_inteiro(ranking.base)} vagas ativas neste recorte citam alguma "
            f"tecnologia. Abaixo de {BASE_MINIMA_TECNOLOGIAS}, uma única vaga muda o "
            "ranking, então ele não é mostrado. Amplie os filtros."
        )
    else:
        st.caption(
            f"Base: {formatar_inteiro(ranking.base)} das {formatar_inteiro(ranking.vagas_ativas)} "
            "vagas ativas citam alguma tecnologia. O percentual é sobre essa base."
        )
        tabela = pd.DataFrame({
            "Tecnologia": [c.rotulo for c in ranking.itens],
            "% das vagas": [round(100 * c.vagas / ranking.base, 1) for c in ranking.itens],
        })
        st.bar_chart(tabela, x="Tecnologia", y="% das vagas", horizontal=True, sort="-% das vagas")

    st.caption(
        "Conta menção, não exigência: \"diferencial: Python\" conta igual a \"exige "
        "Python\". O card do LinkedIn não traz descrição, então as vagas dele quase "
        "nunca entram na base."
    )
