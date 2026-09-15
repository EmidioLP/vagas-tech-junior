"""Politica de execucao da coleta: intervalo entre coletas e status por fonte.

Tudo aqui e puro (sem banco e sem rede), para as regras serem testaveis
isoladamente. Quem le e grava o registro das execucoes e
`persistence/execucoes.py`; quem aplica as regras e `scraper/pipeline.py`.
Detalhes em docs/automation.md.

- **Intervalo.** O cron acorda todo dia; a coleta so roda se a ultima coleta
  completa bem-sucedida foi ha pelo menos X dias, contados por data em UTC.
- **Fonte.** `failed` quando nao trouxe vagas e algo falhou (ou a gravacao dela
  foi desfeita); `partial` quando trouxe vagas mas algo falhou; senao `ok`.
- **Execucao.** `failed` (exit 1) se todas as fontes falharam ou nao houve vagas;
  `partial` se alguma fonte nao ficou ok (exit 0) ou houve vaga nao gravada
  (exit 1, regra da persistencia); senao `success`.
- **Agenda.** Toda execucao com X conhecido informa "Última coleta: dia ... e
  próxima: dia ...": a proxima e a ultima coleta completa + X dias, ou amanha se
  essa data ja passou (o cron acorda todo dia e tenta de novo).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .config import SEARCH_TERMS, Settings
from .models import SourceStats
from .sources import DEFAULT_SOURCES

OK = "ok"
SUCCESS = "success"
PARTIAL = "partial"
FAILED = "failed"
SKIPPED = "skipped"

# Status que contam como "ultima coleta" para a guarda de intervalo. `failed` fica
# de fora para a proxima execucao tentar de novo.
STATUS_QUE_CONTAM = (SUCCESS, PARTIAL)

# Quem disparou a execucao, gravado em `collection_runs.triggered_by`.
GATILHOS = ("local", "manual", "schedule")

ROTULOS = {
    OK: "ok",
    SUCCESS: "sucesso",
    PARTIAL: "parcial",
    FAILED: "falhou",
    SKIPPED: "pulada",
}

# Abaixo disso a coleta e uma amostra e nao pode adiar a coleta completa.
PAGINAS_ESCOPO_COMPLETO = 5


@dataclass(frozen=True)
class Decisao:
    """Resultado da guarda: coletar agora ou pular ate `proxima_em`."""

    executar: bool
    motivo: str
    proxima_em: date | None = None


def escopo_completo(settings: Settings) -> bool:
    """Coleta que representa o mercado inteiro, e nao uma amostra.

    Exige as fontes da coleta padrao; as de `FORA_DA_COLETA_PADRAO` (bloqueadas
    em nuvem) nao sao necessarias.
    """
    return (
        set(settings.sources) >= set(DEFAULT_SOURCES)
        and list(settings.search_terms) == list(SEARCH_TERMS)
        and settings.max_pages_per_term >= PAGINAS_ESCOPO_COMPLETO
        and settings.only_junior
    )


def _dia_utc(momento: datetime) -> date:
    """O SQLite devolve datetime sem fuso; o valor gravado ja esta em UTC."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).date()


def formatar_data(dia: date) -> str:
    """Data como aparece para quem le o terminal e o resumo: 15/09/2026."""
    return dia.strftime("%d/%m/%Y")


@dataclass(frozen=True)
class Agenda:
    """Ultima coleta completa e proxima coleta prevista (datas em UTC)."""

    ultima: date | None
    proxima: date
    intervalo_dias: int

    def frase(self) -> str:
        ultima = f"dia {formatar_data(self.ultima)}" if self.ultima else "nenhuma registrada"
        return f"Última coleta: {ultima} e próxima: dia {formatar_data(self.proxima)}"

    @property
    def periodicidade(self) -> str:
        return "a cada 1 dia" if self.intervalo_dias == 1 else f"a cada {self.intervalo_dias} dias"


def calcular_agenda(
    ultima_coleta: datetime | None, agora: datetime, intervalo_dias: int,
) -> Agenda:
    """Proxima coleta = ultima coleta completa + X dias.

    Se essa data ja passou (a ultima execucao falhou, ou nao ha coleta completa
    registrada), a proxima e amanha: o cron acorda todo dia e tenta de novo.
    """
    amanha = _dia_utc(agora) + timedelta(days=1)
    if ultima_coleta is None:
        return Agenda(None, amanha, intervalo_dias)
    ultima = _dia_utc(ultima_coleta)
    return Agenda(ultima, max(ultima + timedelta(days=intervalo_dias), amanha), intervalo_dias)


def decidir(ultima_coleta: datetime | None, agora: datetime, intervalo_dias: int) -> Decisao:
    """Guarda de intervalo, por data em UTC.

    Comparar datas, e nao horas, evita que o cron diario "escorregue": uma coleta
    iniciada as 09:05 nao faz a execucao das 09:02 do dia previsto ser pulada.
    """
    if intervalo_dias < 1:
        raise ValueError("intervalo_dias precisa ser positivo")
    if ultima_coleta is None:
        return Decisao(True, "nenhuma coleta completa registrada")

    ultima = _dia_utc(ultima_coleta)
    proxima = ultima + timedelta(days=intervalo_dias)
    base = f"última coleta completa em {formatar_data(ultima)}, intervalo de {intervalo_dias} dia(s)"
    if _dia_utc(agora) >= proxima:
        return Decisao(True, f"{base} cumprido")
    return Decisao(False, f"{base} ainda não cumprido", proxima)


def status_fonte(stats: SourceStats | None, gravacao: Any | None = None) -> str:
    """Status de uma fonte. `gravacao` e o `ResumoFonte` da persistencia, se houve."""
    falhou_coleta = stats is not None and bool(stats.errors or stats.requests_failed)
    brutas = stats.raw_jobs if stats is not None else 0
    falhas_gravacao = gravacao.falhas if gravacao is not None else 0

    if brutas == 0 and falhou_coleta:
        return FAILED
    if falhas_gravacao and not (gravacao.jobs_criados + gravacao.jobs_atualizados):
        return FAILED  # nada da fonte foi gravado, por exemplo transacao desfeita
    if falhou_coleta or falhas_gravacao:
        return PARTIAL
    return OK


def status_por_fonte(
    stats: Iterable[SourceStats], persistencia: Any | None = None,
) -> dict[str, str]:
    por_stats = {s.source: s for s in stats}
    por_gravacao = persistencia.por_fonte if persistencia is not None else {}
    fontes = dict.fromkeys([*por_stats, *por_gravacao])
    return {f: status_fonte(por_stats.get(f), por_gravacao.get(f)) for f in fontes}


def status_execucao(
    status_fontes: Mapping[str, str], total_vagas: int, falhas_gravacao: int,
) -> tuple[str, int]:
    """(status, exit code) da execucao. Fonte com falha nunca some: vira `partial`."""
    todas_falharam = bool(status_fontes) and all(s == FAILED for s in status_fontes.values())
    if todas_falharam or total_vagas == 0:
        return FAILED, 1
    if falhas_gravacao:
        return PARTIAL, 1
    if any(s != OK for s in status_fontes.values()):
        return PARTIAL, 0
    return SUCCESS, 0
