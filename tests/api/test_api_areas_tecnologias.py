"""GET /areas, GET /tecnologias e os endpoints de metadados."""

from __future__ import annotations

from api import vocabulary


def test_lista_todas_as_areas_do_vocabulario(client):
    """O numero de areas vem de `areas.yml`, nao de uma constante no teste:
    a taxonomia mudou uma vez (ADR 0008) e vai mudar de novo."""
    corpo = client.get("/areas").json()
    assert len(corpo) == len(vocabulary.areas())
    assert {a["area"] for a in corpo} == set(vocabulary.areas())
    # O balde-resto precisa existir: e para onde vai vaga sem area identificada.
    assert "Outros/TI Geral" in vocabulary.areas()


def test_areas_ordenadas_por_quantidade(client):
    corpo = client.get("/areas").json()
    assert corpo[0]["area"] == "Data"
    assert corpo[0]["vagas"] == 2
    assert [a["vagas"] for a in corpo] == sorted(
        (a["vagas"] for a in corpo), reverse=True
    )


def test_areas_sem_vagas_aparecem_com_zero(client):
    corpo = client.get("/areas").json()
    mobile = next(a for a in corpo if a["area"] == "Mobile")
    assert mobile["vagas"] == 0
    assert mobile["percentual"] == 0.0


def test_percentual_das_areas_soma_cem(client):
    corpo = client.get("/areas").json()
    assert round(sum(a["percentual"] for a in corpo)) == 100


def test_detalhe_de_area(client):
    corpo = client.get("/areas/Data").json()
    assert corpo["area"] == "Data"
    assert corpo["vagas"] == 2


def test_area_inexistente_da_404(client):
    resposta = client.get("/areas/Blockchain")
    assert resposta.status_code == 404
    assert "não encontrada" in resposta.json()["detail"]


def test_lista_tecnologias_com_contagem(client):
    corpo = client.get("/tecnologias").json()
    por_nome = {t["nome"]: t for t in corpo}
    assert por_nome["SQL"]["vagas"] == 2
    assert por_nome["Python"]["vagas"] == 1
    assert por_nome["React"]["vagas"] == 1


def test_tecnologias_ordenadas_por_mencoes(client):
    corpo = client.get("/tecnologias").json()
    assert [t["vagas"] for t in corpo] == sorted(
        (t["vagas"] for t in corpo), reverse=True
    )
    assert corpo[0]["nome"] == "SQL"


def test_filtro_com_vagas_omite_zerados(client):
    corpo = client.get("/tecnologias", params={"com_vagas": True}).json()
    assert {t["nome"] for t in corpo} == {"Python", "SQL", "React"}
    assert all(t["vagas"] > 0 for t in corpo)


def test_filtro_por_grupo(client):
    corpo = client.get(
        "/tecnologias", params={"grupo": "linguagens", "com_vagas": True}
    ).json()
    assert {t["nome"] for t in corpo} == {"Python", "SQL"}


def test_detalhe_de_tecnologia(client):
    corpo = client.get("/tecnologias/Python").json()
    assert corpo == {"nome": "Python", "grupo": "linguagens", "vagas": 1}


def test_tecnologia_inexistente_da_404(client):
    resposta = client.get("/tecnologias/COBOL-2000")
    assert resposta.status_code == 404
    assert "não encontrada" in resposta.json()["detail"]


def test_contagens_refletem_o_banco_e_nao_um_csv(client, seed):
    """Se o banco muda, /areas e /tecnologias mudam junto."""
    from historico_api import snapshot, vaga

    antes = next(a for a in client.get("/areas").json() if a["area"] == "Mobile")
    assert antes["vagas"] == 0

    seed.add(vaga("gupy", "4001", snapshots=[snapshot("Dev Android Jr", "Mobile")]))
    seed.commit()

    depois = next(a for a in client.get("/areas").json() if a["area"] == "Mobile")
    assert depois["vagas"] == 1


def test_areas_contam_so_vagas_ativas(client):
    """A vaga 3001 (Data) esta encerrada: Data continua com 2, como no dashboard."""
    corpo = client.get("/areas").json()
    assert sum(a["vagas"] for a in corpo) == 4
    assert next(a for a in corpo if a["area"] == "Data")["vagas"] == 2


def test_area_vem_do_snapshot_mais_recente(client, seed):
    from historico_api import COLETA_ATUAL, snapshot, vaga

    seed.add(vaga("gupy", "5001", snapshots=[
        snapshot("Dev Mobile Jr", "Mobile", collected_at=COLETA_ATUAL.replace(day=1)),
        snapshot("Dev Backend Jr", "Backend"),
    ]))
    seed.commit()

    corpo = {a["area"]: a["vagas"] for a in client.get("/areas").json()}
    assert corpo["Backend"] == 1
    assert corpo["Mobile"] == 0


def test_tecnologias_contam_so_o_estado_atual_das_ativas(client):
    """Python: so a 1001. O snapshot antigo da 2001 e a encerrada 3001 nao contam."""
    por_nome = {t["nome"]: t["vagas"] for t in client.get("/tecnologias").json()}
    assert por_nome["Python"] == 1


def test_raiz_e_health(client):
    raiz = client.get("/").json()
    assert raiz["somente_leitura"] is True
    assert raiz["docs"] == "/docs"

    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "vagas": 4}


def test_documentacao_disponivel(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/vagas" in schema["paths"]
    # Nenhum verbo de escrita no contrato publico.
    verbos = {v for caminho in schema["paths"].values() for v in caminho}
    assert verbos == {"get"}
