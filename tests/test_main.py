"""CLI: combinacoes de banco e CSV, resumo da execucao e guarda de intervalo."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import main as cli
from scraper import pipeline
from scraper.execucao import Agenda, Decisao
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


def test_respect_interval_nao_combina_com_no_db(capsys):
    with pytest.raises(SystemExit) as saida:
        cli.main(["--respect-interval", "--no-db", "--csv"])
    assert saida.value.code == 2
    assert "--respect-interval" in capsys.readouterr().err


def test_respect_interval_sem_collection_interval_days_encerra_antes_de_coletar(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "collect", lambda _s: pytest.fail("não deveria coletar"))
    assert cli.main(["--respect-interval"]) == 2
    assert "COLLECTION_INTERVAL_DAYS" in capsys.readouterr().err


def _resultado(falhas: int = 0, status_linkedin: str = "ok") -> PipelineResult:
    persistencia = SimpleNamespace(
        jobs_criados=2, jobs_atualizados=1, snapshots_criados=3,
        snapshots_ignorados=0, falhas=falhas,
        erros=[f"gupy:{i}: IntegrityError" for i in range(falhas)],
    )
    if falhas:
        status, codigo = "partial", 1
    elif status_linkedin != "ok":
        status, codigo = "partial", 0
    else:
        status, codigo = "success", 0
    bloqueado = 3 if status_linkedin != "ok" else 0
    return PipelineResult(
        jobs=[object(), object(), object()],
        ranking=[{"posicao": 1, "area": "Backend", "vagas": 3, "percentual": 100.0}],
        stats=[
            SourceStats(source="gupy", requests_made=4, raw_jobs=10, errors=["timeout"]),
            SourceStats(source="linkedin", requests_made=3, requests_failed=bloqueado),
        ],
        meta={"raw_jobs": 10, "dropped_seniority": 4, "duplicates": 2,
              "dropped_non_tech": 1, "requests": 7, "gatilho": "manual",
              "collected_at": "2026-09-15T12:00:00+00:00"},
        persistencia=persistencia,
        status=status,
        exit_code=codigo,
        status_fontes={"gupy": "ok", "linkedin": status_linkedin},
        agenda=Agenda(date(2026, 9, 15), date(2026, 9, 17), 2),
        encerramento=SimpleNamespace(encerradas=1, ausentes=2, erros=[]),
    )


def test_resumo_grava_contagens_da_coleta(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _resultado())
    destino = tmp_path / "coleta" / "resumo.md"

    assert cli.main(["--sources", "gupy", "--resumo", str(destino)]) == 0

    agenda = "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026"
    assert f"{agenda} (a cada 2 dias)." in capsys.readouterr().out
    texto = destino.read_text(encoding="utf-8")
    assert f"- **{agenda}** (a cada 2 dias)" in texto
    assert "sucesso (exit 0)" in texto
    assert "| gupy | ok | 4 | 0 | 10 | 1 |" in texto
    assert "| **Final** | **3** |" in texto
    assert "| 1 | Backend | 3 | 100.0 |" in texto
    assert "| 2 | 1 | 3 | 0 | 0 |" in texto
    assert "**Vagas encerradas:** 1" in texto
    assert "**ausentes pela 1ª vez:** 2" in texto


def test_resumo_destaca_fonte_com_falha_sem_derrubar_a_execucao(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _resultado(status_linkedin="failed"))
    destino = tmp_path / "resumo.md"

    assert cli.main(["--resumo", str(destino)]) == 0

    texto = destino.read_text(encoding="utf-8")
    assert "parcial (exit 0)" in texto
    assert "| linkedin | **falhou** | 3 | 3 | 0 | 0 |" in texto
    assert "linkedin" in capsys.readouterr().out


def test_resumo_sem_alertas_informa_a_secao_de_qualidade(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _resultado())
    destino = tmp_path / "resumo.md"
    cli.main(["--sources", "gupy", "--resumo", str(destino)])
    assert "### Qualidade\n\nNenhum alerta." in destino.read_text(encoding="utf-8")


def test_resumo_e_terminal_mostram_alertas_de_qualidade(monkeypatch, tmp_path, capsys):
    from scraper.qualidade import ALTA, BAIXA, Alerta

    resultado = _resultado()
    resultado.status, resultado.exit_code = "partial", 1
    resultado.status_fontes["gupy"] = "partial"
    resultado.alertas = [
        Alerta("fonte_zerada", ALTA, "gupy", 0, "> 0", "gupy listou 0 vagas sem nenhuma requisição falha"),
        Alerta("url_invalida", BAIXA, "linkedin", 1, 0, "linkedin: 1 vaga(s) com URL que não é http(s)"),
    ]
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: resultado)
    destino = tmp_path / "resumo.md"

    assert cli.main(["--sources", "gupy", "--resumo", str(destino)]) == 1

    texto = destino.read_text(encoding="utf-8")
    assert ("| **alta** | fonte_zerada | gupy | 0 | > 0 "
            "| gupy listou 0 vagas sem nenhuma requisição falha |") in texto
    assert "| baixa | url_invalida | linkedin | 1 | 0 |" in texto
    saida = capsys.readouterr().out
    assert "Qualidade (2 alerta(s)):" in saida
    assert "! [alta] gupy listou 0 vagas" in saida


def test_resumo_lista_falhas_de_persistencia(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: _resultado(falhas=2))
    destino = tmp_path / "resumo.md"

    assert cli.main(["--sources", "gupy", "--resumo", str(destino)]) == 1

    texto = destino.read_text(encoding="utf-8")
    assert "parcial (exit 1)" in texto
    assert "`gupy:1: IntegrityError`" in texto


def test_coleta_pulada_informa_ultima_e_proxima_coleta(monkeypatch, tmp_path, capsys):
    decisao = Decisao(
        False,
        "última coleta completa em 15/09/2026, intervalo de 2 dia(s) ainda não cumprido",
        date(2026, 9, 17),
    )
    pulada = PipelineResult(
        jobs=[], ranking=[], status="skipped", exit_code=0, decisao=decisao,
        agenda=Agenda(date(2026, 9, 15), date(2026, 9, 17), 2),
        meta={"collected_at": "2026-09-16T09:00:00+00:00", "motivo": decisao.motivo,
              "gatilho": "schedule"},
    )
    monkeypatch.setattr(cli, "run", lambda *_a, **_k: pulada)
    destino = tmp_path / "resumo.md"

    assert cli.main(["--respect-interval", "--trigger", "schedule", "--resumo", str(destino)]) == 0

    agenda = "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026"
    saida = capsys.readouterr().out
    assert "Coleta pulada" in saida
    assert f"{agenda} (a cada 2 dias)." in saida
    assert "Nenhuma vaga" not in saida
    texto = destino.read_text(encoding="utf-8")
    assert "pulada (exit 0)" in texto
    assert f"- **{agenda}** (a cada 2 dias)" in texto


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
