"""Paginas do dashboard. So apresentam: os dados vem de `dashboard.consultas`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

import streamlit as st

from dashboard.consultas import DadosIndisponiveis, ResumoGeral

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


def formatar_data(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def formatar_data_hora(momento: datetime) -> str:
    local = momento.astimezone(BRASILIA)
    return f"{local:%d/%m/%Y} às {local:%H:%M}"


def formatar_inteiro(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def frase_agenda(resumo: ResumoGeral) -> str | None:
    """O mesmo texto da CLI. Datas da agenda em UTC, como `next_run_on`."""
    if resumo.proxima_coleta is None:
        return None
    if resumo.ultima_coleta is None:
        ultima = "nenhuma registrada"
    else:
        ultima = f"dia {formatar_data(resumo.ultima_coleta.iniciada_em.astimezone(timezone.utc).date())}"
    return f"Última coleta: {ultima} e próxima: dia {formatar_data(resumo.proxima_coleta)}"


def overview(carregar: Callable[[], ResumoGeral]) -> None:
    st.title("Vagas Tech Júnior")
    st.write(
        "Qual área de tecnologia mais contrata júnior no Brasil, com dados "
        "coletados de sete portais de vagas."
    )

    try:
        resumo = carregar()
    except DadosIndisponiveis as exc:
        st.warning("Dados indisponíveis no momento. Tente de novo em alguns minutos.")
        st.caption(str(exc))
        return

    if resumo.vazio:
        st.info(
            "Ainda não há coleta registrada. Os números aparecem depois da "
            "primeira coleta completa."
        )
        return

    coluna_vagas, coluna_coleta = st.columns(2)
    coluna_vagas.metric("Vagas ativas", formatar_inteiro(resumo.vagas_ativas))
    coluna_coleta.metric(
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


def em_construcao(titulo: str, etapa: str) -> Callable[[], None]:
    """Pagina futura com estado explicito: nenhum numero inventado."""

    def _pagina() -> None:
        st.title(titulo)
        st.info(f"Em construção. Esta página chega na {etapa}; por enquanto não há dados aqui.")

    return _pagina
