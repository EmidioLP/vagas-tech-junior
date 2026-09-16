"""Fixtures dos testes do dashboard."""

from __future__ import annotations

import pytest

from cenario_historico import popular


@pytest.fixture
def banco_com_historico(banco_historico):
    """`banco_historico` com o cenario descrito em cenario_historico.py."""
    pytest.importorskip("sqlalchemy")
    popular(banco_historico)
    return banco_historico
