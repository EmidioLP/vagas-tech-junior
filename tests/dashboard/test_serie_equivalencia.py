"""A varredura por vaga devolve exatamente o que o laco por dia devolvia.

`serie_historica` deixou de visitar todas as vagas em todos os dias e passou a
visitar cada vaga so nos dias entre a estreia e o encerramento (ADR 0007). A
implementacao anterior vive em `scripts/medir_serie_historica.serie_referencia`
e e o **oraculo**: e ela que define o resultado correto, e qualquer divergencia
e regressao. O mesmo oraculo roda contra o banco de verdade pelo
`python scripts/medir_serie_historica.py --comparar`.

O cenario de `tests/cenario_historico.py` (4 vagas) fixa os numeros exatos da
serie e continua sendo a rede principal, em `test_analytics.py`. O que ele nao
cobre em quantidade e o que quebra uma varredura por janela: vaga que nasce e
fecha na mesma coleta, vaga sem snapshot no proprio dia de estreia, e troca de
area no meio do periodo. Por isso aqui o banco e o historico sintetico de
`scripts/medir_serie_historica.py`, com semente fixa.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

pytest.importorskip("sqlalchemy")

from api.models import CollectionRun, JobRecord, JobSnapshot  # noqa: E402
from dashboard import config  # noqa: E402
from dashboard.consultas import Filtros, PontoSerie, serie_historica  # noqa: E402
from scripts.medir_serie_historica import (AREAS, FONTES,  # noqa: E402
                                           gerar_historico, serie_referencia)

# Pequeno de proposito: exercita os mesmos caminhos do historico real em
# segundos. A escala nao muda o resultado, so o tempo do teste.
DIAS = 40
VAGAS_INICIAIS = 40
VAGAS_POR_COLETA = 6


@pytest.fixture(scope="module")
def leitor_sintetico(tmp_path_factory):
    """Banco migrado com o historico sintetico. Um por modulo: montar custa."""
    pytest.importorskip("alembic", reason="Alembic não instalado; teste com banco migrado pulado.")
    from alembic import command
    from alembic.config import Config

    from scraper import config as config_scraper

    caminho = tmp_path_factory.mktemp("serie") / "sintetico.db"
    cfg = Config(str(config_scraper.PROJECT_ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = f"sqlite:///{caminho.as_posix()}"
    command.upgrade(cfg, "head")
    gerar_historico(caminho, DIAS, vagas_iniciais=VAGAS_INICIAIS,
                    vagas_por_coleta=VAGAS_POR_COLETA)

    engine = config.criar_engine(caminho)
    yield engine
    engine.dispose()


@pytest.mark.parametrize("filtros", [
    pytest.param(Filtros(), id="sem-filtro"),
    pytest.param(Filtros(fontes=("gupy",)), id="uma-fonte"),
    pytest.param(Filtros(fontes=FONTES[:3]), id="varias-fontes"),
    pytest.param(Filtros(areas=("Backend",)), id="uma-area"),
    pytest.param(Filtros(areas=("Backend", "Data")), id="duas-areas"),
    pytest.param(Filtros(modalidades=("Não informado",)), id="sem-modalidade"),
    pytest.param(Filtros(modalidades=("Remoto", "Híbrido")), id="duas-modalidades"),
    pytest.param(Filtros(fontes=("linkedin",), areas=AREAS[:2], modalidades=("Remoto",)),
                 id="fonte-area-modalidade"),
    pytest.param(Filtros(inicio=date(2026, 9, 21), fim=date(2026, 10, 5)), id="periodo-no-meio"),
    pytest.param(Filtros(inicio=date(2026, 9, 15), fim=date(2026, 9, 15)), id="um-dia-so"),
    pytest.param(Filtros(areas=("Data",), inicio=date(2026, 9, 25), fim=date(2026, 10, 10)),
                 id="area-com-periodo"),
])
def test_varredura_por_vaga_bate_com_o_laco_por_dia(leitor_sintetico, filtros):
    esperado = serie_referencia(leitor_sintetico, filtros)
    assert serie_historica(leitor_sintetico, filtros) == esperado


def test_vaga_que_estreia_e_encerra_na_mesma_coleta(banco_historico):
    """`closed_at` no instante da estreia: a vaga conta como nova e nunca aberta.

    O pipeline nao produz este estado (encerrar exige duas coletas ausentes em
    dias diferentes), mas o schema permite e o laco por dia contava. A varredura
    por vaga so acerta porque visita sempre o dia de estreia, mesmo com a janela
    de "aberta" vazia.
    """
    from sqlalchemy.orm import Session

    from api.database import make_engine

    dia = date(2026, 9, 15)
    instante = datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc)
    engine_escrita = make_engine(banco_historico)
    try:
        with Session(engine_escrita) as db, db.begin():
            db.add(JobRecord(
                source="gupy", external_id="efemera", url=None,
                first_seen_at=instante, last_seen_at=instante, is_active=False,
                missing_since=instante, closed_at=instante,
                snapshots=[JobSnapshot(collected_at=instante, title="Vaga de um dia",
                                       area="Backend", workplace_type="Remoto",
                                       content_hash="efemera-0")],
            ))
            db.add(CollectionRun(
                started_at=instante, finished_at=instante, triggered_by="schedule",
                status="success", full_scope=True, jobs_count=1, failures=0, summary={},
            ))
    finally:
        engine_escrita.dispose()

    engine = config.criar_engine(banco_historico)
    try:
        assert serie_historica(engine, Filtros()) == serie_referencia(engine, Filtros())
        assert serie_historica(engine, Filtros()) == [
            PontoSerie(dia, abertas=0, novas=1, snapshots=1, abertas_por_area={}),
        ]
    finally:
        engine.dispose()


def test_snapshot_exatamente_na_virada_do_dia(banco_historico):
    """Snapshot as 00:00 de D+1 nao e o estado vigente no fim de D.

    O fim do dia e exclusivo. E a unica igualdade possivel entre um snapshot e o
    limite do dia, e o cron das 09:00 UTC nunca a produz — mas uma carga manual
    produz, e e ela que separa `<` de `<=` no avanco do ponteiro.
    """
    from sqlalchemy.orm import Session

    from api.database import make_engine

    d1, d2 = date(2026, 9, 15), date(2026, 9, 16)
    manha = datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc)
    virada = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)

    engine_escrita = make_engine(banco_historico)
    try:
        with Session(engine_escrita) as db, db.begin():
            db.add(JobRecord(
                source="gupy", external_id="virada", url=None,
                first_seen_at=manha, last_seen_at=virada, is_active=True,
                snapshots=[
                    JobSnapshot(collected_at=manha, title="Vaga", area="Backend",
                                workplace_type="Remoto", content_hash="virada-0"),
                    JobSnapshot(collected_at=virada, title="Vaga", area="Data",
                                workplace_type="Remoto", content_hash="virada-1"),
                ],
            ))
            for instante in (manha, virada):
                db.add(CollectionRun(
                    started_at=instante, finished_at=instante, triggered_by="manual",
                    status="success", full_scope=True, jobs_count=1, failures=0, summary={},
                ))
    finally:
        engine_escrita.dispose()

    engine = config.criar_engine(banco_historico)
    try:
        assert serie_historica(engine, Filtros()) == serie_referencia(engine, Filtros())
        assert serie_historica(engine, Filtros()) == [
            # Em D1 vale o snapshot das 09:05, nao o da meia-noite de D2.
            PontoSerie(d1, abertas=1, novas=1, snapshots=1, abertas_por_area={"Backend": 1}),
            PontoSerie(d2, abertas=1, novas=0, snapshots=1, abertas_por_area={"Data": 1}),
        ]
    finally:
        engine.dispose()


def test_o_cenario_sintetico_cobre_os_casos_de_borda(leitor_sintetico):
    """Sem isto, o teste acima poderia passar comparando series triviais."""
    serie = serie_historica(leitor_sintetico, Filtros())
    assert len(serie) == DIAS // 2
    assert sum(ponto.novas for ponto in serie) > VAGAS_INICIAIS
    # Vagas encerram ao longo do periodo: o total aberto sobe e depois estabiliza.
    assert max(ponto.abertas for ponto in serie) > serie[-1].abertas
    # Mais de uma area viva em cada dia, senao o filtro por area nao prova nada.
    assert max(len(ponto.abertas_por_area) for ponto in serie) > 1
