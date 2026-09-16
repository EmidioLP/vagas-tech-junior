"""Carga de um CSV do scraper no historico (`scripts/carregar_seed.py`)."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.database import make_engine
from api.models import CollectionRun, JobRecord, JobSnapshot
from scripts.carregar_seed import SEED, CargaRecusada, carregar, main

COLUNAS = [
    "area", "seniority", "title", "company", "source", "location",
    "workplace_type", "published_date", "url", "skills", "area_score",
    "area_matches", "search_term", "external_id", "description",
]
COLETA = date(2026, 7, 31)


def _escrever_csv(tmp_path, linhas):
    caminho = tmp_path / "vagas.csv"
    with open(caminho, "w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    return caminho


def _linha(**kwargs):
    base = {c: "" for c in COLUNAS}
    base.update({
        "area": "Data", "seniority": "Júnior", "title": "Analista de Dados Jr",
        "company": "ACME", "source": "gupy", "external_id": "1",
        "workplace_type": "Remoto", "published_date": "2026-07-20",
        "skills": "Python, SQL", "area_score": "12.0",
    })
    base.update(kwargs)
    return base


def _contar(banco, modelo) -> int:
    engine = make_engine(banco)
    try:
        with Session(engine) as db:
            return db.scalar(select(func.count()).select_from(modelo)) or 0
    finally:
        engine.dispose()


def _snapshots(banco) -> list[JobSnapshot]:
    engine = make_engine(banco)
    try:
        with Session(engine) as db:
            return list(db.scalars(select(JobSnapshot).order_by(JobSnapshot.title)))
    finally:
        engine.dispose()


def test_carrega_vagas_no_historico_com_tecnologias(tmp_path, banco_historico):
    csv_path = _escrever_csv(tmp_path, [
        _linha(),
        _linha(external_id="2", title="Suporte Jr", area="Suporte/Infra",
               skills="Linux, Tecnologia-Inexistente"),
    ])
    resumo = carregar(csv_path, banco_historico, COLETA)

    assert (resumo.jobs_criados, resumo.snapshots_criados, resumo.falhas) == (2, 2, 0)
    analista, suporte = _snapshots(banco_historico)
    assert sorted(t.nome for t in analista.tecnologias) == ["Python", "SQL"]
    assert [t.nome for t in suporte.tecnologias] == ["Linux"]
    assert analista.collected_at.date() == COLETA


def test_data_relativa_resolvida_pelo_dia_da_coleta(tmp_path, banco_historico):
    csv_path = _escrever_csv(tmp_path, [_linha(published_date="Ontem")])
    carregar(csv_path, banco_historico, COLETA)
    assert _snapshots(banco_historico)[0].published_date == date(2026, 7, 30)


def test_linha_sem_identidade_e_ignorada(tmp_path, banco_historico):
    csv_path = _escrever_csv(tmp_path, [
        _linha(external_id=""), _linha(source=""), _linha(title="  "), _linha(),
    ])
    carregar(csv_path, banco_historico, COLETA)
    assert _contar(banco_historico, JobRecord) == 1


def test_carregar_de_novo_nao_cria_vagas_nem_snapshots(tmp_path, banco_historico):
    csv_path = _escrever_csv(tmp_path, [_linha(), _linha(external_id="2")])
    carregar(csv_path, banco_historico, COLETA)
    resumo = carregar(csv_path, banco_historico, COLETA)

    assert (resumo.jobs_criados, resumo.snapshots_criados, resumo.falhas) == (0, 0, 0)
    assert _contar(banco_historico, JobRecord) == 2
    assert _contar(banco_historico, JobSnapshot) == 2


def test_recusa_banco_com_coletas_reais(tmp_path, banco_historico):
    agora = datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)
    engine = make_engine(banco_historico)
    try:
        with Session(engine) as db, db.begin():
            db.add(CollectionRun(started_at=agora, finished_at=agora, triggered_by="schedule",
                                 status="success", full_scope=True, jobs_count=1,
                                 failures=0, summary={}))
    finally:
        engine.dispose()

    csv_path = _escrever_csv(tmp_path, [_linha()])
    with pytest.raises(CargaRecusada, match="collection_runs"):
        carregar(csv_path, banco_historico, COLETA)
    assert _contar(banco_historico, JobRecord) == 0
    # Pela linha de comando: saida 2, sem traceback.
    assert main(["--csv", str(csv_path), "--db", str(banco_historico)]) == 2


def test_recusa_banco_sem_migrations(tmp_path):
    csv_path = _escrever_csv(tmp_path, [_linha()])
    with pytest.raises(CargaRecusada, match="alembic upgrade head"):
        carregar(csv_path, tmp_path / "vazio.db", COLETA)


def test_seed_versionado_carrega_sem_falhas_e_a_api_enxerga(banco_historico, monkeypatch):
    from fastapi.testclient import TestClient

    from api.app import app
    from api.database import get_db

    assert main(["--db", str(banco_historico)]) == 0
    with open(SEED, encoding="utf-8-sig", newline="") as fh:
        linhas = sum(1 for _ in csv.DictReader(fh))
    assert _contar(banco_historico, JobRecord) == linhas

    engine = make_engine(banco_historico)

    def sessao():
        with Session(engine) as db:
            yield db

    monkeypatch.setattr("api.app.init_db", lambda: None)
    app.dependency_overrides[get_db] = sessao
    try:
        with TestClient(app) as client:
            assert client.get("/health").json() == {"status": "ok", "vagas": linhas}
            assert client.get("/vagas", params={"limit": 1}).json()["total"] == linhas
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
