"""Assinatura do snapshot: deterministica e sensivel so ao estado gravado."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from persistence.assinatura import assinatura_snapshot

BASE = {
    "title": "Desenvolvedor Python Júnior",
    "company": "ACME",
    "description": "APIs com Python e SQL.",
    "location": "São Paulo, São Paulo",
    "workplace_type": "Remoto",
    "published_date": date(2026, 8, 30),
    "seniority": "Júnior",
    "area": "Backend",
    "area_score": 12.0,
    "area_matches": "python(t)",
    "tecnologias": ["Python", "SQL"],
}


def _com(**mudancas) -> str:
    return assinatura_snapshot({**BASE, **mudancas})


def test_mesmo_estado_gera_a_mesma_assinatura():
    assinatura = assinatura_snapshot(BASE)
    assert assinatura == assinatura_snapshot(dict(BASE))
    assert len(assinatura) == 64
    assert set(assinatura) <= set("0123456789abcdef")


def test_formato_v1_fixado():
    """Mudar campos ou normalizacao sem subir VERSAO geraria snapshots novos para todas as vagas."""
    assert assinatura_snapshot(BASE) == ASSINATURA_V1_BASE


def test_ordem_e_repeticao_das_tecnologias_nao_importam():
    assert _com(tecnologias=["SQL", "Python", "SQL"]) == assinatura_snapshot(BASE)


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_vazio_e_none_sao_o_mesmo_estado(vazio):
    sem_empresa = {k: v for k, v in BASE.items() if k != "company"}
    assert _com(company=vazio) == assinatura_snapshot(sem_empresa)


def test_bordas_de_texto_nao_mudam_a_assinatura():
    assert _com(title="  Desenvolvedor Python Júnior ") == assinatura_snapshot(BASE)


def test_data_em_texto_iso_equivale_a_date():
    assert _com(published_date="2026-08-30") == assinatura_snapshot(BASE)


def test_ruido_de_ponto_flutuante_no_score_e_ignorado():
    assert _com(area_score=12.000000001) == assinatura_snapshot(BASE)


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("title", "Desenvolvedor Python Jr"),
        ("company", "Globex"),
        ("description", "APIs com Python, SQL e Docker."),
        ("location", "Recife, Pernambuco"),
        ("workplace_type", "Híbrido"),
        ("published_date", date(2026, 8, 31)),
        ("seniority", "Estágio"),
        ("area", "Data"),
        ("area_score", 8.0),
        ("area_matches", "python(t), sql(d)"),
        ("tecnologias", ["Python"]),
    ],
)
def test_cada_campo_gravado_muda_a_assinatura(campo, valor):
    assert _com(**{campo: valor}) != assinatura_snapshot(BASE)


def test_campos_fora_do_snapshot_nao_entram():
    assert _com(
        url="https://exemplo.test/outra",
        search_term="desenvolvedor jr",
        collected_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    ) == assinatura_snapshot(BASE)


ASSINATURA_V1_BASE = "83a461e4b995b66919975d20b95bfe68b090db573f9dde85040bb68096f70874"
