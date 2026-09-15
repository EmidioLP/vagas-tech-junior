"""Persistencia idempotente em jobs/job_snapshots, contra o schema das migrations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from api.database import make_engine
from api.models import JobRecord, JobSnapshot
from persistence import repositorio
from persistence.repositorio import persistir_vagas
from scraper.models import Job

COLETA_1 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
COLETA_2 = COLETA_1 + timedelta(days=7)
COLETA_3 = COLETA_2 + timedelta(days=7)


@pytest.fixture
def engine(banco_historico):
    motor = make_engine(banco_historico)
    yield motor
    motor.dispose()


def _vaga(**extra) -> Job:
    dados = dict(
        source="gupy", external_id="1001", title="Desenvolvedor Python Júnior",
        company="ACME", url="https://exemplo.test/1001",
        description="APIs com Python e SQL.", location="São Paulo, São Paulo",
        workplace_type="Remoto", published_date="2026-08-30", seniority="Júnior",
        area="Backend", area_score=12.0, area_matches="python(t)",
        skills=["Python", "SQL"],
    )
    dados.update(extra)
    return Job(**dados)


def _utc(momento: datetime) -> datetime:
    return momento.replace(tzinfo=timezone.utc) if momento.tzinfo is None else momento


def _contagens(resumo) -> tuple[int, int, int, int, int]:
    """(vagas criadas, atualizadas, snapshots criados, ignorados, falhas)"""
    return (resumo.jobs_criados, resumo.jobs_atualizados, resumo.snapshots_criados,
            resumo.snapshots_ignorados, resumo.falhas)


def _contar(engine, modelo) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(modelo))


def _job(engine, source="gupy", external_id="1001") -> JobRecord | None:
    with Session(engine) as db:
        return db.scalar(select(JobRecord).where(
            JobRecord.source == source, JobRecord.external_id == external_id
        ))


def _snapshots(engine, external_id="1001") -> list[JobSnapshot]:
    with Session(engine) as db:
        return list(db.scalars(
            select(JobSnapshot).join(JobRecord)
            .where(JobRecord.external_id == external_id)
            .order_by(JobSnapshot.collected_at)
        ))


def test_primeira_ingestao_cria_vaga_e_snapshot(engine):
    resumo = persistir_vagas([_vaga()], engine, COLETA_1)

    assert _contagens(resumo) == (1, 0, 1, 0, 0)
    job = _job(engine)
    assert (_utc(job.first_seen_at), _utc(job.last_seen_at)) == (COLETA_1, COLETA_1)
    assert job.is_active is True
    assert job.url == "https://exemplo.test/1001"

    [snapshot] = _snapshots(engine)
    assert snapshot.title == "Desenvolvedor Python Júnior"
    assert snapshot.published_date == date(2026, 8, 30)
    assert sorted(t.nome for t in snapshot.tecnologias) == ["Python", "SQL"]
    assert len(snapshot.content_hash) == 64


def test_repeticao_identica_nao_duplica_e_so_avanca_last_seen(engine):
    persistir_vagas([_vaga()], engine, COLETA_1)
    resumo = persistir_vagas([_vaga()], engine, COLETA_2)

    assert _contagens(resumo) == (0, 1, 0, 1, 0)
    assert (_contar(engine, JobRecord), _contar(engine, JobSnapshot)) == (1, 1)
    job = _job(engine)
    assert (_utc(job.first_seen_at), _utc(job.last_seen_at)) == (COLETA_1, COLETA_2)


def test_mesma_coleta_reexecutada_nao_grava_nada_novo(engine):
    persistir_vagas([_vaga()], engine, COLETA_1)
    resumo = persistir_vagas([_vaga(workplace_type="Híbrido")], engine, COLETA_1)

    assert _contagens(resumo) == (0, 1, 0, 1, 0)
    assert _contar(engine, JobSnapshot) == 1


def test_mesma_vaga_duas_vezes_no_lote_gera_um_snapshot(engine):
    resumo = persistir_vagas(
        [_vaga(), _vaga(description="Outra descrição da mesma vaga.")], engine, COLETA_1
    )

    assert _contagens(resumo) == (1, 1, 1, 1, 0)
    assert (_contar(engine, JobRecord), _contar(engine, JobSnapshot)) == (1, 1)


def test_alteracao_observavel_gera_snapshot_e_preserva_o_anterior(engine):
    persistir_vagas([_vaga()], engine, COLETA_1)
    [original] = _snapshots(engine)

    resumo = persistir_vagas([_vaga(workplace_type="Híbrido")], engine, COLETA_2)

    assert _contagens(resumo) == (0, 1, 1, 0, 0)
    antigo, novo = _snapshots(engine)
    assert (antigo.id, antigo.workplace_type, antigo.content_hash) == (
        original.id, "Remoto", original.content_hash
    )
    assert novo.workplace_type == "Híbrido"
    assert novo.content_hash != antigo.content_hash


def test_mudanca_so_nas_tecnologias_gera_snapshot(engine):
    persistir_vagas([_vaga()], engine, COLETA_1)
    persistir_vagas([_vaga(skills=["Python"])], engine, COLETA_2)

    antigo, novo = _snapshots(engine)
    assert sorted(t.nome for t in antigo.tecnologias) == ["Python", "SQL"]
    assert [t.nome for t in novo.tecnologias] == ["Python"]


def test_voltar_ao_estado_anterior_tambem_e_historico(engine):
    """A comparacao e com o snapshot imediatamente anterior, nao com todos."""
    persistir_vagas([_vaga()], engine, COLETA_1)
    persistir_vagas([_vaga(workplace_type="Híbrido")], engine, COLETA_2)
    persistir_vagas([_vaga()], engine, COLETA_3)

    assert [s.workplace_type for s in _snapshots(engine)] == ["Remoto", "Híbrido", "Remoto"]


def test_mesma_vaga_em_fontes_e_ids_distintos_sao_vagas_distintas(engine):
    """A dedupe entre portais e do pipeline; o banco so conhece (source, external_id)."""
    resumo = persistir_vagas(
        [_vaga(), _vaga(source="vagas", external_id="9", url="https://exemplo.test/9")],
        engine, COLETA_1,
    )

    assert _contagens(resumo) == (2, 0, 2, 0, 0)
    assert (_contar(engine, JobRecord), _contar(engine, JobSnapshot)) == (2, 2)


def test_falha_no_meio_da_vaga_desfaz_a_vaga_inteira(engine, monkeypatch):
    original = repositorio._gravar_snapshot

    def _quebra(db, registro, *args):
        if registro.external_id == "1002":
            raise IntegrityError("INSERT simulado", {}, Exception("falha simulada"))
        return original(db, registro, *args)

    monkeypatch.setattr(repositorio, "_gravar_snapshot", _quebra)
    resumo = persistir_vagas(
        [_vaga(), _vaga(external_id="1002"), _vaga(external_id="1003")], engine, COLETA_1
    )

    assert _contagens(resumo) == (2, 0, 2, 0, 1)
    assert resumo.erros == ["gupy:1002: Exception"]
    # A vaga ja tinha sido inserida em `jobs` quando o snapshot falhou.
    assert _job(engine, external_id="1002") is None
    assert (_contar(engine, JobRecord), _contar(engine, JobSnapshot)) == (2, 2)


def test_dado_invalido_conta_falha_sem_derrubar_o_lote(engine):
    resumo = persistir_vagas(
        [_vaga(external_id="x" * 101), _vaga(title="  "), _vaga()], engine, COLETA_1
    )

    assert _contagens(resumo) == (1, 0, 1, 0, 2)
    assert _contar(engine, JobRecord) == 1


def test_id_longo_da_geekhunter_e_gravado_sem_corte(engine):
    """O portal publica o `identifier` do JobPosting como hash de 64 caracteres."""
    externo = "5f6eab294e8177773f3676900be149658eba55631166f6626e88192b3aadf4b7"
    resumo = persistir_vagas([_vaga(source="geekhunter", external_id=externo)], engine, COLETA_1)

    assert _contagens(resumo) == (1, 0, 1, 0, 0)
    assert _job(engine, source="geekhunter", external_id=externo) is not None


def test_falha_de_uma_fonte_nao_desfaz_fontes_ja_confirmadas(engine, monkeypatch):
    original = repositorio._gravar_vaga

    def _cai_a_conexao(db, insert, job, *args):
        if job.source_key == "vagas:2":
            raise OperationalError("SELECT simulado", {}, Exception("conexão perdida"))
        return original(db, insert, job, *args)

    monkeypatch.setattr(repositorio, "_gravar_vaga", _cai_a_conexao)
    resumo = persistir_vagas(
        [_vaga(), _vaga(source="vagas", external_id="1"),
         _vaga(source="vagas", external_id="2")],
        engine, COLETA_1,
    )

    assert _contagens(resumo.por_fonte["gupy"]) == (1, 0, 1, 0, 0)
    # vagas:1 tinha passado, mas a transacao da fonte inteira foi desfeita.
    assert _contagens(resumo.por_fonte["vagas"]) == (0, 0, 0, 0, 2)
    assert resumo.erros == ["vagas: transação desfeita (Exception)"]
    with Session(engine) as db:
        assert db.scalars(select(JobRecord.source)).all() == ["gupy"]


def test_coleta_antiga_gravada_depois_nao_faz_last_seen_retroceder(engine):
    persistir_vagas([_vaga()], engine, COLETA_2)
    persistir_vagas([_vaga()], engine, COLETA_1)

    job = _job(engine)
    assert (_utc(job.first_seen_at), _utc(job.last_seen_at)) == (COLETA_1, COLETA_2)


def test_vaga_vista_de_novo_volta_a_ficar_ativa(engine):
    persistir_vagas([_vaga()], engine, COLETA_1)
    with Session(engine) as db, db.begin():
        db.execute(update(JobRecord).values(is_active=False))

    persistir_vagas([_vaga()], engine, COLETA_2)
    assert _job(engine).is_active is True


def test_data_relativa_e_resolvida_contra_o_dia_da_coleta(engine):
    persistir_vagas([_vaga(published_date="Ontem")], engine, COLETA_1)
    assert _snapshots(engine)[0].published_date == date(2026, 8, 31)


def test_collected_at_sem_fuso_e_recusado(engine):
    with pytest.raises(ValueError, match="fuso"):
        persistir_vagas([_vaga()], engine, datetime(2026, 9, 1, 12, 0))


def test_lote_vazio_nao_toca_o_banco(engine):
    assert _contagens(persistir_vagas([], engine, COLETA_1)) == (0, 0, 0, 0, 0)
