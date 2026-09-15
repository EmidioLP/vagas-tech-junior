"""Registro de portais disponiveis."""

from __future__ import annotations

from .base import JobSource
from .geekhunter import GeekHunterSource
from .gupy import GupySource
from .linkedin import LinkedInSource
from .programathor import ProgramathorSource
from .querovagastech import QueroVagasTechSource
from .trampos import TramposSource
from .vagas_com import VagasComSource

SOURCE_REGISTRY: dict[str, type[JobSource]] = {
    GupySource.name: GupySource,
    VagasComSource.name: VagasComSource,
    ProgramathorSource.name: ProgramathorSource,
    TramposSource.name: TramposSource,
    LinkedInSource.name: LinkedInSource,
    QueroVagasTechSource.name: QueroVagasTechSource,
    GeekHunterSource.name: GeekHunterSource,
}

AVAILABLE_SOURCES = list(SOURCE_REGISTRY)

# Fontes fora da coleta padrao (e do "escopo completo" da guarda de intervalo),
# com o motivo. Continuam registradas: `--sources` ainda as aceita e a API segue
# filtrando as vagas antigas delas.
FORA_DA_COLETA_PADRAO: dict[str, str] = {
    "programathor": "responde HTTP 403 para IPs de nuvem (GitHub Actions) desde 15/09/2026",
}

DEFAULT_SOURCES = [nome for nome in AVAILABLE_SOURCES if nome not in FORA_DA_COLETA_PADRAO]

__all__ = ["JobSource", "GupySource", "VagasComSource", "ProgramathorSource",
           "TramposSource", "LinkedInSource", "QueroVagasTechSource",
           "GeekHunterSource", "SOURCE_REGISTRY", "AVAILABLE_SOURCES",
           "DEFAULT_SOURCES", "FORA_DA_COLETA_PADRAO"]
