"""Endpoints das execucoes da coleta (somente leitura)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..schemas import Erro, ExecucaoOut, ExecucaoPage
from ..vocabulary import GatilhoEnum, StatusExecucaoEnum

router = APIRouter(prefix="/execucoes", tags=["execucoes"])


@router.get(
    "",
    response_model=ExecucaoPage,
    summary="Listar execuções da coleta",
    description=(
        "O registro de cada disparo da coleta (`collection_runs`), da mais recente "
        "para a mais antiga: agendado, manual ou local, inclusive os pulados pela "
        "guarda de intervalo e os que falharam. Traz só contagens por fonte e os "
        "alertas de qualidade (regra, severidade e fonte); nunca URL nem mensagem "
        "de erro. Para saber se os dados estão em dia, use `/health/dados`."
    ),
)
def listar_execucoes(
    db: Session = Depends(get_db),
    status_: StatusExecucaoEnum | None = Query(
        default=None, alias="status", description="Status da execução."),
    gatilho: GatilhoEnum | None = Query(default=None, description="Quem disparou."),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ExecucaoPage:
    total, items = crud.list_execucoes(
        db,
        status=status_.value if status_ else None,
        gatilho=gatilho.value if gatilho else None,
        limit=limit,
        offset=offset,
    )
    return ExecucaoPage(total=total, limit=limit, offset=offset, items=items)


@router.get(
    "/{execucao_id}",
    response_model=ExecucaoOut,
    summary="Buscar execução por id",
    description="O id é o de `collection_runs`, o mesmo que aparece no log e no resumo da coleta.",
    responses={404: {"model": Erro, "description": "Execução não encontrada."}},
)
def buscar_execucao(execucao_id: int, db: Session = Depends(get_db)) -> ExecucaoOut:
    execucao = crud.get_execucao(db, execucao_id)
    if execucao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execução {execucao_id} não encontrada.",
        )
    return execucao
