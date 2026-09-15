"""Integracao: vagas que somem da listagem sao encerradas (`is_active = false`).

Regra: numa coleta completa, fonte com status ok e pelo menos uma vaga listada, a
vaga ausente em duas coletas seguidas, em dias diferentes, e encerrada. Nada e
apagado: o historico (snapshots) fica.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from api.database import make_engine
from api.models import JobRecord, JobSnapshot
from persistence import repositorio
from scraper import pipeline
from scraper.config import Settings
from scraper.models import Job, SourceStats

DIA_1 = datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc)
IDS = ("alfa", "beta", "gama")


def _coleta(sem=None, falham=(), vazias=(), senior=None):
    """Substitui `pipeline.collect`: tres vagas por fonte.

    `sem`: {fonte: ids que sumiram}; `senior`: {fonte: ids listados como senior,
    que o filtro de senioridade descarta}; `falham`/`vazias`: fontes bloqueadas ou
    que voltaram sem nenhuma vaga.
    """
    sem = sem or {}
    senior = senior or {}

    def _collect(settings):
        jobs: list[Job] = []
        stats: list[SourceStats] = []
        for fonte in settings.sources:
            if fonte in falham:
                stats.append(SourceStats(source=fonte, requests_made=3, requests_failed=3))
                continue
            if fonte in vazias:
                stats.append(SourceStats(source=fonte, requests_made=1))
                continue
            vagas = [
                Job(source=fonte, external_id=externo,
                    title=f"Desenvolvedor Backend {'Sênior' if externo in senior.get(fonte, ()) else 'Júnior'}",
                    company=f"{fonte}{externo}", description="APIs REST em Java com Spring Boot.")
                for externo in IDS if externo not in sem.get(fonte, ())
            ]
            jobs.extend(vagas)
            stats.append(SourceStats(source=fonte, requests_made=1, raw_jobs=len(vagas)))
        return jobs, stats, len(stats)

    return _collect


def _rodar(monkeypatch, banco, quando, settings=None, **coleta):
    monkeypatch.setattr(pipeline, "_agora", lambda: quando)
    monkeypatch.setattr(pipeline, "collect", _coleta(**coleta))
    return pipeline.run(settings or Settings(), destino_db=banco)


def _estado(banco, fonte="gupy") -> dict[str, JobRecord]:
    engine = make_engine(banco)
    try:
        with Session(engine, expire_on_commit=False) as db:
            return {r.external_id: r for r in db.scalars(
                select(JobRecord).where(JobRecord.source == fonte))}
    finally:
        engine.dispose()


def _snapshots(banco, fonte="gupy", externo="alfa") -> int:
    engine = make_engine(banco)
    try:
        with Session(engine) as db:
            return db.scalar(
                select(func.count()).select_from(JobSnapshot).join(JobRecord)
                .where(JobRecord.source == fonte, JobRecord.external_id == externo)
            )
    finally:
        engine.dispose()


def test_segunda_coleta_nao_duplica_vagas(monkeypatch, banco_historico):
    primeira = _rodar(monkeypatch, banco_historico, DIA_1)
    segunda = _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2))

    assert primeira.persistencia.jobs_criados > 0
    assert (segunda.persistencia.jobs_criados, segunda.persistencia.snapshots_criados) == (0, 0)
    assert len(_estado(banco_historico)) == len(IDS)


def test_vaga_ausente_uma_vez_continua_ativa(monkeypatch, banco_historico):
    _rodar(monkeypatch, banco_historico, DIA_1)
    resultado = _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2),
                       sem={"gupy": {"alfa"}})

    alfa = _estado(banco_historico)["alfa"]
    assert alfa.is_active
    assert alfa.missing_since is not None
    assert alfa.closed_at is None
    assert (resultado.encerramento.ausentes, resultado.encerramento.encerradas) == (1, 0)


def test_ausente_em_duas_coletas_seguidas_e_encerrada_sem_perder_historico(
    monkeypatch, banco_historico,
):
    _rodar(monkeypatch, banco_historico, DIA_1)
    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2), sem={"gupy": {"alfa"}})
    resultado = _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=4),
                       sem={"gupy": {"alfa"}})

    estado = _estado(banco_historico)
    assert not estado["alfa"].is_active
    assert estado["alfa"].closed_at.date() == date(2026, 9, 19)
    assert estado["beta"].is_active and estado["gama"].is_active
    assert _snapshots(banco_historico) == 1  # historico preservado
    assert resultado.encerramento.encerradas == 1
    assert resultado.meta["encerramento"]["por_fonte"]["gupy"] == {"ausentes": 0, "encerradas": 1}
    assert _estado(banco_historico, "vagas")["alfa"].is_active  # outra fonte, mesma id


def test_vaga_que_reaparece_zera_a_ausencia(monkeypatch, banco_historico):
    _rodar(monkeypatch, banco_historico, DIA_1)
    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2), sem={"gupy": {"alfa"}})
    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=4))
    assert _estado(banco_historico)["alfa"].missing_since is None

    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=6), sem={"gupy": {"alfa"}})
    alfa = _estado(banco_historico)["alfa"]
    assert alfa.is_active  # a contagem recomecou: e so a primeira ausencia
    assert alfa.missing_since is not None


def test_duas_coletas_no_mesmo_dia_contam_como_uma(monkeypatch, banco_historico):
    _rodar(monkeypatch, banco_historico, DIA_1)
    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2), sem={"gupy": {"alfa"}})
    # Execucao forcada tres horas depois da agendada.
    resultado = _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2, hours=3),
                       sem={"gupy": {"alfa"}})

    assert _estado(banco_historico)["alfa"].is_active
    assert resultado.encerramento.encerradas == 0


def test_vaga_encerrada_que_reaparece_volta_a_ativa(monkeypatch, banco_historico):
    _rodar(monkeypatch, banco_historico, DIA_1)
    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2), sem={"gupy": {"alfa"}})
    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=4), sem={"gupy": {"alfa"}})
    assert not _estado(banco_historico)["alfa"].is_active

    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=6))
    alfa = _estado(banco_historico)["alfa"]
    assert alfa.is_active
    assert (alfa.closed_at, alfa.missing_since) == (None, None)


def test_fonte_com_falha_ou_vazia_nao_encerra_nada(monkeypatch, banco_historico):
    _rodar(monkeypatch, banco_historico, DIA_1)
    _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2),
           sem={"gupy": {"alfa"}, "vagas": {"alfa"}})
    resultado = _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=4),
                       falham={"gupy"}, vazias={"vagas"})

    assert resultado.status == "partial"
    assert all(vaga.is_active for vaga in _estado(banco_historico).values())
    assert all(vaga.is_active for vaga in _estado(banco_historico, "vagas").values())
    assert "gupy" not in resultado.encerramento.por_fonte
    assert "vagas" not in resultado.encerramento.por_fonte


def test_coleta_de_escopo_parcial_nao_avalia_ausencias(monkeypatch, banco_historico):
    _rodar(monkeypatch, banco_historico, DIA_1)
    resultado = _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2),
                       settings=Settings(sources=["gupy"]), sem={"gupy": {"alfa"}})

    assert resultado.encerramento is None
    assert _estado(banco_historico)["alfa"].missing_since is None


def test_vaga_ainda_listada_mas_filtrada_nao_conta_como_ausente(monkeypatch, banco_historico):
    _rodar(monkeypatch, banco_historico, DIA_1)
    for dias in (2, 4):
        _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=dias),
               senior={"gupy": {"alfa"}})

    alfa = _estado(banco_historico)["alfa"]
    assert alfa.is_active
    assert alfa.missing_since is None


def test_erro_de_banco_no_encerramento_de_uma_fonte_nao_afeta_as_outras(
    monkeypatch, banco_historico,
):
    _rodar(monkeypatch, banco_historico, DIA_1)

    original = repositorio._encerrar_fonte

    def _falhar_na_gupy(engine, fonte, vistas, collected_at):
        if fonte == "gupy":
            raise OperationalError("UPDATE jobs", {}, Exception("conexão caiu"))
        return original(engine, fonte, vistas, collected_at)

    monkeypatch.setattr(repositorio, "_encerrar_fonte", _falhar_na_gupy)
    resultado = _rodar(monkeypatch, banco_historico, DIA_1 + timedelta(days=2),
                       sem={"gupy": {"alfa"}, "vagas": {"alfa"}})

    assert (resultado.status, resultado.exit_code) == ("partial", 1)
    assert "gupy: encerramento desfeito" in resultado.meta["motivo"]
    assert _estado(banco_historico)["alfa"].missing_since is None
    assert _estado(banco_historico, "vagas")["alfa"].missing_since is not None
