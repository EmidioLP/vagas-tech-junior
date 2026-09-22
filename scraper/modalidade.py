"""Inferencia da modalidade de trabalho pelo texto da vaga.

Complementa o campo estruturado do portal, nunca o substitui: so e usada quando a
fonte nao informou a modalidade (o card do LinkedIn e o do Vagas.com nao
distinguem presencial de hibrido). As regras vivem em `scraper/rules/modalidade.yml`
-- edite la, nao aqui.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from .config import RULES_DIR
from .models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO, WORKPLACE_ORDER, Job, normalize

_WS_RE = re.compile(r"\s+")


def _compilar(frases: list[str] | None) -> list[re.Pattern]:
    padroes = []
    for frase in frases or []:
        token = normalize(frase)
        if token:
            padroes.append(re.compile(rf"\b{re.escape(token)}\b"))
    return padroes


def sem_modalidade(valor: str | None) -> bool:
    """Modalidade ausente: vazia (nulo no banco) ou o rotulo "Não informado"."""
    return not (valor or "").strip() or valor == NAO_INFORMADO


class InferidorModalidade:
    """Decide a modalidade a partir de titulo, local e descricao."""

    def __init__(self, regras: dict) -> None:
        regras = regras or {}
        self.excecoes = _compilar(regras.get("excecoes"))
        validas = set(WORKPLACE_ORDER) - {NAO_INFORMADO}
        self.frases: dict[str, list[re.Pattern]] = {}
        self.palavras: dict[str, list[re.Pattern]] = {}
        for chave, destino in (("frases", self.frases), ("palavras", self.palavras)):
            for modalidade, lista in (regras.get(chave) or {}).items():
                if modalidade not in validas:
                    raise ValueError(f"modalidade desconhecida em modalidade.yml: {modalidade}")
                destino[modalidade] = _compilar(lista)

    @classmethod
    def from_file(cls, path: Path | None = None) -> "InferidorModalidade":
        path = path or (RULES_DIR / "modalidade.yml")
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def _limpar(self, texto: str | None) -> str:
        texto = normalize(texto)
        for padrao in self.excecoes:
            texto = padrao.sub(" ", texto)
        return _WS_RE.sub(" ", texto).strip()

    def _citadas(self, texto: str, com_palavras: bool) -> set[str]:
        grupos = [self.frases, self.palavras] if com_palavras else [self.frases]
        return {
            modalidade
            for grupo in grupos
            for modalidade, padroes in grupo.items()
            if any(p.search(texto) for p in padroes)
        }

    @staticmethod
    def _decidir(achadas: set[str]) -> str:
        """Hibrido com presencial e hibrido ("1 dia por semana presencial").

        Hibrido com remoto, ou remoto com presencial, e ambiguo -- "tecnologia
        100% remoto, demais times hibrido", "trabalho remoto ou hibrido" -- e
        nao vira chute.
        """
        if achadas in ({HIBRIDO}, {HIBRIDO, PRESENCIAL}):
            return HIBRIDO
        if achadas == {REMOTO}:
            return REMOTO
        if achadas == {PRESENCIAL}:
            return PRESENCIAL
        return NAO_INFORMADO

    def inferir(self, title: str = "", description: str = "", location: str = "") -> str:
        """Titulo e local decidem primeiro; a descricao so quando eles nao dizem nada.

        O titulo e o sinal mais direto ("Estagio em TI (Presencial)"); a descricao
        mistura a modalidade da vaga com a da empresa e a do processo seletivo.
        """
        curto = self._decidir(self._citadas(self._limpar(f"{title} {location}"), True))
        if curto != NAO_INFORMADO:
            return curto
        return self._decidir(self._citadas(self._limpar(description), False))


@lru_cache(maxsize=1)
def default_inferidor() -> InferidorModalidade:
    return InferidorModalidade.from_file()


def inferir_modalidade(title: str = "", description: str = "", location: str = "") -> str:
    return default_inferidor().inferir(title, description, location)


def completar_modalidade(jobs: list[Job], inferidor: InferidorModalidade | None = None) -> list[Job]:
    """Preenche a modalidade que o portal nao informou. Nunca sobrescreve a do portal.

    Deve rodar ANTES da exportacao, que trunca a descricao.
    """
    inferidor = inferidor or default_inferidor()
    for job in jobs:
        if sem_modalidade(job.workplace_type):
            job.workplace_type = inferidor.inferir(job.title, job.description, job.location)
    return jobs
