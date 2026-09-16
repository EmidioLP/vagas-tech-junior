"""Consultas ao banco.

A API le o historico que o pipeline grava (`jobs` + `job_snapshots`), pela mesma
"foto atual" do dashboard (`persistence/foto_atual.py`): uma linha por vaga
unica, com o estado do snapshot mais recente. Assim API e dashboard contam as
mesmas vagas.

`/areas` e `/tecnologias` sao sempre calculados a partir das vagas ativas --
nunca lidos dos CSVs de ranking. Os CSVs `ranking_areas` e `skills_por_area` sao
recortes ja agregados (o de skills e truncado no top-15 por area), entao serviriam
numeros errados e desatualizados assim que o banco mudasse.

Filtros viram sempre bind params: nada e interpolado no SQL.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import distinct, exists, func, select
from sqlalchemy.orm import Session

from persistence.foto_atual import vagas_atuais

from . import vocabulary
from .models import Tecnologia, job_snapshot_tecnologias


def _utc(momento: datetime | None) -> datetime | None:
    """O SQLite devolve datetime sem fuso; o valor gravado ja esta em UTC."""
    if momento is None or momento.tzinfo is not None:
        return momento
    return momento.replace(tzinfo=timezone.utc)


def _vaga(linha, tecnologias: list[str]) -> dict:
    """Linha da foto atual no formato dos schemas `VagaOut`/`VagaResumo`."""
    return {
        "id": linha.job_id,
        "source": linha.fonte,
        "external_id": linha.external_id,
        "title": linha.titulo,
        "company": linha.empresa,
        "area": linha.area,
        "seniority": linha.senioridade,
        "location": linha.local,
        "workplace_type": linha.modalidade,
        "published_date": linha.publicada_em,
        "url": linha.url,
        "description": linha.descricao,
        "area_score": linha.area_score,
        "area_matches": linha.area_matches,
        "tecnologias": tecnologias,
        "ativa": bool(linha.ativa),
        "first_seen_at": _utc(linha.primeiro_avistamento),
        "last_seen_at": _utc(linha.ultimo_avistamento),
        "closed_at": _utc(linha.encerrada_em),
    }


def _tecnologias_dos_snapshots(db: Session, snapshot_ids: list[int]) -> dict[int, list[str]]:
    """{snapshot_id: nomes ordenados}, numa consulta so para a pagina inteira."""
    if not snapshot_ids:
        return {}
    linhas = db.execute(
        select(job_snapshot_tecnologias.c.snapshot_id, Tecnologia.nome)
        .join(Tecnologia, Tecnologia.id == job_snapshot_tecnologias.c.tecnologia_id)
        .where(job_snapshot_tecnologias.c.snapshot_id.in_(snapshot_ids))
    ).all()
    por_snapshot: dict[int, list[str]] = defaultdict(list)
    for snapshot_id, nome in linhas:
        por_snapshot[snapshot_id].append(nome)
    return {sid: sorted(nomes) for sid, nomes in por_snapshot.items()}


def list_vagas(
    db: Session,
    *,
    area: str | None = None,
    tecnologia: str | None = None,
    modalidade: str | None = None,
    fonte: str | None = None,
    q: str | None = None,
    incluir_encerradas: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    """(total que casa com os filtros, pagina pedida). Filtros combinam em AND."""
    vagas = vagas_atuais()
    stmt = select(vagas)

    if not incluir_encerradas:
        stmt = stmt.where(vagas.c.ativa.is_(True))
    if area:
        stmt = stmt.where(vagas.c.area == area)
    if modalidade:
        stmt = stmt.where(vagas.c.modalidade == modalidade)
    if fonte:
        stmt = stmt.where(vagas.c.fonte == fonte)
    if q:
        stmt = stmt.where(vagas.c.titulo.ilike(f"%{q}%"))
    if tecnologia:
        # So a tecnologia do snapshot vigente conta: a vaga pode ter deixado de cita-la.
        stmt = stmt.where(exists(
            select(1)
            .select_from(job_snapshot_tecnologias)
            .join(Tecnologia, Tecnologia.id == job_snapshot_tecnologias.c.tecnologia_id)
            .where(job_snapshot_tecnologias.c.snapshot_id == vagas.c.snapshot_id,
                   func.lower(Tecnologia.nome) == tecnologia.lower())
        ))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    linhas = db.execute(
        stmt.order_by(vagas.c.publicada_em.desc().nulls_last(), vagas.c.job_id)
        .limit(limit).offset(offset)
    ).all()
    tecnologias = _tecnologias_dos_snapshots(db, [linha.snapshot_id for linha in linhas])
    return total, [_vaga(linha, tecnologias.get(linha.snapshot_id, [])) for linha in linhas]


def get_vaga(db: Session, vaga_id: int) -> dict | None:
    """Vaga unica pelo id de `jobs`, ativa ou encerrada."""
    vagas = vagas_atuais()
    linha = db.execute(select(vagas).where(vagas.c.job_id == vaga_id)).first()
    if linha is None:
        return None
    tecnologias = _tecnologias_dos_snapshots(db, [linha.snapshot_id])
    return _vaga(linha, tecnologias.get(linha.snapshot_id, []))


def count_by_area(db: Session) -> list[dict]:
    """Vagas ativas por area. Todas as areas do vocabulario, inclusive as com zero."""
    vagas = vagas_atuais()
    rows = db.execute(
        select(vagas.c.area, func.count())
        .where(vagas.c.ativa.is_(True))
        .group_by(vagas.c.area)
    ).all()
    counts = {area: total for area, total in rows}
    total = sum(counts.values())

    result = [
        {
            "area": area,
            "vagas": counts.get(area, 0),
            "percentual": round(100 * counts.get(area, 0) / total, 1) if total else 0.0,
        }
        for area in vocabulary.areas()
    ]
    # Areas que existem no banco mas sairam do YAML nao somem do relatorio.
    for area in counts:
        if area not in vocabulary.areas():
            result.append({
                "area": area,
                "vagas": counts[area],
                "percentual": round(100 * counts[area] / total, 1) if total else 0.0,
            })

    return sorted(result, key=lambda row: (-row["vagas"], row["area"]))


def count_by_tecnologia(db: Session) -> list[dict]:
    """Vagas ativas que citam cada tecnologia no estado atual, inclusive as sem vaga."""
    vagas = vagas_atuais()
    citacoes = (
        select(job_snapshot_tecnologias.c.tecnologia_id, vagas.c.job_id)
        .join(vagas, vagas.c.snapshot_id == job_snapshot_tecnologias.c.snapshot_id)
        .where(vagas.c.ativa.is_(True))
        .subquery("citacoes")
    )
    rows = db.execute(
        select(Tecnologia.nome, Tecnologia.grupo, func.count(distinct(citacoes.c.job_id)))
        .outerjoin(citacoes, citacoes.c.tecnologia_id == Tecnologia.id)
        .group_by(Tecnologia.id, Tecnologia.nome, Tecnologia.grupo)
    ).all()

    known = vocabulary.technologies()
    result = [
        {"nome": nome, "grupo": grupo or known.get(nome, ""), "vagas": total}
        for nome, grupo, total in rows
    ]
    return sorted(result, key=lambda row: (-row["vagas"], row["nome"]))


def get_area(db: Session, nome: str) -> dict | None:
    for row in count_by_area(db):
        if row["area"].lower() == nome.lower():
            return row
    return None


def get_tecnologia(db: Session, nome: str) -> dict | None:
    for row in count_by_tecnologia(db):
        if row["nome"].lower() == nome.lower():
            return row
    return None
