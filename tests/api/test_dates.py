"""Normalizacao das datas de publicacao (`api/dates.py`)."""

from __future__ import annotations

from datetime import date

import pytest

from api.dates import parse_published_date

REFERENCIA = date(2026, 7, 31)


@pytest.mark.parametrize(
    "bruto,esperado",
    [
        ("2026-06-26", date(2026, 6, 26)),          # ISO, da Gupy
        ("09/07/2026", date(2026, 7, 9)),           # dd/mm/aaaa, do Vagas.com
        ("Hoje", REFERENCIA),
        ("Ontem", date(2026, 7, 30)),
        ("Anteontem", date(2026, 7, 29)),
        ("Há 3 dias", date(2026, 7, 28)),
        ("há 1 dia", date(2026, 7, 30)),
        ("Há mais de 30 dias", date(2026, 7, 1)),
        ("Há 2 meses", date(2026, 6, 1)),
        ("", None),
        (None, None),
        ("qualquer coisa", None),
        ("32/13/2026", None),                       # data impossivel
    ],
)
def test_parse_published_date(bruto, esperado):
    assert parse_published_date(bruto, REFERENCIA) == esperado


def test_datas_relativas_usam_a_referencia_e_nao_hoje():
    """Uma coleta antiga tem que reproduzir as datas da época em que foi feita."""
    antiga = date(2020, 1, 10)
    assert parse_published_date("Ontem", antiga) == date(2020, 1, 9)
