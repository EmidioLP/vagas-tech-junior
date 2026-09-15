"""Fontes da coleta padrao: a ProgramaThor fica de fora, mas continua disponivel."""

from __future__ import annotations

import main as cli
from scraper.config import Settings
from scraper.execucao import escopo_completo
from scraper.sources import AVAILABLE_SOURCES, DEFAULT_SOURCES, FORA_DA_COLETA_PADRAO


def test_programathor_fora_da_coleta_padrao_mas_disponivel():
    assert "programathor" in FORA_DA_COLETA_PADRAO
    assert "programathor" not in DEFAULT_SOURCES
    assert "programathor" in AVAILABLE_SOURCES
    assert set(DEFAULT_SOURCES) | set(FORA_DA_COLETA_PADRAO) == set(AVAILABLE_SOURCES)


def test_settings_usa_as_fontes_padrao():
    """`scraper.config` repete a lista para evitar import circular; as duas precisam bater."""
    assert Settings().sources == DEFAULT_SOURCES


def test_cli_usa_as_fontes_padrao_e_aceita_as_de_fora():
    parser = cli.build_parser()
    assert parser.parse_args([]).sources == DEFAULT_SOURCES
    assert parser.parse_args(["--sources", "programathor"]).sources == ["programathor"]


def test_escopo_completo_nao_exige_fontes_fora_do_padrao():
    assert escopo_completo(Settings())
    assert escopo_completo(Settings(sources=[*DEFAULT_SOURCES, "programathor"]))
    assert not escopo_completo(Settings(sources=DEFAULT_SOURCES[:-1]))
