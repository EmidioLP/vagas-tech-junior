"""Docker local: nenhum segredo entra na imagem e o `up` so sobe o que nao usa rede."""

from __future__ import annotations

import re

import yaml

from scraper.config import PROJECT_ROOT

COMPOSE = PROJECT_ROOT / "docker-compose.yml"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"

BANCO_LOCAL = "postgresql://vagas:vagas@db:5432/vagas"


def _servicos() -> dict[str, dict]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _ignorados() -> list[str]:
    linhas = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in linhas if l.strip() and not l.startswith("#")]


def _estagio(nome: str) -> str:
    """Texto do estagio `nome` do Dockerfile, ate o proximo FROM."""
    texto = DOCKERFILE.read_text(encoding="utf-8")
    inicio = re.search(rf"^FROM \S+ AS {nome}$", texto, flags=re.MULTILINE)
    assert inicio, f"estagio {nome!r} nao existe"
    resto = texto[inicio.end():]
    proximo = re.search(r"^FROM ", resto, flags=re.MULTILINE)
    return resto[:proximo.start()] if proximo else resto


def test_dockerignore_tira_segredos_e_dados_locais():
    # A imagem `completa` faz `COPY . .`: sem estas linhas o .env.local iria junto.
    ignorados = _ignorados()
    for padrao in (".env", ".env.*", ".neon", ".streamlit/secrets.toml",
                   "node_modules/", "data/", "output/", "coleta/", "*.db"):
        assert padrao in ignorados, padrao
    # A excecao tem de vir depois do padrao que ela reabre.
    assert ignorados.index("!.env.example") > ignorados.index(".env.*")


def test_dockerignore_deixa_passar_o_que_coleta_e_testes_precisam():
    ignorados = _ignorados()
    for caminho in ("main.py", "tests/", "docs/", "requirements.txt", "render.yaml"):
        assert caminho not in ignorados, caminho


def test_unica_url_de_banco_do_compose_e_a_do_postgres_local():
    texto = COMPOSE.read_text(encoding="utf-8")
    urls = set(re.findall(r"postgres\w*(?:\+\w+)?://\S+", texto))
    assert urls == {BANCO_LOCAL}


def test_up_padrao_nao_coleta_nem_roda_testes():
    servicos = _servicos()
    for nome in ("coleta", "testes"):
        assert servicos[nome].get("profiles"), nome
    for nome in ("db", "preparo", "api", "dashboard"):
        assert "profiles" not in servicos[nome], nome


def test_testes_rodam_sem_rede_e_sem_banco():
    testes = _servicos()["testes"]
    assert testes["network_mode"] == "none"
    assert "environment" not in testes
    assert "depends_on" not in testes


def test_preparo_migra_e_carrega_o_seed_antes_da_api_e_do_dashboard():
    servicos = _servicos()
    comando = servicos["preparo"]["command"]
    assert comando.index("alembic upgrade head") < comando.index("scripts/carregar_seed.py")
    # Sem a flag, o `up` seguinte a uma coleta local terminaria com erro.
    assert "--ignorar-banco-com-coletas" in comando
    for nome in ("api", "dashboard", "coleta"):
        dependencia = servicos[nome]["depends_on"]["preparo"]
        assert dependencia["condition"] == "service_completed_successfully", nome


def test_cada_servico_usa_o_estagio_com_as_dependencias_certas():
    servicos = _servicos()
    alvos = {nome: servicos[nome]["build"]["target"]
             for nome in ("preparo", "api", "dashboard", "coleta", "testes")}
    assert alvos == {"preparo": "api", "api": "api", "dashboard": "dashboard",
                     "coleta": "completa", "testes": "completa"}

    assert "requirements-api.txt" in _estagio("api")
    assert "requirements-dashboard.txt" in _estagio("dashboard")
    assert "-r requirements.txt" in _estagio("completa")


def test_so_a_imagem_completa_copia_o_repositorio_inteiro_e_nenhuma_roda_como_root():
    for nome in ("api", "dashboard", "completa"):
        estagio = _estagio(nome)
        assert "USER vagas" in estagio, nome
        assert (re.search(r"^COPY .*\. \.$", estagio, flags=re.MULTILINE) is not None) == (
            nome == "completa"), nome
