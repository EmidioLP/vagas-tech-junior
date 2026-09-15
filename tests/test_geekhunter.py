"""Parser da GeekHunter, com recortes reais capturados do portal (offline)."""

from __future__ import annotations

from scraper.config import Settings
from scraper.models import NAO_INFORMADO, REMOTO
from scraper.sources.geekhunter import MAX_VAGAS, SITEMAP_URL, GeekHunterSource

# Recorte real de https://www.geekhunter.com/sitemap.xml -- a mesma vaga
# aparece em quatro idiomas, e só a de /pt/ deve entrar.
SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.geekhunter.com/tech-recruiter-as-a-service</loc></url>
<url><loc>https://www.geekhunter.com/nava/jobs/analista-de-redes-junior-1</loc></url>
<url><loc>https://www.geekhunter.com/pt/nava/jobs/analista-de-redes-junior-1</loc></url>
<url><loc>https://www.geekhunter.com/en/nava/jobs/analista-de-redes-junior-1</loc></url>
<url><loc>https://www.geekhunter.com/es/nava/jobs/analista-de-redes-junior-1</loc></url>
<url><loc>https://www.geekhunter.com/pt/ntt/jobs/estagio-testes-em-hardware-1</loc></url>
<url><loc>https://www.geekhunter.com/pt/ntt/jobs/engenheiro-de-redes-senior-1</loc></url>
<url><loc>https://www.geekhunter.com/pt/acme/jobs/desenvolvedor-backend-pleno-2</loc></url>
</urlset>
"""


# Recorte real de uma página de vaga: o bloco JobPosting entre os outros ld+json.
def _pagina(job_posting: str, chip: str = "Presencial") -> str:
    return f"""
    <html><head>
    <script type="application/ld+json">{{"@type":"Organization","name":"GeekHunter"}}</script>
    <script type="application/ld+json">{job_posting}</script>
    </head><body><span class="chip">{chip}</span></body></html>
    """


VAGA_PRESENCIAL = """{
  "@context": "https://schema.org", "@type": "JobPosting",
  "identifier": {"@type": "PropertyValue", "name": "GeekHunter", "value": "5a43fdb3236c"},
  "title": "Analista de Redes J\\u00fanior",
  "datePosted": "2026-08-13",
  "employmentType": ["FULL_TIME"],
  "description": "<p>Atuar com <b>redes</b> e observabilidade.</p>",
  "skills": ["Linux", "Zabbix", "Redes"],
  "hiringOrganization": {"@type": "Organization", "name": "Nava Technology"},
  "jobLocation": [{"@type": "Place", "address": {"@type": "PostalAddress",
      "addressLocality": "Curitiba", "addressRegion": "PR", "addressCountry": "BR"}}]
}"""

VAGA_REMOTA = """{
  "@context": "https://schema.org", "@type": "JobPosting",
  "identifier": {"@type": "PropertyValue", "value": "abc999"},
  "title": "Desenvolvedor Backend Java J\\u00fanior",
  "datePosted": "2026-08-06",
  "description": "Vaga para atuar com Java e Azure.",
  "jobLocationType": "TELECOMMUTE",
  "applicantLocationRequirements": {"@type": "Country", "name": "BR"},
  "hiringOrganization": {"@type": "Organization", "name": "NTT DATA"}
}"""


class _Resposta:
    def __init__(self, text):
        self.text = text


def _source():
    return GeekHunterSource(session=None, settings=Settings())


def _com_sitemap(monkeypatch, texto):
    fonte = _source()
    sessao = type("S", (), {"get": lambda self, url: _Resposta(texto)})()
    monkeypatch.setattr(fonte, "session", sessao)
    return fonte


def test_so_entram_urls_em_portugues_de_nivel_de_entrada(monkeypatch):
    """O sitemap repete a vaga em 4 idiomas; sênior e pleno não entram."""
    urls = _com_sitemap(monkeypatch, SITEMAP)._urls_de_entrada()
    assert urls == [
        "https://www.geekhunter.com/pt/nava/jobs/analista-de-redes-junior-1",
        "https://www.geekhunter.com/pt/ntt/jobs/estagio-testes-em-hardware-1",
    ]


def test_aceita_o_dominio_com_br_tambem(monkeypatch):
    """O portal serve o mesmo sitemap em .com e .com.br."""
    sitemap = SITEMAP.replace("geekhunter.com/", "geekhunter.com.br/")
    urls = _com_sitemap(monkeypatch, sitemap)._urls_de_entrada()
    assert len(urls) == 2
    assert all(".com.br/pt/" in u for u in urls)


def test_sitemap_e_o_do_dominio_que_o_robots_aponta():
    assert SITEMAP_URL == "https://www.geekhunter.com/sitemap.xml"


def test_sitemap_indisponivel_nao_derruba_a_coleta(monkeypatch):
    fonte = _source()
    monkeypatch.setattr(fonte, "session", type("S", (), {"get": lambda *_: None})())
    assert fonte._urls_de_entrada() == []


def test_parse_mapeia_os_campos_da_vaga():
    url = "https://www.geekhunter.com/pt/nava/jobs/analista-de-redes-junior-1"
    job = _source()._parse(_pagina(VAGA_PRESENCIAL), url)

    assert job is not None
    assert job.source == "geekhunter"
    assert job.external_id == "5a43fdb3236c"
    assert job.title == "Analista de Redes Júnior"
    assert job.company == "Nava Technology"
    assert job.url == url
    assert job.location == "Curitiba, PR"
    assert job.published_date == "2026-08-13"


def test_descricao_perde_o_html():
    job = _source()._parse(_pagina(VAGA_PRESENCIAL), "https://x/jobs/y")
    assert "<p>" not in job.description
    assert "redes" in job.description


def test_skills_declaradas_entram_na_descricao():
    """Sinal direto para o extrator de tecnologias, como as tags da ProgramaThor."""
    job = _source()._parse(_pagina(VAGA_PRESENCIAL), "https://x/jobs/y")
    assert job.description.startswith("Tecnologias: Linux, Zabbix, Redes.")


def test_skills_em_texto_tambem_funciona():
    vaga = VAGA_PRESENCIAL.replace('["Linux", "Zabbix", "Redes"]', '"Linux, Zabbix"')
    job = _source()._parse(_pagina(vaga), "https://x/jobs/y")
    assert "Tecnologias: Linux, Zabbix." in job.description


def test_vaga_sem_skills_nao_ganha_prefixo_vazio():
    job = _source()._parse(_pagina(VAGA_REMOTA, chip="Remoto"), "https://x/jobs/y")
    assert "Tecnologias" not in job.description


def test_telecommute_prova_remoto():
    job = _source()._parse(_pagina(VAGA_REMOTA, chip="Remoto"), "https://x/jobs/y")
    assert job.workplace_type == REMOTO


def test_sem_telecommute_vale_o_rotulo_da_pagina():
    """O schema.org só marca remoto; presencial e híbrida vêm do rótulo."""
    job = _source()._parse(_pagina(VAGA_PRESENCIAL, chip="Híbrido"), "https://x/jobs/y")
    assert job.workplace_type == "Híbrido"


def test_pagina_com_varios_rotulos_nao_adivinha_modalidade():
    """Se a página lista os três, nenhum é desta vaga."""
    html = _pagina(VAGA_PRESENCIAL).replace(
        '<span class="chip">Presencial</span>',
        "<span>Remoto</span><span>Híbrido</span><span>Presencial</span>")
    job = _source()._parse(html, "https://x/jobs/y")
    assert job.workplace_type == NAO_INFORMADO


def test_pagina_sem_jobposting_devolve_none():
    html = '<script type="application/ld+json">{"@type":"WebSite"}</script>'
    assert _source()._parse(html, "https://x/jobs/y") is None


def test_ld_json_quebrado_nao_estoura():
    html = '<script type="application/ld+json">{isso nao e json}</script>'
    assert _source()._parse(html, "https://x/jobs/y") is None


def test_identificador_cai_no_slug_quando_falta():
    sem_id = VAGA_PRESENCIAL.replace(
        '"identifier": {"@type": "PropertyValue", "name": "GeekHunter", "value": "5a43fdb3236c"},', "")
    job = _source()._parse(_pagina(sem_id), "https://x/jobs/analista-de-redes-junior-1")
    assert job.external_id == "analista-de-redes-junior-1"


def test_vaga_sem_local_nao_inventa_um():
    job = _source()._parse(_pagina(VAGA_REMOTA, chip="Remoto"), "https://x/jobs/y")
    assert job.location == ""


def test_fetch_term_nao_e_usado():
    """A superfície liberada pelo robots.txt não tem busca por palavra."""
    assert _source().fetch_term("desenvolvedor junior") == []


def test_teto_de_seguranca_existe():
    assert MAX_VAGAS >= 50
