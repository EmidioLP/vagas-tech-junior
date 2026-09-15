"""CLI: combinacoes de banco e CSV."""

from __future__ import annotations

import pytest

import main as cli
from scraper import pipeline


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
