"""Frescor dos dados: a coleta esta em dia, vencida ou parada?

Uma coleta que **falha** deixa rastro (job vermelho, e-mail do GitHub). Uma coleta
que **deixa de rodar** nao deixa nada: o GitHub desativa agendamentos de repositorios
sem atividade por 60 dias, e API e dashboard seguiriam mostrando numeros velhos.
Esta regra transforma `collection_runs` nesse sinal. Lida pela API
(`/health/dados`) e pelo dashboard; detalhes em docs/observability.md.

Fica em `persistence/`, e nao em `scraper/`, porque o dashboard nao pode importar
`scraper.execucao` (que puxa as fontes, com requests e bs4).

Estados, em ordem de avaliacao (datas comparadas por dia UTC, como a guarda):

- `sem_coleta`: nenhuma coleta completa `success`/`partial` registrada;
- `sem_intervalo`: ha coleta, mas nenhuma execucao agendada gravou o intervalo X,
  entao nao ha regua. Informativo;
- `vencido`: a ultima coleta completa tem mais de 2 x X dias;
- `coleta_parada`: nenhuma execucao (nem pulada) ha mais de 2 dias. O cron acorda
  todo dia e registra ate os pulos, entao o silencio indica agendamento parado ou
  desativado, antes mesmo de o dado vencer;
- `em_dia`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import CollectionRun

# Copia de `scraper.execucao.STATUS_QUE_CONTAM`: importar aquele modulo puxaria as
# fontes. Status que contam como "ultima coleta" para a guarda de intervalo.
STATUS_QUE_CONTAM = ("success", "partial")

# Com X = 2 (o valor do projeto), o dado vence a partir de 5 dias sem coleta
# completa: tolera uma coleta perdida (o GitHub pode descartar execucoes agendadas).
MULTIPLO_DO_INTERVALO = 2
# O cron acorda todo dia e toda execucao e registrada, inclusive as puladas.
DIAS_SEM_EXECUCAO = 2

EM_DIA = "em_dia"
VENCIDO = "vencido"
COLETA_PARADA = "coleta_parada"
SEM_COLETA = "sem_coleta"
SEM_INTERVALO = "sem_intervalo"

# Estados em que o monitoramento deve alertar.
ESTADOS_COM_PROBLEMA = (VENCIDO, COLETA_PARADA, SEM_COLETA)


def _utc(momento: datetime | None) -> datetime | None:
    """O SQLite devolve datetime sem fuso; o valor gravado ja esta em UTC."""
    if momento is None:
        return None
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


@dataclass(frozen=True)
class Frescor:
    estado: str
    ultima_coleta: datetime | None = None
    status_ultima_coleta: str | None = None
    dias_desde_ultima_coleta: int | None = None
    intervalo_dias: int | None = None
    limite_dias: int | None = None
    ultima_execucao: datetime | None = None
    status_ultima_execucao: str | None = None
    dias_desde_ultima_execucao: int | None = None
    proxima_coleta: date | None = None

    @property
    def saudavel(self) -> bool:
        return self.estado == EM_DIA

    @property
    def com_problema(self) -> bool:
        return self.estado in ESTADOS_COM_PROBLEMA


def avaliar(
    ultima_coleta: tuple[datetime, str] | None,
    ultima_execucao: tuple[datetime, str] | None,
    intervalo_dias: int | None,
    proxima_coleta: date | None,
    agora: datetime,
) -> Frescor:
    """Regra pura. `ultima_coleta`/`ultima_execucao` sao (inicio, status)."""
    hoje = _utc(agora).date()
    coleta_em, coleta_status = ultima_coleta or (None, None)
    execucao_em, execucao_status = ultima_execucao or (None, None)
    coleta_em, execucao_em = _utc(coleta_em), _utc(execucao_em)

    dias_coleta = (hoje - coleta_em.date()).days if coleta_em else None
    dias_execucao = (hoje - execucao_em.date()).days if execucao_em else None
    limite = intervalo_dias * MULTIPLO_DO_INTERVALO if intervalo_dias else None

    if coleta_em is None:
        estado = SEM_COLETA
    elif limite is None:
        estado = SEM_INTERVALO
    elif dias_coleta > limite:
        estado = VENCIDO
    elif dias_execucao is None or dias_execucao > DIAS_SEM_EXECUCAO:
        estado = COLETA_PARADA
    else:
        estado = EM_DIA

    return Frescor(
        estado=estado,
        ultima_coleta=coleta_em,
        status_ultima_coleta=coleta_status,
        dias_desde_ultima_coleta=dias_coleta,
        intervalo_dias=intervalo_dias,
        limite_dias=limite,
        ultima_execucao=execucao_em,
        status_ultima_execucao=execucao_status,
        dias_desde_ultima_execucao=dias_execucao,
        proxima_coleta=proxima_coleta,
    )


def estado_das_coletas(db: Session, agora: datetime | None = None) -> Frescor:
    """Frescor a partir de `collection_runs`. Quatro consultas simples e so leitura."""
    agora = agora or datetime.now(timezone.utc)
    recentes = CollectionRun.started_at.desc()

    coleta = db.execute(
        select(CollectionRun.started_at, CollectionRun.status)
        .where(CollectionRun.full_scope.is_(True),
               CollectionRun.status.in_(STATUS_QUE_CONTAM))
        .order_by(recentes).limit(1)
    ).first()
    execucao = db.execute(
        select(CollectionRun.started_at, CollectionRun.status).order_by(recentes).limit(1)
    ).first()
    intervalo = db.scalar(
        select(CollectionRun.interval_days)
        .where(CollectionRun.interval_days.is_not(None))
        .order_by(recentes).limit(1)
    )
    proxima = db.scalar(
        select(CollectionRun.next_run_on)
        .where(CollectionRun.next_run_on.is_not(None))
        .order_by(recentes).limit(1)
    )
    return avaliar(
        tuple(coleta) if coleta else None,
        tuple(execucao) if execucao else None,
        intervalo, proxima, agora,
    )
