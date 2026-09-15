"""Remove credenciais e enderecos do banco de um log antes de publica-lo.

Usado pelo workflow de coleta (`.github/workflows/collect.yml`) antes de subir o
log como artefato: a mascara de secrets do GitHub vale para o log do job, nao
para arquivos enviados.

    python scripts/sanitizar_log.py coleta/coleta.log coleta/coleta.sanitizado.log

Os valores de DATABASE_URL e DATABASE_URL_UNPOOLED do ambiente (e suas partes:
senha, usuario e host) sao removidos literalmente. Alem disso, qualquer URL com
credencial, qualquer URL PostgreSQL e qualquer host do Neon viram `***`.
"""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import unquote, urlsplit

OCULTO = "***"
VARIAVEIS = ("DATABASE_URL", "DATABASE_URL_UNPOOLED")

# Qualquer URL com usuario:senha@, de qualquer esquema.
_URL_COM_CREDENCIAL = re.compile(
    r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@'\"]+:[^\s@'\"]*@[^\s'\"]*"
)
# URL do PostgreSQL mesmo sem senha: host e usuario tambem nao saem.
_URL_POSTGRES = re.compile(r"postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]*", re.IGNORECASE)
_HOST_NEON = re.compile(r"[a-zA-Z0-9.-]+\.neon\.tech\b", re.IGNORECASE)
# Partes curtas demais (usuario "u") apagariam letras soltas do log inteiro.
_TAMANHO_MINIMO = 4


def _partes(valor: str) -> set[str]:
    partes = {valor}
    try:
        url = urlsplit(valor)
        candidatos = (url.password, url.username, url.hostname)
    except ValueError:
        candidatos = ()
    for candidato in candidatos:
        if candidato:
            partes.update({candidato, unquote(candidato)})
    return {p for p in partes if len(p) >= _TAMANHO_MINIMO}


def segredos_do_ambiente(environ: Mapping[str, str] | None = None) -> list[str]:
    environ = os.environ if environ is None else environ
    return [valor for nome in VARIAVEIS if (valor := (environ.get(nome) or "").strip())]


def sanitizar(texto: str, segredos: Iterable[str] = ()) -> str:
    """Texto sem os segredos informados nem URLs/hosts de banco."""
    literais = sorted({p for s in segredos for p in _partes(s)}, key=len, reverse=True)
    for literal in literais:  # do maior para o menor: a URL inteira antes da senha
        texto = texto.replace(literal, OCULTO)
    texto = _URL_COM_CREDENCIAL.sub(OCULTO, texto)
    texto = _URL_POSTGRES.sub(OCULTO, texto)
    return _HOST_NEON.sub(OCULTO, texto)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entrada", type=Path, help="Log original.")
    parser.add_argument("saida", type=Path, help="Onde gravar o log sanitizado.")
    args = parser.parse_args(argv)

    texto = args.entrada.read_text(encoding="utf-8", errors="replace")
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(sanitizar(texto, segredos_do_ambiente()), encoding="utf-8")
    print(f"Log sanitizado gravado em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
