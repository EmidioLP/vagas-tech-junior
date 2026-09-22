"""Reclassificacao do historico depois de uma mudanca em `areas.yml` ou `modalidade.yml`.

Duas propriedades importam, e as duas sao faceis de quebrar sem perceber:

1. **A assinatura tem que ser reproduzivel.** O script recalcula o
   `content_hash` de cada snapshot. Se ele montar os campos de um jeito
   diferente do que `persistence/assinatura.py` monta, gravaria hash errado e
   toda coleta seguinte veria mudanca onde nao houve. Por isso ele confere
   primeiro que consegue reproduzir o hash **ja gravado**, e aborta se nao
   conseguir.
2. **Depois de reclassificar, a coleta seguinte nao grava snapshot novo.** E o
   ponto inteiro de recalcular o hash: area nova no snapshot e no hash, entao a
   proxima assinatura bate e nada e gravado.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session, selectinload  # noqa: E402

from api.database import make_engine  # noqa: E402
from api.models import JobRecord, JobSnapshot  # noqa: E402
from persistence.repositorio import persistir_vagas  # noqa: E402
from scraper.models import Job  # noqa: E402
from scripts.reclassificar_areas import (conferir_assinaturas, montar_plano,  # noqa: E402
                                         main)

COLETA = datetime.combine(date(2026, 9, 15), time(9, 5), tzinfo=timezone.utc)


class _ClassificadorFixo:
    """Classificador de mentira: manda tudo para uma area so."""

    def __init__(self, area: str, score: float = 12.0):
        self.area, self.score = area, score

    def classify(self, title, description=""):
        from scraper.classifier import AreaScore

        return AreaScore(self.area, self.score, ["keyword(t)"], self.score)


def _vaga(titulo="Analista de Suporte Jr", area="Área Antiga"):
    # Descricao com mais de uma keyword: com uma so, o separador da evidencia
    # nao aparece e um formato diferente do da coleta passaria despercebido.
    return Job(source="gupy", external_id="1", title=titulo, company="Acme",
               description="Atendimento a chamados de usuarios, suporte tecnico "
                           "e help desk.", area=area,
               area_score=12.0, area_matches="suporte(t)")


@pytest.fixture
def banco(banco_historico):
    engine = make_engine(banco_historico)
    persistir_vagas([_vaga()], engine, COLETA)
    yield engine
    engine.dispose()


def _snapshots(engine):
    with Session(engine) as db:
        return db.scalars(
            select(JobSnapshot).options(selectinload(JobSnapshot.tecnologias))
        ).all()


def test_a_assinatura_gravada_e_reproduzivel(banco):
    """Se isto falhar, o script monta os campos diferente da persistencia."""
    assert conferir_assinaturas(_snapshots(banco)) == []


def test_hash_adulterado_e_detectado(banco):
    """A conferencia existe para abortar, nao para enfeitar o relatorio."""
    with Session(banco) as db:
        snapshot = db.scalars(select(JobSnapshot)).one()
        snapshot.content_hash = "0" * 64
        db.commit()
    assert len(conferir_assinaturas(_snapshots(banco))) == 1


def test_plano_nao_grava_nada(banco):
    antes = [(s.area, s.content_hash) for s in _snapshots(banco)]
    montar_plano(_snapshots(banco), _ClassificadorFixo("Suporte Técnico"))
    assert [(s.area, s.content_hash) for s in _snapshots(banco)] == antes


def test_plano_aponta_a_area_que_saiu_do_vocabulario(banco):
    plano, _ = montar_plano(_snapshots(banco), _ClassificadorFixo("Suporte Técnico"))
    # "Área Antiga" nao esta em areas.yml: e o que dispara alerta alto de
    # qualidade enquanto o historico nao for reclassificado.
    assert plano.fora_do_vocabulario == {"Área Antiga": 1}
    assert plano.mudam == 1
    assert plano.vagas_depois == {"Suporte Técnico": 1}


def _como_o_pipeline_classificaria(vaga):
    """A coleta roda `classify_jobs`: area, score e evidencia saem dele.

    Tem de ser a funcao da coleta, nao uma copia: os tres campos entram na
    assinatura, e uma copia com outro formato de evidencia (o script ja usou
    "; " enquanto a coleta usa ", ") esconde exatamente o bug que este teste
    existe para pegar.
    """
    from scraper.classifier import classify_jobs

    return classify_jobs([vaga])[0]


def test_depois_de_reclassificar_a_coleta_seguinte_nao_grava_snapshot(banco_historico):
    """A propriedade que justifica recalcular o hash.

    Com a area velha gravada, a coleta seguinte ve assinatura diferente e grava
    um snapshot para uma mudanca que nunca houve. Depois da reclassificacao,
    nao grava nada.
    """
    mais_tarde = COLETA.replace(hour=18)
    engine = make_engine(banco_historico)
    try:
        persistir_vagas([_vaga()], engine, COLETA)   # area velha, como as coletas antigas
        sem = persistir_vagas([_como_o_pipeline_classificaria(_vaga())], engine, mais_tarde)
        assert sem.snapshots_criados == 1
    finally:
        engine.dispose()

    # Mesmo cenario, agora reclassificando antes da coleta seguinte.
    engine = make_engine(banco_historico)
    try:
        with Session(engine) as db:
            for s in db.scalars(select(JobSnapshot)):
                db.delete(s)
            for j in db.scalars(select(JobRecord)):
                db.delete(j)
            db.commit()
        persistir_vagas([_vaga()], engine, COLETA)
    finally:
        engine.dispose()

    assert main(["--db", str(banco_historico), "--aplicar"]) == 0

    engine = make_engine(banco_historico)
    try:
        com = persistir_vagas([_como_o_pipeline_classificaria(_vaga())], engine, mais_tarde)
        assert com.snapshots_criados == 0
        assert com.snapshots_ignorados == 1
    finally:
        engine.dispose()


def test_o_script_recusa_gravar_com_assinatura_divergente(banco_historico, capsys):
    engine = make_engine(banco_historico)
    try:
        persistir_vagas([_vaga()], engine, COLETA)
        with Session(engine) as db:
            db.scalars(select(JobSnapshot)).one().content_hash = "0" * 64
            db.commit()
    finally:
        engine.dispose()

    assert main(["--db", str(banco_historico)]) == 3
    assert "nao se reproduz" in capsys.readouterr().err


def _plano_modalidade(banco_historico, **campos):
    engine = make_engine(banco_historico)
    try:
        persistir_vagas([Job(source="linkedin", external_id="9", title="Dev Jr",
                             company="Acme", **campos)], engine, COLETA)
        snapshots = _snapshots(engine)
    finally:
        engine.dispose()
    return montar_plano(snapshots, _ClassificadorFixo("Suporte Técnico"))


def test_modalidade_ausente_e_inferida(banco_historico):
    plano, alteracoes = _plano_modalidade(
        banco_historico, description="Modelo de trabalho 100% remoto.",
        workplace_type="Não informado")
    (alteracao,) = alteracoes
    assert alteracao.workplace_type == "Remoto"
    assert plano.modalidade_antes == {"Não informado": 1}
    assert plano.modalidade_depois == {"Remoto": 1}


def test_modalidade_informada_nunca_muda(banco_historico):
    plano, alteracoes = _plano_modalidade(
        banco_historico, description="Modelo de trabalho 100% remoto.",
        workplace_type="Presencial")
    assert [a.workplace_type for a in alteracoes] == ["Presencial"]
    assert plano.modalidade_depois == {"Presencial": 1}


def test_aplicar_grava_a_modalidade_com_assinatura_reproduzivel(banco_historico):
    engine = make_engine(banco_historico)
    try:
        persistir_vagas([Job(source="vagas", external_id="7", title="Dev Jr (Híbrido)",
                             company="Acme", workplace_type="Não informado")],
                        engine, COLETA)
    finally:
        engine.dispose()
    assert main(["--db", str(banco_historico), "--aplicar"]) == 0
    engine = make_engine(banco_historico)
    try:
        (snapshot,) = _snapshots(engine)
        assert snapshot.workplace_type == "Híbrido"
        assert conferir_assinaturas([snapshot]) == []
    finally:
        engine.dispose()
