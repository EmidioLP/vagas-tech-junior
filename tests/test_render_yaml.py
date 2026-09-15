"""render.yaml: a API le do Neon sem segredo no git e sem apagar o banco no boot."""

from __future__ import annotations

import yaml

from scraper.config import PROJECT_ROOT

RENDER = PROJECT_ROOT / "render.yaml"


def _servico() -> dict:
    [servico] = yaml.safe_load(RENDER.read_text(encoding="utf-8"))["services"]
    return servico


def _variaveis() -> dict[str, dict]:
    return {v["key"]: v for v in _servico()["envVars"]}


def test_database_url_declarada_sem_valor_no_git():
    variavel = _variaveis()["DATABASE_URL"]
    assert variavel.get("sync") is False
    assert "value" not in variavel


def test_nenhuma_url_de_banco_no_arquivo():
    texto = RENDER.read_text(encoding="utf-8")
    assert "://" not in texto.replace("https://render.com", "")


def test_boot_so_sobe_a_api_sem_importar_nem_recriar():
    comando = _servico()["startCommand"]
    assert "--recriar" not in comando
    assert "import_csv" not in comando
    assert comando.startswith("uvicorn api.app:app")


def test_health_check_e_build_da_api():
    servico = _servico()
    assert servico["healthCheckPath"] == "/health"
    assert "requirements-api.txt" in servico["buildCommand"]
