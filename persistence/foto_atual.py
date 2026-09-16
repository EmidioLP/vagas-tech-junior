"""A "foto atual" das vagas: identidade de `jobs` + estado do snapshot mais recente.

Regra unica lida pela API (`api/crud.py`) e pelo dashboard
(`dashboard/consultas.py`), para os dois contarem as mesmas vagas. So monta
consultas; quem executa e decide filtros e cada consumidor.

Nao importa FastAPI, Streamlit, requests, bs4 nem yaml: o dashboard publicado
instala so `requirements-dashboard.txt`.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select

from api.models import JobRecord, JobSnapshot
from scraper.models import NAO_INFORMADO

# Snapshot sem area gravada (a coluna aceita nulo).
SEM_AREA = "Sem área"


def rotulo_area(coluna):
    return func.coalesce(func.nullif(coluna, ""), SEM_AREA)


def rotulo_modalidade(coluna):
    return func.coalesce(func.nullif(coluna, ""), NAO_INFORMADO)


def vagas_atuais():
    """Uma linha por vaga unica, com o estado do snapshot mais recente.

    `(job_id, collected_at)` e unico, entao o join com o `max(collected_at)` nunca
    duplica vagas. Vaga sem nenhum snapshot fica de fora. Ativas e encerradas
    entram; o filtro por `ativa` e de quem consulta.
    """
    ultimo = (
        select(JobSnapshot.job_id, func.max(JobSnapshot.collected_at).label("collected_at"))
        .group_by(JobSnapshot.job_id)
        .subquery("ultimo_snapshot")
    )
    return (
        select(
            JobRecord.id.label("job_id"),
            JobRecord.source.label("fonte"),
            JobRecord.external_id.label("external_id"),
            JobRecord.is_active.label("ativa"),
            JobRecord.first_seen_at.label("primeiro_avistamento"),
            JobRecord.last_seen_at.label("ultimo_avistamento"),
            JobRecord.closed_at.label("encerrada_em"),
            JobRecord.url.label("url"),
            JobSnapshot.id.label("snapshot_id"),
            JobSnapshot.title.label("titulo"),
            JobSnapshot.company.label("empresa"),
            JobSnapshot.description.label("descricao"),
            JobSnapshot.location.label("local"),
            JobSnapshot.seniority.label("senioridade"),
            JobSnapshot.published_date.label("publicada_em"),
            JobSnapshot.area_score.label("area_score"),
            JobSnapshot.area_matches.label("area_matches"),
            rotulo_area(JobSnapshot.area).label("area"),
            rotulo_modalidade(JobSnapshot.workplace_type).label("modalidade"),
        )
        .join(ultimo, ultimo.c.job_id == JobRecord.id)
        .join(JobSnapshot, and_(JobSnapshot.job_id == ultimo.c.job_id,
                                JobSnapshot.collected_at == ultimo.c.collected_at))
        .subquery("vagas_atuais")
    )
