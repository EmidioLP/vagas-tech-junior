"""API e dashboard contam as mesmas vagas no mesmo banco.

Usa o cenario de historico conhecido (tests/cenario_historico.py) sobre o schema
das migrations: a API pelo HTTP, o dashboard pelas funcoes de `dashboard/consultas.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import app
from api.database import get_db, make_engine
from cenario_historico import popular
from dashboard.consultas import (
    Filtros,
    distribuicao,
    indicadores_atuais,
    top_tecnologias,
    vagas_ativas,
)


@pytest.fixture
def cenario(banco_historico, monkeypatch):
    popular(banco_historico)
    engine = make_engine(banco_historico)

    def sessao():
        with Session(engine) as db:
            yield db

    monkeypatch.setattr("api.app.init_db", lambda: None)
    app.dependency_overrides[get_db] = sessao
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_total_de_areas_igual_as_vagas_ativas_do_dashboard(cenario):
    client, engine = cenario
    areas = client.get("/areas").json()
    assert sum(a["vagas"] for a in areas) == vagas_ativas(engine) == 3


def test_cada_area_igual_a_distribuicao_do_dashboard(cenario):
    client, engine = cenario
    api = {a["area"]: a["vagas"] for a in client.get("/areas").json() if a["vagas"]}
    dashboard = {c.rotulo: c.vagas for c in distribuicao(engine, Filtros(), "area")}
    # A vaga A mudou de Backend para Data: conta em Data, pelo estado atual.
    assert api == dashboard == {"Data": 1, "Suporte/Infra": 1, "Frontend": 1}


@pytest.mark.parametrize("area, modalidade", [
    ("Data", "Remoto"),
    ("Suporte/Infra", "Não informado"),
    ("Data", "Presencial"),  # so a vaga B, que esta encerrada
])
def test_filtro_de_vagas_igual_aos_indicadores_do_dashboard(cenario, area, modalidade):
    client, engine = cenario
    corpo = client.get("/vagas", params={"area": area, "modalidade": modalidade}).json()
    filtros = Filtros(areas=(area,), modalidades=(modalidade,))
    assert corpo["total"] == indicadores_atuais(engine, filtros).vagas_ativas


def test_tecnologias_iguais_ao_ranking_do_dashboard(cenario):
    client, engine = cenario
    api = {t["nome"]: t["vagas"]
           for t in client.get("/tecnologias", params={"com_vagas": True}).json()}
    ranking = top_tecnologias(engine, Filtros(), limite=1000)
    # Java so aparece no snapshot antigo de A e na vaga encerrada B.
    assert api == {c.rotulo: c.vagas for c in ranking.itens} == {"SQL": 2, "Python": 1}
