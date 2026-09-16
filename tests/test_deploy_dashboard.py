"""Deploy do dashboard (docs/deploy.md): dependencias enxutas, sem segredo no git e
GRANTs em dia com as tabelas que o dashboard le."""

from __future__ import annotations

import re
import subprocess

import pytest

from scraper.config import PROJECT_ROOT

DOC = PROJECT_ROOT / "docs" / "deploy.md"


def _pacotes(arquivo) -> set[str]:
    nomes = set()
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if linha and not linha.startswith("-"):
            nomes.add(re.split(r"[<>=\[ ]", linha, maxsplit=1)[0].lower())
    return nomes


def test_streamlit_cloud_instala_so_as_dependencias_do_dashboard():
    entrypoint = PROJECT_ROOT / "dashboard" / "requirements.txt"
    linhas = [linha.strip() for linha in entrypoint.read_text(encoding="utf-8").splitlines()
              if linha.strip() and not linha.lstrip().startswith("#")]
    assert linhas == ["-r ../requirements-dashboard.txt"]

    pacotes = _pacotes(PROJECT_ROOT / "requirements-dashboard.txt")
    assert {"streamlit", "sqlalchemy", "psycopg", "python-dotenv"} <= pacotes
    assert not pacotes & {"fastapi", "uvicorn", "requests", "beautifulsoup4", "pyyaml", "matplotlib"}


def test_secrets_do_streamlit_nunca_vao_para_o_git():
    try:
        saida = subprocess.run(
            ["git", "check-ignore", ".streamlit/secrets.toml", ".env.local"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        pytest.skip("git não instalado")
    if saida.returncode == 128:
        pytest.skip("fora de um repositório git")
    assert saida.stdout.split() == [".streamlit/secrets.toml", ".env.local"]


def test_doc_nao_tem_url_de_banco_real():
    texto = DOC.read_text(encoding="utf-8")
    for url in re.findall(r"postgres(?:ql)?://\S+", texto):
        assert "<SENHA>" in url and "<host>" in url


def test_grants_cobrem_as_tabelas_que_o_dashboard_le():
    from api import models
    from dashboard import consultas

    tabelas_lidas = set()
    for nome in dir(consultas):
        objeto = getattr(consultas, nome)
        tabela = getattr(objeto, "__table__", None) if isinstance(objeto, type) else None
        if tabela is not None:
            tabelas_lidas.add(tabela.name)
        elif objeto is models.job_snapshot_tecnologias:
            tabelas_lidas.add(objeto.name)

    grant = re.search(r"GRANT SELECT ON (.+?)\s+TO dashboard_leitura", DOC.read_text(encoding="utf-8"),
                      re.DOTALL)
    assert grant, "docs/deploy.md sem o GRANT SELECT do papel do dashboard"
    concedidas = {t.strip() for t in grant.group(1).split(",")}
    assert concedidas == tabelas_lidas == {
        "jobs", "job_snapshots", "job_snapshot_tecnologias", "tecnologias", "collection_runs"}
