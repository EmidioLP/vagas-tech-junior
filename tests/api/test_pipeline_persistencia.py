"""Integracao: pipeline -> banco, com uma coleta fixa no lugar da rede.

Fluxo exercitado: 6 vagas brutas -> senioridade (-1 senior) -> dedupe (-1 cruzada)
-> portao de tecnologia (-1 contabil) -> 3 vagas -> jobs/job_snapshots.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.database import make_engine
from api.models import JobRecord, JobSnapshot
from scraper import pipeline
from scraper.config import ConfiguracaoError, Settings
from scraper.models import Job

DESCRICAO_BACKEND = "APIs REST em Java com Spring Boot e PostgreSQL."


def _coleta(descricao_backend: str = DESCRICAO_BACKEND) -> list[Job]:
    """Objetos novos a cada chamada: o pipeline preenche area, skills etc."""
    return [
        Job(source="gupy", external_id="1", title="Desenvolvedor Backend Júnior",
            company="ACME", description=descricao_backend, workplace_type="Remoto"),
        Job(source="gupy", external_id="2", title="Desenvolvedor Backend Sênior",
            company="ACME", description="APIs REST em Java com Spring Boot."),
        Job(source="gupy", external_id="3", title="Analista Contábil Júnior",
            company="Globex", description="Conciliação contábil, apuração fiscal e fechamento mensal."),
        Job(source="vagas", external_id="10", title="Desenvolvedor Backend Júnior",
            company="ACME Ltda", description="Java."),
        Job(source="vagas", external_id="11", title="Estágio em Suporte Técnico",
            company="Umbrella", description="Atendimento a usuários, chamados e redes."),
        Job(source="linkedin", external_id="20", title="Desenvolvedor Front-End Júnior",
            company="Initech"),
    ]


@pytest.fixture
def settings(tmp_path):
    return Settings(sources=["gupy", "vagas", "linkedin"], output_dir=tmp_path / "output")


def _rodar(monkeypatch, settings, **kwargs):
    coleta = kwargs.pop("coleta", {})
    monkeypatch.setattr(pipeline, "collect", lambda _s: (_coleta(**coleta), [], 0))
    return pipeline.run(settings, **kwargs)


def _contagens(resumo) -> tuple[int, int, int, int, int]:
    return (resumo.jobs_criados, resumo.jobs_atualizados, resumo.snapshots_criados,
            resumo.snapshots_ignorados, resumo.falhas)


def _linhas(banco) -> tuple[int, int]:
    engine = make_engine(banco)
    try:
        with Session(engine) as db:
            return (db.scalar(select(func.count()).select_from(JobRecord)),
                    db.scalar(select(func.count()).select_from(JobSnapshot)))
    finally:
        engine.dispose()


def test_pipeline_grava_no_banco_e_reexecucao_e_idempotente(monkeypatch, settings, banco_historico):
    primeira = _rodar(monkeypatch, settings, destino_db=banco_historico)
    assert sorted(j.source_key for j in primeira.jobs) == ["gupy:1", "linkedin:20", "vagas:11"]
    assert _contagens(primeira.persistencia) == (3, 0, 3, 0, 0)
    assert _linhas(banco_historico) == (3, 3)

    segunda = _rodar(monkeypatch, settings, destino_db=banco_historico)
    assert _contagens(segunda.persistencia) == (0, 3, 0, 3, 0)
    assert _linhas(banco_historico) == (3, 3)

    terceira = _rodar(monkeypatch, settings, destino_db=banco_historico,
                      coleta={"descricao_backend": "APIs REST em Java, Spring Boot e Kafka."})
    assert _contagens(terceira.persistencia) == (0, 3, 1, 2, 0)
    assert _linhas(banco_historico) == (3, 4)

    # CSV e opcional: sem --csv, nenhum arquivo e gerado.
    assert primeira.files == {}
    assert not settings.output_dir.exists()
    assert primeira.meta["persistencia"]["por_fonte"]["gupy"]["jobs_criados"] == 1


def _nao_deve_coletar(_settings):
    raise AssertionError("a coleta não deveria começar sem banco válido")


def test_sem_database_url_falha_antes_de_coletar(monkeypatch, settings):
    monkeypatch.setattr(pipeline, "collect", _nao_deve_coletar)
    with pytest.raises(ConfiguracaoError, match="DATABASE_URL"):
        pipeline.run(settings)


def test_banco_sem_migrations_falha_antes_de_coletar(monkeypatch, settings, tmp_path):
    monkeypatch.setattr(pipeline, "collect", _nao_deve_coletar)
    with pytest.raises(ConfiguracaoError, match="alembic upgrade head"):
        pipeline.run(settings, destino_db=tmp_path / "vazio.db")


def test_sem_banco_com_csv_so_exporta(monkeypatch, settings):
    resultado = _rodar(monkeypatch, settings, persistir=False, exportar_csv=True,
                       with_charts=False)
    assert resultado.persistencia is None
    assert resultado.files["jobs_csv"].is_file()
