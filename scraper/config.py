"""Configuracao central do projeto.

Tudo que voce provavelmente vai querer ajustar (termos de busca, delays, caminhos)
esta neste arquivo ou nos YAMLs em `scraper/rules/`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = Path(__file__).resolve().parent / "rules"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

USER_AGENT = (
    "vagas-tech-junior/1.0 (estudo de mercado de trabalho) python-requests"
)

# Termos usados na busca. Cada termo vira uma consulta separada em cada portal.
SEARCH_TERMS: list[str] = [
    "desenvolvedor junior",
    "desenvolvedor jr",
    "programador junior",
    "analista de sistemas junior",
    "estagio desenvolvimento",
    "estagio ti",
    "estagio tecnologia",
    "trainee tecnologia",
    "engenheiro de dados junior",
    "analista de dados junior",
    "qa junior",
    "devops junior",
    "suporte tecnico junior",
]


@dataclass
class Settings:
    """Parametros de execucao. Sobrescritos pela CLI em `main.py`."""

    search_terms: list[str] = field(default_factory=lambda: list(SEARCH_TERMS))
    # Todos os portais que funcionam hoje. Ver `scraper/sources/__init__.py`.
    sources: list[str] = field(
        default_factory=lambda: ["gupy", "vagas", "programathor", "trampos",
                                 "linkedin", "querovagastech", "geekhunter"]
    )
    output_dir: Path = DEFAULT_OUTPUT_DIR

    # Educacao com o servidor
    delay_seconds: float = 1.5
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    user_agent: str = USER_AGENT

    # Limites de coleta
    page_size: int = 100  # a API da Gupy rejeita limit > 100 (HTTP 400)
    max_pages_per_term: int = 5

    # Filtros
    only_junior: bool = True

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

# Em ordem de precedencia, depois das variaveis ja definidas no ambiente.
# `.env.local` e o que `neon env pull` gera; `.env` e o formato legado.
ARQUIVOS_ENV: tuple[Path, ...] = (PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env")

_ESQUEMAS_POSTGRES = {"postgres", "postgresql", "postgresql+psycopg"}

_MENSAGEM_AUSENTE = (
    "DATABASE_URL não definida. Defina a variável no ambiente ou gere o "
    ".env.local com `neon env pull --service postgres` "
    "(veja docs/neon-setup.md)."
)


class ConfiguracaoError(RuntimeError):
    """Configuracao obrigatoria ausente ou invalida.

    A mensagem nunca inclui o valor recebido: uma URL de banco carrega senha.
    """


def _fontes(
    environ: Mapping[str, str] | None,
    arquivos: Sequence[Path] | None,
) -> Iterator[Mapping[str, str | None]]:
    """Ambiente, depois cada arquivo existente, lidos so quando necessarios.

    Os arquivos sao lidos sem tocar em `os.environ`, para que carregar a
    configuracao nao vaze a URL para subprocessos nem entre testes.
    """
    yield os.environ if environ is None else environ
    for arquivo in ARQUIVOS_ENV if arquivos is None else arquivos:
        if Path(arquivo).is_file():
            yield dotenv_values(arquivo)


def _valor(fonte: Mapping[str, str | None], chave: str) -> str:
    return (fonte.get(chave) or "").strip()


def _validar_postgres(valor: str) -> str:
    partes = urlsplit(valor)
    if partes.scheme not in _ESQUEMAS_POSTGRES:
        raise ConfiguracaoError(
            "DATABASE_URL precisa ser uma URL PostgreSQL, começando com "
            "postgresql:// ou postgres://."
        )
    if not partes.hostname:
        raise ConfiguracaoError(
            "DATABASE_URL não tem host. Gere a URL novamente com "
            "`neon env pull --service postgres`."
        )
    return valor


def obter_database_url(
    environ: Mapping[str, str] | None = None,
    arquivos: Sequence[Path] | None = None,
) -> str:
    """DATABASE_URL, na ordem: ambiente > `.env.local` > `.env`."""
    for fonte in _fontes(environ, arquivos):
        valor = _valor(fonte, "DATABASE_URL")
        if valor:
            return _validar_postgres(valor)
    raise ConfiguracaoError(_MENSAGEM_AUSENTE)


def obter_url_migrations(
    environ: Mapping[str, str] | None = None,
    arquivos: Sequence[Path] | None = None,
) -> str:
    """URL para migrations: a conexao direta (DATABASE_URL_UNPOOLED) quando existir.

    No Neon, DATABASE_URL passa pelo PgBouncer em modo transacao, que quebra
    DDL e estado de sessao. A primeira fonte que define qualquer uma das duas
    variaveis decide, para nunca combinar bancos de fontes diferentes.
    """
    for fonte in _fontes(environ, arquivos):
        valor = _valor(fonte, "DATABASE_URL_UNPOOLED") or _valor(fonte, "DATABASE_URL")
        if valor:
            return _validar_postgres(valor)
    raise ConfiguracaoError(_MENSAGEM_AUSENTE)
