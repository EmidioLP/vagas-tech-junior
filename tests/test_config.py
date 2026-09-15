"""DATABASE_URL: precedencia, validacao e mensagens sem segredo. Sem rede."""

from __future__ import annotations

import os

import pytest

from scraper.config import ConfiguracaoError, obter_database_url

URL_AMBIENTE = "postgresql://ambiente:senha-ficticia@ep-ambiente.exemplo.test/vagas"
URL_LOCAL = (
    "postgresql://local:senha-ficticia@ep-exemplo.exemplo.test/vagas"
    "?sslmode=require&channel_binding=require"
)
URL_LEGADO = "postgresql://legado:senha-ficticia@ep-legado.exemplo.test/vagas"


def _arquivo(pasta, nome, conteudo):
    caminho = pasta / nome
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_ambiente_vence_os_arquivos(tmp_path):
    local = _arquivo(tmp_path, ".env.local", f"DATABASE_URL={URL_LOCAL}\n")
    url = obter_database_url(environ={"DATABASE_URL": URL_AMBIENTE}, arquivos=[local])
    assert url == URL_AMBIENTE


def test_env_local_vence_env_legado(tmp_path):
    local = _arquivo(tmp_path, ".env.local", f"DATABASE_URL={URL_LOCAL}\n")
    legado = _arquivo(tmp_path, ".env", f"DATABASE_URL={URL_LEGADO}\n")
    assert obter_database_url(environ={}, arquivos=[local, legado]) == URL_LOCAL


def test_env_legado_usado_sem_env_local(tmp_path):
    legado = _arquivo(tmp_path, ".env", f"DATABASE_URL={URL_LEGADO}\n")
    inexistente = tmp_path / ".env.local"
    assert obter_database_url(environ={}, arquivos=[inexistente, legado]) == URL_LEGADO


def test_env_local_sem_database_url_passa_para_o_proximo(tmp_path):
    local = _arquivo(tmp_path, ".env.local", "NEON_BRANCH=feature\n")
    legado = _arquivo(tmp_path, ".env", f"DATABASE_URL={URL_LEGADO}\n")
    assert obter_database_url(environ={}, arquivos=[local, legado]) == URL_LEGADO


def test_parametros_do_neon_sao_mantidos(tmp_path):
    local = _arquivo(tmp_path, ".env.local", f'DATABASE_URL="{URL_LOCAL}"\n')
    url = obter_database_url(environ={}, arquivos=[local])
    assert url.endswith("?sslmode=require&channel_binding=require")


def test_prefixo_legado_postgres_e_aceito():
    url = "postgres://u:senha-ficticia@ep-exemplo.exemplo.test/vagas"
    assert obter_database_url(environ={"DATABASE_URL": url}, arquivos=[]) == url


@pytest.mark.parametrize("ambiente", [{}, {"DATABASE_URL": ""}, {"DATABASE_URL": "  "}])
def test_ausente_falha_com_instrucao(ambiente):
    with pytest.raises(ConfiguracaoError) as erro:
        obter_database_url(environ=ambiente, arquivos=[])
    mensagem = str(erro.value)
    assert "DATABASE_URL" in mensagem
    assert "neon env pull" in mensagem


@pytest.mark.parametrize(
    "invalida",
    [
        "mysql://usuario:segredo@host/db",
        "sqlite:///segredo.db",
        "usuario:segredo@host/db",
        "postgresql:///segredo",
    ],
)
def test_invalida_falha_sem_ecoar_o_valor(invalida):
    with pytest.raises(ConfiguracaoError) as erro:
        obter_database_url(environ={"DATABASE_URL": invalida}, arquivos=[])
    assert "segredo" not in str(erro.value)
    assert "usuario" not in str(erro.value)


def test_ler_arquivo_nao_altera_os_environ(tmp_path):
    local = _arquivo(
        tmp_path, ".env.local", f"DATABASE_URL={URL_LOCAL}\nNEON_BRANCH=feature\n"
    )
    obter_database_url(environ={}, arquivos=[local])
    assert "DATABASE_URL" not in os.environ
    assert "NEON_BRANCH" not in os.environ
