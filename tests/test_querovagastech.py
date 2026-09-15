"""Parser do Quero Vagas Tech, com recortes reais da API (offline)."""

from __future__ import annotations

import pytest

from scraper.config import Settings
from scraper.models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO
from scraper.sources.querovagastech import (
    MAX_PAGINAS,
    PAGE_SIZE,
    SITE_URL,
    QueroVagasTechSource,
)

# Recorte real de GET /api/jobs?page=1&pageSize=100&sort=postedAt:desc
ITEM = {
    "id": "5600783b-9e07-4006-928d-9569ac96b41b",
    "title": "Desenvolvedor Back-End Júnior",
    "company": "Magalu Cloud",
    "location": "São Paulo, São Paulo, BR",
    "workMode": "Remote",
    "seniority": "Mid",
    "employmentType": "CLT",
    "applyUrl": "https://exemplo.inhire.app/vagas/53e6/desenvolvedor",
    "sourceName": "Manual",
    "postedAt": "2026-09-11T20:12:28.0375219+00:00",
}

# Caso medido no portal: o classificador dele chama gerente de "Intern".
GERENTE_COMO_INTERN = {
    **ITEM,
    "id": "outro-id",
    "title": "Gerente de Infraestrutura de TI - LATAM (São Paulo)",
    "seniority": "Intern",
}


class _Sessao:
    """Substitui a PoliteSession: devolve respostas na ordem programada."""

    def __init__(self, paginas, detalhes=None):
        self.paginas = list(paginas)
        self.detalhes = detalhes or {}
        self.urls = []
        self.request_count = 0

    def get_json(self, url, params=None, **kwargs):
        self.urls.append((url, params))
        self.request_count += 1
        if params is not None:
            return self.paginas.pop(0) if self.paginas else None
        return self.detalhes.get(url.rsplit("/", 1)[-1])


def _fonte(sessao, **ajustes):
    return QueroVagasTechSource(session=sessao, settings=Settings(**ajustes))


def _envelope(itens, total=None, **extra):
    return {"items": itens, "page": 1, "pageSize": PAGE_SIZE,
            "total": total if total is not None else len(itens), **extra}


def test_parse_mapeia_os_campos():
    job = _fonte(_Sessao([]))._parse(ITEM)

    assert job is not None
    assert job.source == "querovagastech"
    assert job.external_id == "5600783b-9e07-4006-928d-9569ac96b41b"
    assert job.title == "Desenvolvedor Back-End Júnior"
    assert job.company == "Magalu Cloud"
    assert job.url == ITEM["applyUrl"]
    assert job.location == "São Paulo, São Paulo, BR"
    assert job.workplace_type == REMOTO
    assert job.published_date == "2026-09-11"


def test_senioridade_do_portal_nao_e_aproveitada():
    """Decisivo: `filter_entry_level` confia em nível declarado e ignora o
    título. Se este campo entrasse, "Gerente de TI" passaria como Intern."""
    job = _fonte(_Sessao([]))._parse(GERENTE_COMO_INTERN)
    assert job.seniority == ""


def test_gerente_rotulado_de_intern_e_descartado_no_pre_filtro():
    fonte = _fonte(_Sessao([]))
    assert fonte._pre_filtrar([fonte._parse(GERENTE_COMO_INTERN)]) == []


def test_pre_filtro_aceita_qualquer_modalidade_e_local():
    """Este projeto analisa vagas de todo tipo: presencial em Curitiba passa."""
    fonte = _fonte(_Sessao([]))
    presencial = fonte._parse({**ITEM, "id": "p", "workMode": "Onsite",
                               "location": "Curitiba, PR, BR"})
    remota = fonte._parse(ITEM)
    assert fonte._pre_filtrar([presencial, remota]) == [presencial, remota]


def test_all_levels_desliga_o_pre_filtro():
    """Com --all-levels o pipeline não corta por nível, então aqui também não."""
    fonte = _fonte(_Sessao([]), only_junior=False)
    gerente = fonte._parse(GERENTE_COMO_INTERN)
    assert fonte._pre_filtrar([gerente]) == [gerente]


@pytest.mark.parametrize("bruto,esperado", [
    ("Remote", REMOTO),
    ("Onsite", PRESENCIAL),
    ("Hybrid", HIBRIDO),
    ("Unknown", NAO_INFORMADO),
    (None, NAO_INFORMADO),
    ("ModoNovoQueAindaNaoExiste", NAO_INFORMADO),
])
def test_de_para_de_modalidade(bruto, esperado):
    job = _fonte(_Sessao([]))._parse({**ITEM, "workMode": bruto})
    assert job.workplace_type == esperado


@pytest.mark.parametrize("candidatura", [
    "manual://jobs/8c879549-fdbb-46d0-be6f-5c85c11c8be8",  # 31 vagas assim
    "rh@solus-it.com.br",   # candidatura por e-mail, medida no portal
    "",
    None,
])
def test_sem_url_navegavel_cai_na_pagina_do_portal(candidatura):
    """Sem reserva, essas vagas ficariam no CSV e na API com link que não abre."""
    job = _fonte(_Sessao([]))._parse({**ITEM, "applyUrl": candidatura})
    assert job.url == f"{SITE_URL}/vagas/{ITEM['id']}"


def test_url_de_candidatura_boa_e_preservada():
    job = _fonte(_Sessao([]))._parse(ITEM)
    assert job.url == ITEM["applyUrl"]


def test_item_sem_titulo_ou_id_e_ignorado():
    fonte = _fonte(_Sessao([]))
    assert fonte._parse({**ITEM, "title": "   "}) is None
    assert fonte._parse({**ITEM, "id": None}) is None


def test_paginacao_para_na_ultima_pagina():
    cheia = _envelope([{**ITEM, "id": f"id-{n}"} for n in range(PAGE_SIZE)], total=150)
    resto = _envelope([{**ITEM, "id": f"id-x{n}"} for n in range(50)], total=150)
    sessao = _Sessao([cheia, resto])
    jobs = _fonte(sessao)._listar()

    assert len(jobs) == 150
    assert len(sessao.urls) == 2, "não deve pedir uma terceira página"


def test_paginacao_respeita_o_total_mesmo_com_pagina_cheia():
    """Página cheia + total alcançado = fim; sem isso a coleta giraria à toa."""
    cheia = _envelope([{**ITEM, "id": f"id-{n}"} for n in range(PAGE_SIZE)],
                      total=PAGE_SIZE)
    sessao = _Sessao([cheia, cheia])
    _fonte(sessao)._listar()
    assert len(sessao.urls) == 1


def test_limite_anonimo_vira_aviso(caplog):
    """O portal tem campo para limitar anônimo; hoje não morde, mas pode."""
    envelope = _envelope([ITEM], isLimited=True, requiresAuthForMore=True,
                         anonymousVisibleLimit=10)
    with caplog.at_level("WARNING"):
        _fonte(_Sessao([envelope]))._listar()
    assert "limitar cliente anonimo" in caplog.text


def test_descricao_vem_do_endpoint_da_vaga_e_perde_html():
    detalhe = {"description": "<p>Atuar com <b>Python</b> e SQL.</p>"}
    sessao = _Sessao([], detalhes={ITEM["id"]: detalhe})
    fonte = _fonte(sessao)
    job = fonte._parse(ITEM)
    fonte._preencher_descricao(job)

    assert "<p>" not in job.description
    assert "Python" in job.description


def test_fetch_busca_descricao_so_das_candidatas():
    """A economia que justifica o pré-filtro: uma requisição por sobrevivente."""
    presencial = {**ITEM, "id": "presencial-cwb", "workMode": "Onsite",
                  "location": "Curitiba, PR, BR"}
    sessao = _Sessao([_envelope([ITEM, GERENTE_COMO_INTERN, presencial])],
                     detalhes={ITEM["id"]: {"description": "Vaga de Python."},
                               "presencial-cwb": {"description": "Vaga de Java."}})
    jobs = _fonte(sessao).fetch(["desenvolvedor junior"])

    assert [j.external_id for j in jobs] == [ITEM["id"], "presencial-cwb"]
    detalhes_pedidos = [u for u, p in sessao.urls if p is None]
    assert len(detalhes_pedidos) == 2, "o gerente não deve custar requisição"


def test_fetch_term_nao_e_usado():
    assert _fonte(_Sessao([])).fetch_term("desenvolvedor junior") == []


def test_teto_de_paginas_existe():
    assert MAX_PAGINAS >= 7
