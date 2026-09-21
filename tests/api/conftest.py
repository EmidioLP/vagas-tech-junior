"""Fixtures da API: banco SQLite em memoria, sem rede e sem tocar no banco real.

Os testes da API ficam num diretorio proprio para que quem so usa o scraper
possa rodar `pytest tests/` sem ter FastAPI instalado -- o importorskip abaixo
pula esta pasta inteira nesse caso.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi", reason="FastAPI não instalado; testes da API pulados.")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from api.app import app  # noqa: E402
from api.database import Base, get_db  # noqa: E402
from api.models import Tecnologia  # noqa: E402
from historico_api import COLETA_ANTIGA, snapshot, vaga  # noqa: E402

@pytest.fixture
def db_session():
    """SQLite em memoria. StaticPool mantem a mesma conexao entre as sessoes."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def seed(db_session):
    """Um historico pequeno e previsivel, no formato que o pipeline grava.

    Quatro vagas ativas, mais:
      - 2001 tem um snapshot antigo que citava Python; o vigente so cita React;
      - 3001 esta encerrada (area Data), e nao conta por padrao.
    """
    python = Tecnologia(nome="Python", grupo="linguagens")
    sql = Tecnologia(nome="SQL", grupo="linguagens")
    react = Tecnologia(nome="React", grupo="frameworks")
    db_session.add_all([python, sql, react])

    db_session.add_all([
        vaga("gupy", "1001", snapshots=[snapshot(
            "Engenheiro de Dados Júnior", "Data", company="ACME",
            seniority="Júnior", location="São Paulo, São Paulo",
            workplace_type="Remoto", published_date=date(2026, 7, 20),
            description="Vaga de dados.",
            area_score=12.0, area_matches="engenheiro de dados(t)",
            tecnologias=[python, sql],
        )]),
        vaga("gupy", "1002", snapshots=[snapshot(
            "Analista de Dados Júnior", "Data", company="Globex",
            seniority="Júnior", location="Belo Horizonte, Minas Gerais",
            workplace_type="Híbrido", published_date=date(2026, 7, 10),
            description="BI e relatórios.", tecnologias=[sql],
        )]),
        vaga("vagas", "2001", snapshots=[
            snapshot("Desenvolvedor Front-End Jr", "Frontend", collected_at=COLETA_ANTIGA,
                     company="Initech", workplace_type="Remoto",
                     published_date=date(2026, 7, 25), tecnologias=[python]),
            snapshot("Desenvolvedor Front-End Jr", "Frontend", company="Initech",
                     seniority="Júnior", location="100% Home Office",
                     workplace_type="Remoto", published_date=date(2026, 7, 25),
                     description="React e CSS.", tecnologias=[react]),
        ]),
        vaga("vagas", "2002", snapshots=[snapshot(
            "Estágio em Suporte Técnico", "Suporte Técnico", company="Umbrella",
            seniority="Estágio", location="Curitiba / PR",
            workplace_type="Não informado", published_date=None,
            description="Atendimento e chamados.",
        )]),
        vaga("gupy", "3001", ativa=False, snapshots=[snapshot(
            "Cientista de Dados Júnior", "Data", collected_at=COLETA_ANTIGA,
            company="Hooli", workplace_type="Remoto",
            published_date=date(2026, 7, 30), tecnologias=[python],
        )]),
    ])
    db_session.commit()
    return db_session


@pytest.fixture
def client(seed, monkeypatch):
    """TestClient com o banco de teste injetado no lugar do banco real.

    O lifespan chama `init_db`, que exige DATABASE_URL; aqui as tabelas ja
    existem no banco em memoria do `seed`.
    """
    monkeypatch.setattr("api.app.init_db", lambda: None)
    app.dependency_overrides[get_db] = lambda: seed
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
