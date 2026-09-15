"""CLI: combinacoes de banco e CSV."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import main as cli
from scraper import pipeline
from scraper.models import SourceStats
from scraper.pipeline import PipelineResult


def test_no_db_sem_csv_e_recusado(capsys):
    with pytest.raises(SystemExit) as saida:
        cli.main(["--no-db"])
    assert saida.value.code == 2
    assert "--csv" in capsys.readouterr().err


def test_db_e_no_db_sao_incompativeis():
    with pytest.raises(SystemExit) as saida:
        cli.main(["--no-db", "--csv", "--db", "data/teste.db"])
    assert saida.value.code == 2


def test_sem_database_url_encerra_com_mensagem_antes_de_coletar(monkeypatch, capsys):
    pytest.importorskip("sqlalchemy")

    def _nao_deve_coletar(_settings):
        raise AssertionError("a coleta não deveria começar sem banco")

    monkeypatch.setattr(pipeline, "collect", _nao_deve_coletar)
    assert cli.main(["--sources", "gupy"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def _resultado(falhas: int = 0) -> PipelineResult:
    persistencia = SimpleNamespace(
        jobs_criados=2, jobs_atualizados=1, snapshots_criados=3,
        snapshots_ignorados=0, falhas=falhas,
        erros=[f"gupy:{i}: IntegrityError" for i in range(falhas)],
    )
    return PipelineResult(
        jobs=[object(), object(), object()],
        ranking=[{"posicao": 1, "area": "Backend", "vagas": 3, "percentual": 100.0}],
        stats=[SourceStats(source="gupy", requests_made=4, raw_jobs=10,
                           errors=["timeout"])],
        meta={"raw_jobs": 10, "dropped_seniority": 4, "duplicates": 2,
              "dropped_non_tech": 1, "requests": 4,
              "collected_at": "2026-09-15T12:00:00+00:00"},
        persistencia=persistencia,
    )


def test_resumo_grava_contagens_da_coleta(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _resultado())
    destino = tmp_path / "coleta" / "resumo.md"

    assert cli.main(["--sources", "gupy", "--resumo", str(destino)]) == 0

    texto = destino.read_text(encoding="utf-8")
    assert "concluída (exit 0)" in texto
    assert "| gupy | 4 | 10 | 1 |" in texto
    assert "| **Final** | **3** |" in texto
    assert "| 1 | Backend | 3 | 100.0 |" in texto
    assert "| 2 | 1 | 3 | 0 | 0 |" in texto


def test_resumo_lista_falhas_de_persistencia(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _resultado(falhas=2))
    destino = tmp_path / "resumo.md"

    assert cli.main(["--sources", "gupy", "--resumo", str(destino)]) == 1

    texto = destino.read_text(encoding="utf-8")
    assert "concluída com falhas (exit 1)" in texto
    assert "`gupy:1: IntegrityError`" in texto


def test_resumo_de_erro_de_configuracao_nao_vaza_a_url(monkeypatch, tmp_path):
    pytest.importorskip("sqlalchemy")
    # Esquema invalido: falha na validacao, antes de qualquer conexao.
    monkeypatch.setenv("DATABASE_URL", "mysql://usuario:senha-ficticia@db.exemplo.test/vagas")
    monkeypatch.setattr(pipeline, "collect", lambda _s: pytest.fail("não deveria coletar"))
    destino = tmp_path / "resumo.md"

    assert cli.main(["--sources", "gupy", "--resumo", str(destino)]) == 2

    texto = destino.read_text(encoding="utf-8")
    assert "erro de configuração (exit 2)" in texto
    assert "PostgreSQL" in texto
    for trecho in ("senha-ficticia", "usuario", "db.exemplo.test", "mysql://"):
        assert trecho not in texto
