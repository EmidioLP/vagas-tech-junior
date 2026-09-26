"""Os PNGs do `--csv` (scraper/charts.py) sao gravados, inclusive sem modalidade informada."""

import pytest

pytest.importorskip("matplotlib")

from scraper.charts import chart_workplace, export_charts  # noqa: E402
from scraper.models import Job  # noqa: E402


def _jobs():
    modalidades = ["Remoto", "Remoto", "Híbrido", "Presencial", "", "", "Outra"]
    return [
        Job(source="gupy", external_id=str(i), title=f"Dev Backend Jr {i}", company="ACME",
            area="Backend" if i % 2 else "Data", seniority="Júnior", workplace_type=modalidade,
            description="Python e SQL")
        for i, modalidade in enumerate(modalidades)
    ]


def test_modalidade_grava_png_com_modalidade_vazia_e_desconhecida(tmp_path):
    caminho = chart_workplace(_jobs(), tmp_path / "modalidade.png", subtitle="teste")

    assert caminho.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_modalidade_sem_vagas_recusa():
    with pytest.raises(ValueError):
        chart_workplace([], "nao-usado.png")


def test_export_charts_grava_areas_e_modalidade(tmp_path):
    arquivos = export_charts(_jobs(), tmp_path, "teste")

    assert {"chart_areas", "chart_workplace"} <= set(arquivos)
    for caminho in arquivos.values():
        assert caminho.exists() and caminho.stat().st_size > 0
