"""Unica camada de acesso ao banco do dashboard. So le.

Funcoes puras que recebem o engine, testaveis sem Streamlit. Os criterios seguem
os contratos do pipeline, sem reimplementar regra nenhuma:

- **ultima coleta:** a mesma regra da guarda de intervalo (`scraper/execucao.py`):
  execucao de escopo completo com status `success` ou `partial`;
- **proxima coleta:** o `next_run_on` gravado pela execucao mais recente;
- **vaga ativa:** `jobs.is_active` (encerramento em `persistence/repositorio.py`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.models import CollectionRun, JobRecord

# Copia de `scraper.execucao.STATUS_QUE_CONTAM`: importar aquele modulo puxaria as
# fontes (requests, bs4), que o dashboard nao usa.
STATUS_QUE_CONTAM = ("success", "partial")


class DadosIndisponiveis(RuntimeError):
    """Banco inacessivel, sem configuracao ou sem schema.

    A mensagem so traz o tipo do erro: a do driver pode citar host, usuario ou
    caminho do arquivo.
    """


@dataclass(frozen=True)
class Coleta:
    iniciada_em: datetime
    status: str
    vagas: int


@dataclass(frozen=True)
class Execucao:
    iniciada_em: datetime
    status: str
    gatilho: str


@dataclass(frozen=True)
class ResumoGeral:
    ultima_coleta: Coleta | None
    proxima_coleta: date | None
    ultima_execucao: Execucao | None
    vagas_ativas: int

    @property
    def vazio(self) -> bool:
        return self.ultima_coleta is None and self.vagas_ativas == 0


def _utc(momento: datetime) -> datetime:
    """O SQLite devolve datetime sem fuso; o valor gravado ja esta em UTC."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


@contextmanager
def _leitura(engine: Engine) -> Iterator[Session]:
    try:
        with Session(engine) as db:
            yield db
    except SQLAlchemyError as exc:
        tipo = type(getattr(exc, "orig", None) or exc).__name__
        raise DadosIndisponiveis(f"Não foi possível ler o banco ({tipo}).") from exc


def ultima_coleta(engine: Engine) -> Coleta | None:
    with _leitura(engine) as db:
        linha = db.execute(
            select(CollectionRun.started_at, CollectionRun.status, CollectionRun.jobs_count)
            .where(CollectionRun.full_scope.is_(True),
                   CollectionRun.status.in_(STATUS_QUE_CONTAM))
            .order_by(CollectionRun.started_at.desc())
            .limit(1)
        ).first()
    if linha is None:
        return None
    return Coleta(_utc(linha.started_at), linha.status, linha.jobs_count)


def proxima_coleta(engine: Engine) -> date | None:
    with _leitura(engine) as db:
        return db.scalar(
            select(CollectionRun.next_run_on)
            .where(CollectionRun.next_run_on.is_not(None))
            .order_by(CollectionRun.started_at.desc())
            .limit(1)
        )


def ultima_execucao(engine: Engine) -> Execucao | None:
    """Execucao mais recente de qualquer status, inclusive pulada ou com falha."""
    with _leitura(engine) as db:
        linha = db.execute(
            select(CollectionRun.started_at, CollectionRun.status, CollectionRun.triggered_by)
            .order_by(CollectionRun.started_at.desc())
            .limit(1)
        ).first()
    if linha is None:
        return None
    return Execucao(_utc(linha.started_at), linha.status, linha.triggered_by)


def vagas_ativas(engine: Engine) -> int:
    with _leitura(engine) as db:
        total = db.scalar(
            select(func.count()).select_from(JobRecord).where(JobRecord.is_active.is_(True))
        )
    return total or 0


def resumo_geral(engine: Engine) -> ResumoGeral:
    return ResumoGeral(
        ultima_coleta=ultima_coleta(engine),
        proxima_coleta=proxima_coleta(engine),
        ultima_execucao=ultima_execucao(engine),
        vagas_ativas=vagas_ativas(engine),
    )
