"""Endpoint de modalidades de trabalho."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..schemas import ModalidadeOut
from ..vocabulary import AreaEnum, FonteEnum

router = APIRouter(prefix="/modalidades", tags=["modalidades"])


@router.get(
    "",
    response_model=list[ModalidadeOut],
    summary="Distribuição das vagas por modalidade",
    description=(
        "Vagas únicas ativas por modalidade, pelo estado da coleta mais recente "
        "de cada uma (a mesma regra do dashboard). Sempre as quatro modalidades "
        "do vocabulário, na ordem Remoto, Híbrido, Presencial e Não informado; as "
        "sem vagas aparecem com zero. Os filtros `area` e `fonte` recortam a "
        "base, e o percentual passa a ser sobre o recorte. A modalidade é em "
        "parte inferida do texto da vaga, e o LinkedIn raramente a informa: "
        "compare `Não informado` antes de ler os percentuais."
    ),
)
def listar_modalidades(
    db: Session = Depends(get_db),
    area: AreaEnum | None = Query(default=None, description="Área de tecnologia."),
    fonte: FonteEnum | None = Query(default=None, description="Portal de origem."),
) -> list[ModalidadeOut]:
    rows = crud.count_by_modalidade(
        db,
        area=area.value if area else None,
        fonte=fonte.value if fonte else None,
    )
    return [ModalidadeOut(**row) for row in rows]
