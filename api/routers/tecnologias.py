"""Endpoints de tecnologias."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..schemas import Erro, TecnologiaOut, TecnologiasDaAreaOut
from ..vocabulary import AreaEnum

router = APIRouter(prefix="/tecnologias", tags=["tecnologias"])


@router.get(
    "",
    response_model=list[TecnologiaOut],
    summary="Listar tecnologias com contagem de menções",
    description=(
        "As tecnologias de `skills.yml`, da mais para a menos citada. "
        "A contagem é o número de vagas únicas ativas que citam a tecnologia "
        "na coleta mais recente de cada uma (a mesma regra do dashboard). Vem "
        "do banco, não do CSV `skills_por_area`, que é truncado no top-15 de "
        "cada área."
    ),
)
def listar_tecnologias(
    db: Session = Depends(get_db),
    grupo: str | None = Query(
        default=None, description="Filtra por grupo, ex.: `linguagens`."
    ),
    com_vagas: bool = Query(
        default=False, description="Se verdadeiro, omite tecnologias com zero vagas."
    ),
) -> list[TecnologiaOut]:
    rows = crud.count_by_tecnologia(db)
    if grupo:
        rows = [r for r in rows if r["grupo"].lower() == grupo.lower()]
    if com_vagas:
        rows = [r for r in rows if r["vagas"] > 0]
    return [TecnologiaOut(**row) for row in rows]


# Declarada antes de `/{nome}`: senao "por-area" seria lido como nome de tecnologia.
@router.get(
    "/por-area",
    response_model=list[TecnologiasDaAreaOut],
    summary="Ranking de tecnologias por área",
    description=(
        "Para cada área com vaga ativa, as tecnologias mais citadas no estado "
        "atual das vagas dela (a mesma conta do dashboard). Cada área tem a "
        "própria `base`: as vagas ativas dela que citam alguma tecnologia, que é "
        "o denominador do percentual. A API não esconde área de base pequena; o "
        "dashboard só exibe a partir de 15 e trata abaixo de 30 como indicativo. "
        "Mede menção, não exigência. Ordem: maior base primeiro."
    ),
)
def listar_tecnologias_por_area(
    db: Session = Depends(get_db),
    area: AreaEnum | None = Query(default=None, description="Só esta área."),
    limit: int = Query(default=8, ge=1, le=200, description="Tecnologias por área."),
) -> list[TecnologiasDaAreaOut]:
    rows = crud.tecnologias_por_area(db, area=area.value if area else None, limit=limit)
    return [TecnologiasDaAreaOut(**row) for row in rows]


@router.get(
    "/{nome}",
    response_model=TecnologiaOut,
    summary="Buscar tecnologia por nome",
    responses={404: {"model": Erro, "description": "Tecnologia não encontrada."}},
)
def buscar_tecnologia(nome: str, db: Session = Depends(get_db)) -> TecnologiaOut:
    row = crud.get_tecnologia(db, nome)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tecnologia não encontrada: {nome!r}.",
        )
    return TecnologiaOut(**row)
