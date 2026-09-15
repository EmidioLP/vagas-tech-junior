"""Workflows do GitHub Actions: permissoes minimas, DATABASE_URL so via Secret e
agendamento diario que so acorda a guarda de intervalo."""

from __future__ import annotations

import re

import pytest
import yaml

from scraper.config import PROJECT_ROOT

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
NOMES = ["ci.yml", "collect.yml"]


def _texto(nome: str) -> str:
    return (WORKFLOWS / nome).read_text(encoding="utf-8")


def _carregar(nome: str) -> dict:
    return yaml.safe_load(_texto(nome))


def _gatilhos(workflow: dict) -> dict:
    # O PyYAML segue o YAML 1.1 e le a chave `on` como o booleano True.
    return workflow.get("on", workflow.get(True))


def _passos(workflow: dict) -> list[dict]:
    return [passo for job in workflow["jobs"].values() for passo in job["steps"]]


def _passo(workflow: dict, nome: str) -> dict:
    return next(p for p in _passos(workflow) if p.get("name") == nome)


@pytest.mark.parametrize("nome", NOMES)
def test_permissoes_minimas(nome):
    workflow = _carregar(nome)
    assert workflow["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in workflow["jobs"].values())


@pytest.mark.parametrize("nome", NOMES)
def test_scripts_nao_interpolam_expressoes(nome):
    """Inputs chegam por env; `${{ }}` dentro de `run` abriria injecao de shell."""
    for passo in _passos(_carregar(nome)):
        assert "${{" not in passo.get("run", ""), passo.get("name")


def test_ci_roda_a_suite_em_push_e_pr_sem_segredos():
    assert "secrets" not in _texto("ci.yml")
    assert "DATABASE_URL" not in _texto("ci.yml")

    workflow = _carregar("ci.yml")
    assert {"push", "pull_request"} <= set(_gatilhos(workflow))
    assert any(p.get("run") == "python -m pytest -q" for p in _passos(workflow))


def test_coleta_acorda_todo_dia_e_pode_ser_disparada_manualmente():
    gatilhos = _gatilhos(_carregar("collect.yml"))
    assert set(gatilhos) == {"schedule", "workflow_dispatch"}

    crons = [item["cron"] for item in gatilhos["schedule"]]
    # Um cron diario fixo: a frequencia efetiva e da guarda, nunca do YAML.
    assert len(crons) == 1
    assert re.fullmatch(r"\d{1,2} \d{1,2} \* \* \*", crons[0])


def test_agendada_respeita_o_intervalo_e_manual_forca_por_padrao():
    workflow = _carregar("collect.yml")
    script = _passo(workflow, "Coletar")["run"]
    assert "--trigger schedule --respect-interval" in script
    assert "--trigger manual" in script

    entrada = _gatilhos(workflow)["workflow_dispatch"]["inputs"]["respeitar_intervalo"]
    assert entrada["type"] == "boolean"
    assert entrada["default"] is False


def test_intervalo_vem_de_variable_e_nao_de_secret():
    env = _passo(_carregar("collect.yml"), "Coletar")["env"]
    assert env["COLLECTION_INTERVAL_DAYS"] == "${{ vars.COLLECTION_INTERVAL_DAYS }}"
    assert "secrets.COLLECTION_INTERVAL_DAYS" not in _texto("collect.yml")


def test_database_url_so_vem_do_secret_nos_passos():
    workflow = _carregar("collect.yml")
    assert "DATABASE_URL" not in (workflow.get("env") or {})
    assert all("DATABASE_URL" not in (job.get("env") or {}) for job in workflow["jobs"].values())

    com_banco = [p for p in _passos(workflow) if "DATABASE_URL" in (p.get("env") or {})]
    assert [p["name"] for p in com_banco] == ["Coletar", "Sanitizar log"]
    for passo in com_banco:
        assert passo["env"]["DATABASE_URL"] == "${{ secrets.DATABASE_URL }}"
    assert all("DATABASE_URL" not in p.get("run", "") for p in _passos(workflow))


def test_coleta_roda_o_comando_oficial_sem_debug():
    script = _passo(_carregar("collect.yml"), "Coletar")["run"]
    assert "python main.py" in script
    assert "--resumo coleta/resumo.md" in script
    assert not re.search(r"\s-v\b|--verbose", script)


def test_artefato_so_leva_arquivos_sanitizados_e_so_em_falha():
    uploads = [
        p for p in _passos(_carregar("collect.yml"))
        if p.get("uses", "").startswith("actions/upload-artifact")
    ]
    assert uploads
    for passo in uploads:
        assert passo["if"] == "failure()"
        assert set(passo["with"]["path"].split()) == {
            "coleta/coleta.sanitizado.log", "coleta/resumo.md",
        }
