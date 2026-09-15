"""Schema historico: identidade (jobs) separada dos estados observados (job_snapshots).

O banco sai de `alembic upgrade head`, para testar o schema da migration e nao o
do create_all. O SQLite so aplica FKs com `PRAGMA foreign_keys=ON`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

pytest.importorskip("alembic", reason="Alembic não instalado; testes do histórico pulados.")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, event, func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.models import (  # noqa: E402
    JobRecord,
    JobSnapshot,
    Tecnologia,
    job_snapshot_tecnologias,
)
from scraper.config import PROJECT_ROOT  # noqa: E402

COLETA_1 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
COLETA_2 = COLETA_1 + timedelta(days=7)


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{(tmp_path / 'historico.db').as_posix()}"
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")

    motor = create_engine(url)

    @event.listens_for(motor, "connect")
    def _ligar_fks(conexao, _registro):
        conexao.execute("PRAGMA foreign_keys=ON")

    yield motor
    motor.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as sessao:
        yield sessao


def _job(**extra) -> JobRecord:
    dados = dict(
        source="gupy", external_id="1001", url="https://exemplo.test/1001",
        first_seen_at=COLETA_1, last_seen_at=COLETA_1,
    )
    dados.update(extra)
    return JobRecord(**dados)


def _snapshot(job: JobRecord, collected_at=COLETA_1, **extra) -> JobSnapshot:
    dados = dict(
        job=job, collected_at=collected_at, title="Desenvolvedor Python Júnior",
        company="ACME", area="Backend", workplace_type="Remoto",
    )
    dados.update(extra)
    return JobSnapshot(**dados)


def _contar(db, alvo) -> int:
    return db.scalar(select(func.count()).select_from(alvo))


def test_mesma_vaga_em_duas_coletas_gera_um_job_e_dois_snapshots(db):
    job = _job()
    db.add_all([
        job,
        _snapshot(job, COLETA_2, title="Desenvolvedor Python Jr", workplace_type="Híbrido"),
        _snapshot(job, COLETA_1, published_date=date(2026, 8, 30)),
    ])
    db.commit()

    assert _contar(db, JobRecord) == 1
    assert _contar(db, JobSnapshot) == 2

    db.expire_all()
    job = db.scalar(select(JobRecord))
    assert [s.collected_at.replace(tzinfo=None) for s in job.snapshots] == [
        COLETA_1.replace(tzinfo=None), COLETA_2.replace(tzinfo=None),
    ]
    assert {s.job_id for s in job.snapshots} == {job.id}
    assert [s.workplace_type for s in job.snapshots] == ["Remoto", "Híbrido"]
    assert job.snapshots[0].published_date == date(2026, 8, 30)


def test_vaga_nova_comeca_ativa(db):
    job = _job()
    db.add(job)
    db.commit()
    db.refresh(job)
    assert job.is_active is True


def test_source_e_external_id_identificam_a_vaga(db):
    db.add(_job())
    db.commit()
    db.add(_job(url="https://exemplo.test/outra-url"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_mesmo_external_id_em_fontes_diferentes_sao_vagas_distintas(db):
    db.add_all([_job(), _job(source="vagas")])
    db.commit()
    assert _contar(db, JobRecord) == 2


def test_snapshot_exige_vaga_existente(db):
    db.add(JobSnapshot(job_id=999, collected_at=COLETA_1, title="Órfão"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_no_maximo_um_snapshot_por_vaga_por_coleta(db):
    job = _job()
    db.add_all([job, _snapshot(job), _snapshot(job)])
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize("campo", ["source", "external_id", "first_seen_at", "last_seen_at"])
def test_campos_obrigatorios_da_vaga(db, campo):
    db.add(_job(**{campo: None}))
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize("campo", ["title", "collected_at"])
def test_campos_obrigatorios_do_snapshot(db, campo):
    job = _job()
    db.add(job)
    db.commit()
    db.add(_snapshot(job, **{campo: None}))
    with pytest.raises(IntegrityError):
        db.commit()


def test_apagar_vaga_com_historico_e_bloqueado(db):
    job = _job()
    db.add_all([job, _snapshot(job)])
    db.commit()

    db.delete(job)
    with pytest.raises(IntegrityError):
        db.commit()


def test_snapshot_guarda_tecnologias_e_apagar_preserva_a_tecnologia(db):
    python = Tecnologia(nome="Python", grupo="linguagens")
    job = _job()
    snapshot = _snapshot(job, tecnologias=[python])
    db.add_all([python, job, snapshot])
    db.commit()

    db.expire_all()
    assert [t.nome for t in db.scalar(select(JobSnapshot)).tecnologias] == ["Python"]

    db.delete(db.scalar(select(JobSnapshot)))
    db.commit()
    assert _contar(db, job_snapshot_tecnologias) == 0
    assert db.scalar(select(Tecnologia.nome)) == "Python"
    assert _contar(db, JobRecord) == 1
