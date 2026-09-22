"""Parser do Solides, com recortes reais da API (offline)."""

from __future__ import annotations

import pytest

from scraper.config import Settings
from scraper.dedupe import identidade_no_link
from scraper.models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO
from scraper.sources.solides import API_URL, MAX_TAKE, SITE_URL, SolidesSource

# Recorte real de
# GET https://apigw.solides.com.br/jobs/v3/portal-vacancies?take=25&page=1&title=desenvolvedor%20junior
ITEM = {
    "id": 923305,
    "title": "Analista Desenvolvedor Júnior",
    "description": "<p>Buscamos um profissional dinâmico para atuar com "
                   "<b>desenvolvimento web</b> e integrações de sistemas.</p>",
    "currentState": "em_andamento",
    "companyName": "FF BIANCHI LTDA",
    "state": {"id": 27, "name": "Distrito Federal", "code": "DF"},
    "city": {"id": 5570, "name": "Brasília", "state_id": 27},
    "slug": "saferevia",
    "redirectLink": "https://saferevia.solides.jobs/vacancies/923305?origem=portal",
    "isHiddenJob": False,
    "homeOffice": False,
    "jobType": "presencial",
    "showModality": True,
    "seniority": [{"id": 4, "name": "Junior", "level": None}],
    "createdAt": "2026-09-16",
}

# Mesma busca: id alfanumérico (5 de 40 medidas vêm assim) e, na mesma vaga,
# `showModality: false` com `jobType` preenchido.
ID_ALFANUMERICO = {
    "id": "vgV6ou5UrL",
    "title": "Desenvolvedor Junior",
    "description": "Missão do Cargo: atuar com C#/.NET e PHP/Laravel.",
    "currentState": "em_andamento",
    "companyName": "Grupo Senff",
    "state": {"name": "Paraná", "code": "PR"},
    "city": {"name": "CURITIBA", "state_id": 0},
    "slug": "senff",
    "redirectLink": "https://senff.solides.jobs/vacancies/vgV6ou5UrL?origem=portal",
    "isHiddenJob": False,
    "homeOffice": False,
    "jobType": "hibrido",
    "showModality": False,
    "seniority": [],
    "createdAt": "2026-09-02",
}


class _Sessao:
    """Substitui a PoliteSession: devolve respostas na ordem programada."""

    def __init__(self, paginas):
        self.paginas = list(paginas)
        self.urls = []
        self.request_count = 0

    def get_json(self, url, params=None, **kwargs):
        self.urls.append((url, params))
        self.request_count += 1
        return self.paginas.pop(0) if self.paginas else None


def _fonte(sessao=None, **ajustes):
    return SolidesSource(session=sessao or _Sessao([]), settings=Settings(**ajustes))


def _envelope(itens, total_pages=1):
    """O envelope da API aninha a lista dentro de `data.data`."""
    return {"success": True, "errors": [],
            "data": {"totalPages": total_pages, "currentPage": 1,
                     "count": len(itens), "data": itens}}


def _pagina_cheia(prefixo="p", total_pages=99):
    return _envelope([{**ITEM, "id": f"{prefixo}-{n}"} for n in range(MAX_TAKE)],
                     total_pages=total_pages)


def test_parse_mapeia_os_campos():
    job = _fonte()._parse(ITEM, "desenvolvedor junior")

    assert job is not None
    assert job.source == "solides"
    assert job.external_id == "923305"
    assert job.title == "Analista Desenvolvedor Júnior"
    assert job.company == "FF BIANCHI LTDA"
    assert job.url == ITEM["redirectLink"]
    assert job.location == "Brasília, DF"
    assert job.workplace_type == PRESENCIAL
    assert job.published_date == "2026-09-16"
    assert job.search_term == "desenvolvedor junior"


def test_descricao_perde_o_html():
    job = _fonte()._parse(ITEM, "x")
    assert "<b>" not in job.description
    assert "desenvolvimento web" in job.description


def test_id_alfanumerico_vira_texto():
    """O `id` vem inteiro ou alfanumérico; o banco guarda os dois como texto."""
    job = _fonte()._parse(ID_ALFANUMERICO, "x")
    assert job.external_id == "vgV6ou5UrL"


def test_senioridade_declarada_pelo_portal_e_ignorada():
    """`filter_entry_level` confia no nível da fonte e nem olha o título."""
    job = _fonte()._parse(ITEM, "x")
    assert ITEM["seniority"][0]["name"] == "Junior", "o recorte real declara nível"
    assert job.seniority == ""


@pytest.mark.parametrize(
    "campos,esperado",
    [
        ({"jobType": "presencial"}, PRESENCIAL),
        ({"jobType": "hibrido"}, HIBRIDO),
        ({"jobType": "remoto"}, REMOTO),
        # `homeOffice` é reserva: só decide quando `jobType` não vem.
        ({"jobType": "", "homeOffice": True}, REMOTO),
        ({"jobType": None, "homeOffice": False}, NAO_INFORMADO),
        ({}, NAO_INFORMADO),
    ],
)
def test_modalidade(campos, esperado):
    assert SolidesSource._modalidade(campos) == esperado


def test_show_modality_falso_nao_apaga_a_modalidade():
    """O campo controla a exibição no portal, não a validade do dado."""
    job = _fonte()._parse(ID_ALFANUMERICO, "x")
    assert ID_ALFANUMERICO["showModality"] is False
    assert job.workplace_type == HIBRIDO


def test_vaga_que_nao_esta_aberta_e_descartada():
    assert _fonte()._parse({**ITEM, "currentState": "encerrada"}, "x") is None


def test_registro_incompleto_vira_none():
    fonte = _fonte()
    assert fonte._parse({**ITEM, "id": None}, "x") is None
    assert fonte._parse({**ITEM, "title": ""}, "x") is None


def test_local_com_campos_faltando():
    assert SolidesSource._local({"city": {"name": "CURITIBA"}, "state": {}}) == "CURITIBA"
    assert SolidesSource._local({"city": {}, "state": {"code": "PR"}}) == "PR"
    assert SolidesSource._local({}) == ""


def test_url_tem_reserva_quando_o_portal_nao_manda_link():
    job = _fonte()._parse({**ITEM, "redirectLink": ""}, "x")
    assert job.url == f"{SITE_URL}/vaga/923305"


def test_take_respeita_o_teto_da_api():
    """`page_size` padrão é 100, mas acima de 25 a API responde HTTP 400."""
    sessao = _Sessao([_envelope([ITEM])])
    _fonte(sessao).fetch_term("desenvolvedor junior")

    url, params = sessao.urls[0]
    assert url == API_URL
    assert params == {"title": "desenvolvedor junior", "page": 1, "take": MAX_TAKE}


def test_pagina_vazia_encerra_a_paginacao():
    sessao = _Sessao([_envelope([])])
    assert _fonte(sessao).fetch_term("x") == []
    assert len(sessao.urls) == 1


def test_paginacao_para_na_ultima_pagina_parcial():
    resto = _envelope([{**ITEM, "id": 900 + n} for n in range(3)], total_pages=2)
    sessao = _Sessao([_pagina_cheia(total_pages=2), resto])
    jobs = _fonte(sessao).fetch_term("x")

    assert len(jobs) == MAX_TAKE + 3
    assert len(sessao.urls) == 2, "não deve pedir uma terceira página"


def test_paginacao_respeita_total_pages_mesmo_com_pagina_cheia():
    """Página cheia + última página alcançada = fim; sem isso giraria à toa."""
    cheia = _pagina_cheia(total_pages=1)
    sessao = _Sessao([cheia, cheia])
    _fonte(sessao).fetch_term("x")
    assert len(sessao.urls) == 1


def test_paginacao_respeita_max_pages_per_term():
    sessao = _Sessao([_pagina_cheia(prefixo=f"p{p}") for p in range(5)])
    _fonte(sessao, max_pages_per_term=2).fetch_term("x")

    assert [params["page"] for _, params in sessao.urls] == [1, 2]


def test_pagina_repetida_nao_gera_loop():
    cheia = _pagina_cheia()
    sessao = _Sessao([cheia, cheia, cheia])
    jobs = _fonte(sessao).fetch_term("x")

    assert len(jobs) == MAX_TAKE
    assert len(sessao.urls) == 2, "para assim que uma página não traz nada novo"


def test_dedupe_le_o_id_do_link_numerico():
    """O subdomínio muda por empresa, mas o domínio que identifica o portal não."""
    assert identidade_no_link(ITEM["redirectLink"]) == "solides.jobs:923305"


def test_dedupe_nao_inventa_id_para_link_alfanumerico():
    """Sem id reconhecível o link não vale como prova; sobra título + empresa."""
    assert identidade_no_link(ID_ALFANUMERICO["redirectLink"]) == ""
