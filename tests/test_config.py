"""DATABASE_URL: precedencia, validacao e mensagens sem segredo. Sem rede."""

from __future__ import annotations

import os

import pytest

from scraper.config import ConfiguracaoError, obter_database_url, obter_url_migrations

URL_AMBIENTE = "postgresql://ambiente:senha-ficticia@ep-ambiente.exemplo.test/vagas"
URL_LOCAL = (
    "postgresql://local:senha-ficticia@ep-exemplo.exemplo.test/vagas"
    "?sslmode=require&channel_binding=require"
)
URL_LEGADO = "postgresql://legado:senha-ficticia@ep-legado.exemplo.test/vagas"
URL_POOLED = "postgresql://local:senha-ficticia@pool.exemplo.test/vagas?sslmode=require"
URL_DIRETA = "postgresql://local:senha-ficticia@direto.exemplo.test/vagas?sslmode=require"


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


# --- URL de migrations -------------------------------------------------------


def _neon_local(tmp_path):
    return _arquivo(
        tmp_path,
        ".env.local",
        f"DATABASE_URL={URL_POOLED}\nDATABASE_URL_UNPOOLED={URL_DIRETA}\n",
    )


def test_migrations_preferem_a_conexao_direta(tmp_path):
    assert obter_url_migrations(environ={}, arquivos=[_neon_local(tmp_path)]) == URL_DIRETA


def test_aplicacao_continua_na_conexao_pooled(tmp_path):
    assert obter_database_url(environ={}, arquivos=[_neon_local(tmp_path)]) == URL_POOLED


def test_migrations_sem_unpooled_usam_database_url(tmp_path):
    local = _arquivo(tmp_path, ".env.local", f"DATABASE_URL={URL_POOLED}\n")
    assert obter_url_migrations(environ={}, arquivos=[local]) == URL_POOLED


def test_migrations_nao_misturam_fontes(tmp_path):
    """O banco exportado no shell vence a URL direta de outro banco no .env.local."""
    url = obter_url_migrations(
        environ={"DATABASE_URL": URL_AMBIENTE}, arquivos=[_neon_local(tmp_path)]
    )
    assert url == URL_AMBIENTE


def test_migrations_sem_url_falham():
    with pytest.raises(ConfiguracaoError, match="DATABASE_URL"):
        obter_url_migrations(environ={}, arquivos=[])


def test_migrations_url_invalida_nao_e_ecoada():
    with pytest.raises(ConfiguracaoError) as erro:
        obter_url_migrations(
            environ={"DATABASE_URL_UNPOOLED": "mysql://usuario:segredo@host/db"},
            arquivos=[],
        )
    assert "segredo" not in str(erro.value)
