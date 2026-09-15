"""Registro das execucoes da coleta em `collection_runs`.

A decisao (coletar ou pular) e as regras de status ficam em `scraper/execucao.py`;
aqui so se le a ultima coleta que conta para a guarda e se grava cada execucao.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from api.models import CollectionRun
from scraper.execucao import STATUS_QUE_CONTAM


def ultima_coleta_completa(engine: Engine) -> datetime | None:
    """Inicio da ultima coleta de escopo completo com status `success` ou `partial`."""
    with Session(engine) as db:
        momento = db.scalar(
            select(CollectionRun.started_at)
            .where(
                CollectionRun.full_scope.is_(True),
                CollectionRun.status.in_(STATUS_QUE_CONTAM),
            )
            .order_by(CollectionRun.started_at.desc())
            .limit(1)
        )
    if momento is None:
        return None
    if momento.tzinfo is None:  # o SQLite nao guarda fuso; o valor gravado ja e UTC
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def registrar_execucao(
    engine: Engine,
    *,
    started_at: datetime,
    finished_at: datetime,
    triggered_by: str,
    status: str,
    full_scope: bool,
    interval_days: int | None = None,
    reason: str | None = None,
    next_run_on: date | None = None,
    jobs_count: int = 0,
    failures: int = 0,
    summary: dict | None = None,
) -> int:
    """Grava uma execucao numa transacao propria e devolve o id."""
    with Session(engine) as db, db.begin():
        execucao = CollectionRun(
            started_at=started_at,
            finished_at=finished_at,
            triggered_by=triggered_by,
            status=status,
            full_scope=full_scope,
            interval_days=interval_days,
            reason=reason,
            next_run_on=next_run_on,
            jobs_count=jobs_count,
            failures=failures,
            summary=summary or {},
        )
        db.add(execucao)
        db.flush()
        return execucao.id
