"""Sanitizacao do log da coleta antes de virar artefato no GitHub Actions."""

from __future__ import annotations

from scripts import sanitizar_log
from scripts.sanitizar_log import sanitizar

HOST = "ep-exemplo-123.sa-east-1.aws.neon.tech"
URL = f"postgresql://neondb_owner:senha-ficticia@{HOST}/neondb?sslmode=require"


def _sem_vazamento(texto: str) -> None:
    for trecho in ("senha-ficticia", "neondb_owner", "neon.tech", "postgresql://"):
        assert trecho not in texto


def test_remove_a_url_e_cada_parte_do_segredo():
    log = (
        f"conectando em {URL}\n"
        f'connection to server at "{HOST}" failed for user "neondb_owner"\n'
        "senha usada: senha-ficticia\n"
    )
    _sem_vazamento(sanitizar(log, [URL]))


def test_sem_segredo_conhecido_ainda_remove_urls_de_banco():
    log = (
        "erro em postgres://u:outra-senha@db.exemplo.test:5432/vagas\n"
        "sem senha: postgresql+psycopg://leitor@db.exemplo.test/vagas\n"
        f"host solto: {HOST}\n"
    )
    limpo = sanitizar(log)
    assert "outra-senha" not in limpo
    assert "db.exemplo.test" not in limpo
    assert "neon.tech" not in limpo


def test_log_comum_fica_intacto():
    log = (
        "10:00:00  INFO    === Coletando em Gupy ===\n"
        "10:00:03  WARNING GET https://portal.api.gupy.io/api/job?name=qa+junior -> 429\n"
        "  Vagas criadas ........ 12\n"
    )
    assert sanitizar(log, [URL]) == log


def test_partes_curtas_do_segredo_nao_apagam_o_log():
    log = "Total bruto: 10 vagas"
    assert sanitizar(log, ["postgresql://u:p@h/db"]) == log


def test_cli_le_segredos_do_ambiente(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DATABASE_URL", URL)
    entrada = tmp_path / "coleta.log"
    saida = tmp_path / "saida" / "coleta.sanitizado.log"
    entrada.write_text(f"falhou em {HOST} com senha-ficticia\n", encoding="utf-8")

    assert sanitizar_log.main([str(entrada), str(saida)]) == 0

    _sem_vazamento(saida.read_text(encoding="utf-8"))
    _sem_vazamento(capsys.readouterr().out)
