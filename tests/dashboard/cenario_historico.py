"""Cenario de historico conhecido para as analises do dashboard.

Modulo comum (nao conftest) para os testes importarem as datas; a fixture
`banco_com_historico` fica em tests/dashboard/conftest.py.

Tres dias de coleta (D1, D2, D3) e uma execucao que falhou em D4:

| vaga | fonte    | vista     | encerrada | snapshots (area, modalidade, empresa)                                   |
|------|----------|-----------|-----------|-------------------------------------------------------------------------|
| A    | gupy     | D1 → D3   | não       | D1 Backend/Remoto/Acme · D2 Backend/Remoto · D3 Data/Remoto (Python, SQL) |
| B    | linkedin | D1 → D2   | D3        | D1 Data/Presencial (Java)                                               |
| C    | vagas    | D2 → D3   | não       | D2 Suporte/Infra/sem modalidade/Beta (SQL)                              |
| D    | gupy     | D3        | não       | D3 Frontend/Híbrido/" ACME"                                             |

A tem 3 snapshots e conta como uma vaga unica. O D1 de A cita Java, que nao
pode aparecer no ranking atual.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

D1, D2, D3, D4 = date(2026, 9, 10), date(2026, 9, 12), date(2026, 9, 14), date(2026, 9, 16)


def momento(dia: date) -> datetime:
    return datetime(dia.year, dia.month, dia.day, 9, 5, tzinfo=timezone.utc)


def gravar(banco, *objetos) -> None:
    """Grava com o engine normal: o do dashboard nao escreve."""
    from sqlalchemy.orm import Session

    from api.database import make_engine

    engine = make_engine(banco)
    try:
        with Session(engine) as db, db.begin():
            db.add_all(objetos)
    finally:
        engine.dispose()


def popular(banco) -> None:
    from api.models import CollectionRun, JobRecord, JobSnapshot, Tecnologia

    python, sql, java = (Tecnologia(nome=n, grupo="Linguagens") for n in ("Python", "SQL", "Java"))

    def execucao(dia, status="success"):
        return CollectionRun(started_at=momento(dia), finished_at=momento(dia),
                             triggered_by="schedule", status=status, full_scope=True,
                             jobs_count=0 if status == "failed" else 3, failures=0, summary={})

    def snapshot(dia, titulo, area, modalidade, empresa=None, tecnologias=()):
        return JobSnapshot(collected_at=momento(dia), title=titulo, company=empresa, area=area,
                           workplace_type=modalidade, content_hash=f"{titulo}-{dia}",
                           tecnologias=list(tecnologias))

    vaga_a = JobRecord(
        source="gupy", external_id="A", url="https://portal.exemplo/vagas/a",
        first_seen_at=momento(D1), last_seen_at=momento(D3), is_active=True,
        snapshots=[
            snapshot(D1, "Dev Backend Jr", "Backend", "Remoto", "Acme", [java]),
            snapshot(D2, "Desenvolvedor Backend Jr", "Backend", "Remoto", "Acme"),
            snapshot(D3, "Engenheiro de Dados Jr", "Data", "Remoto", "Acme", [python, sql]),
        ],
    )
    vaga_b = JobRecord(
        source="linkedin", external_id="B", url="javascript:alert(1)",
        first_seen_at=momento(D1), last_seen_at=momento(D2), is_active=False,
        missing_since=momento(D2), closed_at=momento(D3),
        snapshots=[snapshot(D1, "Analista de Dados Jr", "Data", "Presencial", "acme ", [java])],
    )
    vaga_c = JobRecord(
        source="vagas", external_id="C", url=None,
        first_seen_at=momento(D2), last_seen_at=momento(D3), is_active=True,
        snapshots=[snapshot(D2, "Suporte N1", "Suporte/Infra", None, "Beta", [sql])],
    )
    vaga_d = JobRecord(
        source="gupy", external_id="D", url="http://portal.exemplo/vagas/d",
        first_seen_at=momento(D3), last_seen_at=momento(D3), is_active=True,
        snapshots=[snapshot(D3, "Dev Frontend Jr", "Frontend", "Híbrido", " ACME")],
    )
    gravar(banco, vaga_a, vaga_b, vaga_c, vaga_d,
           execucao(D1), execucao(D2, "partial"), execucao(D3), execucao(D4, "failed"))
