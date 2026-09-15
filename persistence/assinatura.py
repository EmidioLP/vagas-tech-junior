"""Assinatura deterministica do estado de uma vaga numa coleta.

A persistencia compara a assinatura da coleta atual com a do snapshot anterior:
igual, a vaga nao mudou e nenhum snapshot novo e gravado; diferente, grava.

Versao 1 -- entram exatamente os campos que o snapshot grava:

    title, company, description, location, workplace_type, published_date,
    seniority, area, area_score, area_matches, tecnologias

Ficam de fora:
  - `url`: faz parte da identidade e mora em `jobs`;
  - `search_term`: depende de qual termo trouxe a vaga primeiro, nao do estado dela;
  - `collected_at`: toda coleta tem um, e a vaga nao muda por isso.

Normalizacao: texto tem as bordas aparadas e vazio vira null (`""` e `None` sao o
mesmo estado); `published_date` vai em ISO; `area_score` com 4 casas decimais;
`tecnologias` ordenadas e sem repeticao. O JSON canonico (chaves ordenadas, sem
espacos) e resumido com SHA-256.

Mudar os campos ou a normalizacao muda todos os hashes e faz a proxima coleta
gravar um snapshot novo para cada vaga. Quando isso for intencional, suba
`VERSAO`, que entra no hash e documenta a quebra.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from typing import Any

VERSAO = 1

CAMPOS_TEXTO = (
    "title", "company", "description", "location", "workplace_type",
    "seniority", "area", "area_matches",
)


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    return str(valor).strip() or None


def _data(valor: Any) -> str | None:
    if isinstance(valor, date):
        return valor.isoformat()
    return _texto(valor)


def _score(valor: Any) -> str | None:
    if valor is None or valor == "":
        return None
    return f"{float(valor):.4f}"


def assinatura_snapshot(campos: Mapping[str, Any]) -> str:
    """SHA-256 hex (64 caracteres) do estado observavel. Campo ausente vale null."""
    canonico: dict[str, Any] = {campo: _texto(campos.get(campo)) for campo in CAMPOS_TEXTO}
    canonico["v"] = VERSAO
    canonico["published_date"] = _data(campos.get("published_date"))
    canonico["area_score"] = _score(campos.get("area_score"))
    canonico["tecnologias"] = sorted(
        {nome for nome in (_texto(t) for t in campos.get("tecnologias") or ()) if nome}
    )
    texto = json.dumps(canonico, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
