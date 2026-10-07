"""GET /modalidades, GET /tecnologias/por-area e GET /execucoes."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from api import vocabulary
from api.models import CollectionRun
from historico_api import snapshot, vaga


# --- /modalidades ---------------------------------------------------------------


def test_modalidades_na_ordem_do_vocabulario_com_zeros(client):
    corpo = client.get("/modalidades").json()
    assert [m["modalidade"] for m in corpo] == vocabulary.workplace_types()
    assert {m["modalidade"]: m["vagas"] for m in corpo} == {
        "Remoto": 2, "Híbrido": 1, "Presencial": 0, "Não informado": 1,
    }


def test_modalidades_contam_so_vagas_ativas_e_somam_cem(client):
    """A 3001 (Remoto) esta encerrada: o total e 4, como em /areas."""
    corpo = client.get("/modalidades").json()
    assert sum(m["vagas"] for m in corpo) == 4
    assert {m["modalidade"]: m["percentual"] for m in corpo} == {
        "Remoto": 50.0, "Híbrido": 25.0, "Presencial": 0.0, "Não informado": 25.0,
    }


def test_modalidades_por_fonte_recortam_a_base(client):
    corpo = client.get("/modalidades", params={"fonte": "vagas"}).json()
    assert {m["modalidade"]: (m["vagas"], m["percentual"]) for m in corpo} == {
        "Remoto": (1, 50.0), "Híbrido": (0, 0.0),
        "Presencial": (0, 0.0), "Não informado": (1, 50.0),
    }


def test_modalidades_por_area_e_fonte_combinam(client):
    corpo = client.get("/modalidades", params={"area": "Data", "fonte": "gupy"}).json()
    assert {m["modalidade"]: m["vagas"] for m in corpo if m["vagas"]} == {
        "Remoto": 1, "Híbrido": 1,
    }


def test_modalidades_sem_vagas_no_recorte_nao_dividem_por_zero(client):
    corpo = client.get("/modalidades", params={"area": "Mobile"}).json()
    assert all(m["vagas"] == 0 and m["percentual"] == 0.0 for m in corpo)


def test_modalidade_vem_do_snapshot_mais_recente(client, seed):
    from historico_api import COLETA_ANTIGA

    seed.add(vaga("gupy", "6001", snapshots=[
        snapshot("Dev Jr", "Backend", collected_at=COLETA_ANTIGA, workplace_type="Remoto"),
        snapshot("Dev Jr", "Backend", workplace_type="Presencial"),
    ]))
    seed.commit()

    corpo = {m["modalidade"]: m["vagas"] for m in client.get("/modalidades").json()}
    assert (corpo["Remoto"], corpo["Presencial"]) == (2, 1)


@pytest.mark.parametrize("parametros", [{"area": "Inexistente"}, {"fonte": "portal-inexistente"}])
def test_modalidades_com_filtro_invalido_dao_422(client, parametros):
    assert client.get("/modalidades", params=parametros).status_code == 422


# --- /tecnologias/por-area ------------------------------------------------------


def test_tecnologias_por_area_com_base_propria(client):
    corpo = client.get("/tecnologias/por-area").json()
    # Maior base primeiro; Suporte Tecnico tem vaga ativa mas nenhuma cita tecnologia.
    assert [a["area"] for a in corpo] == ["Data", "Frontend", "Suporte Técnico"]
    assert corpo[0] == {
        "area": "Data", "vagas_ativas": 2, "base": 2,
        "tecnologias": [
            {"nome": "SQL", "grupo": "linguagens", "vagas": 2, "percentual": 100.0},
            {"nome": "Python", "grupo": "linguagens", "vagas": 1, "percentual": 50.0},
        ],
    }
    assert corpo[2] == {"area": "Suporte Técnico", "vagas_ativas": 1, "base": 0,
                        "tecnologias": []}


def test_tecnologias_por_area_so_contam_o_estado_atual_das_ativas(client):
    """O snapshot antigo da 2001 citava Python; o vigente so cita React."""
    corpo = client.get("/tecnologias/por-area", params={"area": "Frontend"}).json()
    assert len(corpo) == 1
    assert [t["nome"] for t in corpo[0]["tecnologias"]] == ["React"]


def test_tecnologias_por_area_respeitam_o_limite(client):
    corpo = client.get("/tecnologias/por-area", params={"area": "Data", "limit": 1}).json()
    assert [t["nome"] for t in corpo[0]["tecnologias"]] == ["SQL"]
    # A base nao muda com o limite: e o denominador, nao o tamanho da lista.
    assert corpo[0]["base"] == 2


def test_tecnologias_por_area_sem_vaga_ativa_volta_vazio(client):
    assert client.get("/tecnologias/por-area", params={"area": "Mobile"}).json() == []


def test_tecnologias_por_area_com_parametro_invalido_dao_422(client):
    assert client.get("/tecnologias/por-area", params={"area": "Inexistente"}).status_code == 422
    assert client.get("/tecnologias/por-area", params={"limit": 0}).status_code == 422


def test_por_area_nao_e_lido_como_nome_de_tecnologia(client):
    """A rota fixa vem antes de `/tecnologias/{nome}`, que continua funcionando."""
    assert isinstance(client.get("/tecnologias/por-area").json(), list)
    assert client.get("/tecnologias/Python").json()["nome"] == "Python"


# --- /execucoes -----------------------------------------------------------------


def _momento(dia: int) -> datetime:
    return datetime(2026, 9, dia, 9, 5, tzinfo=timezone.utc)


@pytest.fixture
def execucoes(seed):
    """Tres execucoes: completa com alerta, pulada pela guarda e manual que falhou."""
    seed.add_all([
        CollectionRun(
            started_at=_momento(12), finished_at=_momento(12).replace(minute=40),
            triggered_by="schedule", status="partial", full_scope=True, interval_days=1,
            reason="alertas de qualidade: queda_brusca", next_run_on=date(2026, 9, 13),
            jobs_count=120, failures=2,
            summary={
                "fontes": {
                    "vagas": {"status": "partial", "requests": 9, "requests_falhos": 0,
                              "vagas_brutas": 40, "erros": 0, "criadas": 3},
                    "gupy": {"status": "ok", "requests": 12, "requests_falhos": 1,
                             "vagas_brutas": 300},
                },
                "vagas": 120,
                "qualidade": [{"regra": "queda_brusca", "severidade": "alta", "fonte": "vagas",
                               "valor": 40, "limite": 90,
                               "mensagem": "texto livre que nao deve sair"}],
                "github_run_id": "123456",
            },
        ),
        CollectionRun(
            started_at=_momento(13), finished_at=_momento(13),
            triggered_by="schedule", status="skipped", full_scope=True, interval_days=1,
            reason="intervalo ainda não passou", next_run_on=date(2026, 9, 14),
            jobs_count=0, failures=0, summary={},
        ),
        CollectionRun(
            started_at=_momento(14), finished_at=_momento(14),
            triggered_by="manual", status="failed", full_scope=False,
            reason="todas as fontes falharam", jobs_count=0, failures=0,
            summary={"fontes": {"gupy": {"status": "failed"}}, "vagas": 0, "qualidade": []},
        ),
    ])
    seed.commit()
    return seed


def test_execucoes_da_mais_recente_para_a_mais_antiga(client, execucoes):
    corpo = client.get("/execucoes").json()
    assert (corpo["total"], corpo["limit"], corpo["offset"]) == (3, 30, 0)
    assert [e["status"] for e in corpo["items"]] == ["failed", "skipped", "partial"]


def test_execucao_traz_contagens_por_fonte_e_alertas(client, execucoes):
    completa = client.get("/execucoes", params={"status": "partial"}).json()["items"][0]
    assert completa["iniciada_em"] == "2026-09-12T09:05:00Z"
    assert completa["finalizada_em"] == "2026-09-12T09:40:00Z"
    assert (completa["gatilho"], completa["escopo_completo"], completa["intervalo_dias"]) == (
        "schedule", True, 1)
    assert (completa["vagas"], completa["falhas"]) == (120, 2)
    assert completa["motivo"] == "alertas de qualidade: queda_brusca"
    assert completa["proxima_coleta"] == "2026-09-13"
    assert completa["fontes"] == [
        {"fonte": "gupy", "status": "ok", "requests": 12, "requests_falhos": 1,
         "vagas_brutas": 300},
        {"fonte": "vagas", "status": "partial", "requests": 9, "requests_falhos": 0,
         "vagas_brutas": 40},
    ]
    assert completa["alertas_qualidade"] == [
        {"regra": "queda_brusca", "severidade": "alta", "fonte": "vagas"}]


def test_execucao_nao_repassa_o_sumario_livre(client, execucoes):
    """O `summary` e JSON livre: so saem as chaves listadas em `crud._CAMPOS_DA_FONTE`."""
    texto = client.get("/execucoes").text
    assert "texto livre" not in texto
    assert "github_run_id" not in texto
    assert "summary" not in texto


def test_execucao_pulada_e_sem_sumario(client, execucoes):
    pulada = client.get("/execucoes", params={"status": "skipped"}).json()["items"][0]
    assert (pulada["fontes"], pulada["alertas_qualidade"], pulada["vagas"]) == ([], [], 0)
    assert pulada["motivo"] == "intervalo ainda não passou"


def test_execucoes_filtram_por_gatilho_e_status(client, execucoes):
    manual = client.get("/execucoes", params={"gatilho": "manual"}).json()
    assert (manual["total"], manual["items"][0]["status"]) == (1, "failed")
    assert manual["items"][0]["escopo_completo"] is False
    nenhuma = client.get("/execucoes", params={"gatilho": "manual", "status": "success"}).json()
    assert (nenhuma["total"], nenhuma["items"]) == (0, [])


def test_execucoes_paginam(client, execucoes):
    corpo = client.get("/execucoes", params={"limit": 1, "offset": 1}).json()
    assert corpo["total"] == 3
    assert [e["status"] for e in corpo["items"]] == ["skipped"]


def test_execucoes_sem_registro_voltam_vazias(client):
    assert client.get("/execucoes").json() == {"total": 0, "limit": 30, "offset": 0, "items": []}


def test_execucao_por_id(client, execucoes):
    alvo = client.get("/execucoes", params={"status": "skipped"}).json()["items"][0]
    assert client.get(f"/execucoes/{alvo['id']}").json() == alvo


def test_execucao_inexistente_da_404(client, execucoes):
    resposta = client.get("/execucoes/99999")
    assert resposta.status_code == 404
    assert "não encontrada" in resposta.json()["detail"]


@pytest.mark.parametrize("parametros", [
    {"status": "ok"}, {"gatilho": "cron"}, {"limit": 0}, {"limit": 500}, {"offset": -1},
])
def test_execucoes_com_parametro_invalido_dao_422(client, parametros):
    assert client.get("/execucoes", params=parametros).status_code == 422


def test_execucoes_nao_expoem_escrita(client):
    assert client.post("/execucoes", json={}).status_code == 405
    assert client.delete("/execucoes/1").status_code == 405
