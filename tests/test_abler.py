"""Parser do Abler, com recortes reais capturados do portal (offline).

Os recortes vieram do projeto irmao vagas-remotas-alerta (capturados em
22/09/2026), onde o coletor nasceu.
"""

from __future__ import annotations

import pytest

from scraper.config import Settings
from scraper.models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO
from scraper.sources.abler import MAX_VAGAS, SITEMAP_URL, AblerSource, _ler_nuxt

# Recorte real de https://candidatos.abler.com.br/sitemap.xml (22/09/2026).
SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
  <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url>
        <loc>https://candidatos.abler.com.br/vagas/</loc>
        <lastmod>2018-01-19T14:31:11+00:00</lastmod>
      </url>
        <url>
          <loc>https://candidatos.abler.com.br/vagas/desenvolvedor-fullstack-junior-637999</loc>
          <lastmod>2026-09-22T20:33:16+00:00</lastmod>
          <changefreq>weekly</changefreq>
        </url>
        <url>
          <loc>https://candidatos.abler.com.br/vagas/advogado-junior-154578</loc>
          <lastmod>2026-07-28T19:20:34+00:00</lastmod>
        </url>
        <url>
          <loc>https://candidatos.abler.com.br/vagas/desenvolvedor-a-android-senior-781479</loc>
          <lastmod>2026-07-28T19:34:54+00:00</lastmod>
        </url>
        <url>
          <loc>https://candidatos.abler.com.br/vagas/desenvolvedor-full-stack-jr-56946</loc>
          <lastmod>2025-07-08T17:17:52+00:00</lastmod>
        </url>
  </urlset>
"""


def _pagina(vaga: str, parametros: str = "a,b,c,d,e",
            argumentos: str = 'null,false,"",true,0') -> str:
    """Recorte real da página: o `__NUXT__` com a vaga em state.candidate.vacancy."""
    return (
        '<html><body><div id="__nuxt"></div><script>'
        f"window.__NUXT__=(function({parametros}){{return {{layout:\"default\","
        "data:[{},{isDesktopAsyncData:b},{}],fetch:{},error:a,"
        'state:{alerts:[],overlay:b,apiBaseURL:"https:\\u002F\\u002Fhulk-smash.abler.com.br\\u002Fapi",'
        "candidate:{vacancy:{vacancy:" + vaga + ",vacancies:[],pagination:a,loading:b,error:a}}},"
        'serverRendered:d,routePath:"\\u002Fvagas\\u002Fx",'
        'config:{_app:{basePath:"\\u002F",cdnURL:a}}}}'
        f"}}({argumentos}));"
        '</script><script src="/static/0628f1e.js" defer async></script></body></html>'
    )


# Vaga 393184 (AnkaTech): remota, empresa visível, nível "Júnior".
VAGA_REMOTA = (
    '{companyName:"AnkaTech",companyLogo:c,companyId:6072,'
    'title:"Desenvolvedor Fullstack Junior",titleFormatted:"Desenvolvedor Fullstack Junior",'
    'address:{cityId:"5389",stateId:"26",neighborhood:"Jardim Paulistano",id:"15395471",'
    'cep:c,street:c,number:c,complement:c,country:"Brasil",cityName:"S\\u00e3o Paulo",'
    'stateName:"S\\u00e3o Paulo",stateAbbr:"SP",'
    'formattedFullAddress:"Jardim Paulistano, S\\u00e3o Paulo - SP - Brasil"},'
    'areaOfInterests:[{id:"115",name:"Tecnologia da Informa\\u00e7\\u00e3o"}],'
    'company:{id:"6072",name:"AnkaTech",logo:c,url:void 0},'
    'contractingRegime:"pj",createdAt:"2026-09-21T15:10:23.772-03:00",'
    'description:"\\u003Cp\\u003E\\ud83d\\ude80 \\u003Cstrong\\u003EVaga: Fullstack Developer '
    'J\\u00fanior \\u2013 Sustenta\\u00e7\\u00e3o | Anka Tech\\u003C\\u002Fstrong\\u003E\\u003C\\u002Fp\\u003E'
    '\\u003Cp class=\\"ql-align-center\\"\\u003E\\u003Cbr\\u003E\\u003C\\u002Fp\\u003E",'
    'levelOfInterests:[{id:"16",name:"J\\u00fanior"}],hideCompany:b,'
    'publishedAt:"2026-09-21T15:39:39.701-03:00",id:"393184",salary:2500,'
    'slug:"desenvolvedor-fullstack-junior-637999",status:"Em andamento",'
    'workTypes:[{id:"remoto",name:void 0}],workTypeFormatted:void 0}'
)

# Vaga 391547: presencial em Natal, empresa oculta, nível "Assistente".
VAGA_OCULTA_NATAL = (
    '{companyName:"Conex\\u00e3o.CX",companyId:3725,'
    'title:"Atendente de Suporte T\\u00e9cnico J\\u00fanior",'
    'address:{cityId:"3798",stateId:"20",neighborhood:"Ne\\u00f3polis",id:"15289782",'
    'cep:c,country:"Brasil",cityName:"Natal",stateName:"Rio Grande do Norte",stateAbbr:"RN"},'
    'description:"\\u003Cp\\u003ESobre a vaga\\u003C\\u002Fp\\u003E",'
    'levelOfInterests:[{id:"4",name:"Assistente"}],hideCompany:d,'
    'publishedAt:"2026-09-11T15:37:53.928-03:00",id:"391547",'
    'workTypes:[{id:"presencial",name:void 0}]}'
)


def _source(sessao=None):
    return AblerSource(session=sessao, settings=Settings())


def test_pre_filtro_pelo_slug_exige_nivel_de_entrada_e_tecnologia():
    urls = _source()._candidatas(SITEMAP)
    # Advogado não é tech e Android é sênior; a raiz `/vagas/` não é vaga.
    assert urls == [
        "https://candidatos.abler.com.br/vagas/desenvolvedor-fullstack-junior-637999",
        "https://candidatos.abler.com.br/vagas/desenvolvedor-full-stack-jr-56946",
    ]


def test_lastmod_antigo_nao_corta_a_vaga():
    """Não há corte por idade: vaga de `lastmod` de 2025 segue "Em andamento".

    Medido em 24/09/2026: 8 candidatas com `lastmod` de 428 a 751 dias,
    abertas uma a uma, estavam todas em andamento.
    """
    assert ("https://candidatos.abler.com.br/vagas/desenvolvedor-full-stack-jr-56946"
            in _source()._candidatas(SITEMAP))


def test_parse_mapeia_os_campos():
    job = _source()._parse(_pagina(VAGA_REMOTA), "https://candidatos.abler.com.br/vagas/x")
    assert job.source == "abler"
    assert job.external_id == "393184"  # o da página, não o 637999 do slug
    assert job.title == "Desenvolvedor Fullstack Junior"
    assert job.company == "AnkaTech"
    assert job.url == "https://candidatos.abler.com.br/vagas/x"
    assert job.location == "São Paulo, SP"
    assert job.workplace_type == REMOTO
    assert job.published_date == "2026-09-21"
    assert job.description.startswith("🚀 Vaga: Fullstack Developer Júnior")
    assert "<" not in job.description


def test_nivel_do_portal_nao_e_aproveitado():
    """"Assistente" numa vaga júnior: o título decide, não o portal."""
    job = _source()._parse(_pagina(VAGA_OCULTA_NATAL), "u")
    assert job.seniority == ""


def test_empresa_oculta_fica_vazia():
    """Vazia, e não um rótulo: "Empresa confidencial" fundiria vagas no dedupe."""
    job = _source()._parse(_pagina(VAGA_OCULTA_NATAL), "u")
    assert job.company == ""
    assert job.location == "Natal, RN"
    assert job.workplace_type == PRESENCIAL


def test_variaveis_do_nuxt_mudam_de_pagina_para_pagina():
    # A mesma vaga, com as letras trocadas: `d` agora é false e `b` é true.
    vaga = VAGA_OCULTA_NATAL.replace("hideCompany:d", "hideCompany:x")
    job = _source()._parse(
        _pagina(vaga, parametros="a,b,c,d,e,x", argumentos='null,true,"",false,0,false'), "u")
    assert job.company == "Conexão.CX"


@pytest.mark.parametrize("tipos,esperado", [
    ('[{id:"remoto",name:void 0}]', REMOTO),
    ('[{id:"hibrida",name:void 0}]', HIBRIDO),
    ('[{id:"presencial",name:void 0}]', PRESENCIAL),
    ("[]", NAO_INFORMADO),
    ('[{id:"remoto"},{id:"presencial"}]', NAO_INFORMADO),
    ('[{id:"modo-novo"}]', NAO_INFORMADO),
])
def test_de_para_de_modalidade(tipos, esperado):
    vaga = VAGA_REMOTA.replace('workTypes:[{id:"remoto",name:void 0}]', f"workTypes:{tipos}")
    assert _source()._parse(_pagina(vaga), "u").workplace_type == esperado


def test_pagina_sem_vaga_devolve_none():
    assert _source()._parse(_pagina("a"), "u") is None
    assert _source()._parse("<html></html>", "u") is None


def test_nuxt_quebrado_nao_estoura():
    assert _ler_nuxt("<script>window.__NUXT__=(function(a){return {x:</script>") is None


def test_numero_sem_zero_antes_do_ponto():
    # `salaryValue:.01` veio numa página real (vaga 391212) e quebrava a leitura.
    vaga = VAGA_REMOTA.replace("salary:2500", 'salary:"A combinar",salaryValue:.01')
    job = _source()._parse(_pagina(vaga), "u")
    assert job is not None and job.external_id == "393184"


class _Resposta:
    def __init__(self, text):
        self.text = text


class _Sessao:
    def __init__(self, paginas):
        self.paginas = paginas
        self.request_count = 0

    def get(self, url, **kwargs):
        self.request_count += 1
        html = self.paginas.get(url)
        return None if html is None else _Resposta(html)


def test_sitemap_indisponivel_nao_derruba_a_coleta():
    fonte = _source(_Sessao({}))
    assert fonte.fetch([]) == []
    assert fonte.stats.raw_jobs == 0


def test_fetch_vai_do_sitemap_a_pagina_e_fecha_as_estatisticas():
    url = "https://candidatos.abler.com.br/vagas/desenvolvedor-fullstack-junior-637999"
    # A página da outra candidata (a de 2025) falha: ela some, mas a coleta segue.
    fonte = _source(_Sessao({SITEMAP_URL: SITEMAP, url: _pagina(VAGA_REMOTA)}))
    jobs = fonte.fetch(["ignorado"])
    assert [j.external_id for j in jobs] == ["393184"]
    assert fonte.stats.raw_jobs == 1
    assert fonte.stats.requests_made == 3  # sitemap + as duas candidatas


def test_fetch_term_nao_e_usado():
    assert _source().fetch_term("qualquer") == []


def test_teto_de_seguranca_cabe_a_medicao():
    # 94 candidatas em 24/09/2026; o teto deixa folga sem virar varredura.
    assert 94 < MAX_VAGAS <= 200
