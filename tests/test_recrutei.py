"""Coletor do Recrutei, com recortes reais do portal (offline).

Os tres cards foram capturados aqui em 02/10/2026, depois do redesign da
listagem (30/09/2026), sem corte nenhum: a indentacao larga e os `?has_bot=1`
sao como chegaram. `CARD_REMOTO` e `CARD_PRESENCIAL_OU_REMOTO` vieram de
`/vagas/tecnologia`, e `CARD_ANONIMO` de `/vagas/tecnologia?page=4`. Os dois
JSON-LD vieram do projeto irmao vagas-remotas-alerta (22/09/2026); a pagina da
vaga nao mudou.
"""

from __future__ import annotations

import re

from scraper.classifier import default_classifier
from scraper.config import Settings
from scraper.models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO
from scraper.sources.recrutei import (CATEGORIAS, MAX_PAGINAS, PAGE_SIZE, PORTAL_URL,
                                      RecruteiSource)

# Vaga remota. O local "Brasil" e como o portal mostra a vaga sem cidade.
CARD_REMOTO = """                                                        <article class="d2-card d2-jobrow">
    <span class="d2-logo d2-logo--56 d2-logo--mark"  >
    <img src="https://recrutei-web.s3.amazonaws.com/storage/files/logos/MwAtdRnZPfDeTxxFrOlufMEq0cADc9beBvtl3Kpf.png" alt="Logo THERA CONSULTING" width="56" height="56" loading="lazy" decoding="async"  style="--w:100.00;--l:0.00;--t:30.44" >
</span>
    <div class="d2-jobrow__main">
        <h3 class="d2-jobrow__title">
            <a href="https://empregos.recrutei.com.br/vaga/thera-consulting/160383-consultor-sap-abap-senior?has_bot=1" >Consultor SAP ABAP - Sênior</a>
        </h3>
        <p class="d2-jobrow__meta">THERA CONSULTING · Brasil</p>
        <div class="d2-badges">
                            <span class="d2-badge d2-badge--success">Vaga nova</span>
                                    <span class="d2-badge d2-badge--default">Pessoa Jurídica</span>            <span class="d2-badge d2-badge--default">Remoto</span>        </div>
    </div>
    <div class="d2-jobrow__side">
        <span class="d2-jobrow__salary is-empty">Não informado</span>
                    <span class="d2-jobrow__time"><svg class="d2-icon" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
Publicada há 10 horas</span>
                <div class="d2-jobrow__actions">
            
            <a href="https://empregos.recrutei.com.br/vaga/thera-consulting/160383-consultor-sap-abap-senior?has_bot=1" class="d2-btn d2-btn--primary" >Candidatar-se</a>
        </div>
    </div>
</article>"""

# A quarta modalidade: o portal a separa de "Remoto" no proprio filtro
# (`model=presential-remote`).
CARD_PRESENCIAL_OU_REMOTO = """                                                <article class="d2-card d2-jobrow">
    <span class="d2-logo d2-logo--56 d2-logo--mark"  >
    <img src="https://recrutei-web.s3.amazonaws.com/storage/files/logos/MwAtdRnZPfDeTxxFrOlufMEq0cADc9beBvtl3Kpf.png" alt="Logo THERA CONSULTING" width="56" height="56" loading="lazy" decoding="async"  style="--w:100.00;--l:0.00;--t:30.44" >
</span>
    <div class="d2-jobrow__main">
        <h3 class="d2-jobrow__title">
            <a href="https://empregos.recrutei.com.br/vaga/thera-consulting/160477-desenvolvedor-oracle?has_bot=1" >DESENVOLVEDOR ORACLE</a>
        </h3>
        <p class="d2-jobrow__meta">THERA CONSULTING · São Paulo, SP</p>
        <div class="d2-badges">
                            <span class="d2-badge d2-badge--success">Vaga nova</span>
                                    <span class="d2-badge d2-badge--default">Pessoa Jurídica</span>            <span class="d2-badge d2-badge--default">Presencial ou Remoto</span>        </div>
    </div>
    <div class="d2-jobrow__side">
        <span class="d2-jobrow__salary is-empty">Não informado</span>
                    <span class="d2-jobrow__time"><svg class="d2-icon" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
Publicada há 4 horas</span>
                <div class="d2-jobrow__actions">
            
            <a href="https://empregos.recrutei.com.br/vaga/thera-consulting/160477-desenvolvedor-oracle?has_bot=1" class="d2-btn d2-btn--primary" >Candidatar-se</a>
        </div>
    </div>
</article>"""

# Empresa anonima: link com UUID, e a pagina da vaga responde 404.
CARD_ANONIMO = """                                                        <article class="d2-card d2-jobrow">
    <span class="d2-logo d2-logo--initials d2-logo--56" aria-hidden="true">EA</span>
    <div class="d2-jobrow__main">
        <h3 class="d2-jobrow__title">
            <a href="https://empregos.recrutei.com.br/vaga/anonimo/15bcd025-d74d-4ad8-8599-eb10f995f820" >Supervisor da Central de Serviços e Monitoramento</a>
        </h3>
        <p class="d2-jobrow__meta">Empresa anônima · São Paulo, SP</p>
        <div class="d2-badges">
                                                <span class="d2-badge d2-badge--default">Presencial</span>        </div>
    </div>
    <div class="d2-jobrow__side">
        <span class="d2-jobrow__salary is-empty">Não informado</span>
                    <span class="d2-jobrow__time"><svg class="d2-icon" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
Publicada há 3 dias</span>
                <div class="d2-jobrow__actions">
            
            <a href="https://empregos.recrutei.com.br/vaga/anonimo/15bcd025-d74d-4ad8-8599-eb10f995f820" class="d2-btn d2-btn--primary" >Candidatar-se</a>
        </div>
    </div>
</article>"""

# Os dois JSON-LD da pagina da vaga, na ordem em que ela os traz.
_LD_JOB_POSTING = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"ENGENHEIRO DE IA JR","description":"BM VAGAS em parceria com Bhaskara Consultoria em Inteligencia Artificial seleciona ENGENHEIRO DE IA JR para cidade de São José dos Campos.ResponsabilidadesDesenvolver e evoluir o Post4u, produto de IA para planejamento, criação e publicação de conteúdo em redes sociais.Implementar funcionalidades no frontend e backend, integrar APIs de IA, redes sociais, pagamentos e banco de dados, corrigir bugs e melhorar a experiência do usuário.Trabalhar a partir de prioridades e critérios de aceite, registrar decisões e evidências das entregas, escrever e executar testes proporcionais ao risco e acompanhar o produto em produção.Usar ferramentas de IA intensivamente para acelerar pesquisa, implementação, revisão e documentação, mantendo raciocínio crítico, segurança e qualidade técnica.RequisitosAprendizado rápido, abertura a feedback, curiosidade, autonomia, organização, pensamento crítico, uso prático de inteligência artificial, criação de prompts, programação com IA assistida (SDD, TDD), Python, RAG, tools, MCP, Git e GitHub, banco de dados SQL, PostgreSQL, integração com APIs externas, autenticação, testes automatizados, depuração de bugs, fundamentos de segurança de aplicações, leitura de documentação técnica, comunicação clara, atenção a detalhesSuperior Incompleto / cursandoDeterminado e gosta de desafiosHorário0","datePosted":"2026-08-23T01:58:05.000000Z","validThrough":"2026-10-23T01:58:05+00:00","employmentType":["FULL_TIME"],"jobBenefits":"","industry":"","skills":"TypeScript, JavaScript, React, HTML, CSS, APIs REST, programação com IA assistida (SDD, TDD), Python, RAG, tools, MCP, Git e GitHub, banco de dados SQL, PostgreSQL, integração com APIs externas, autenticação, testes automatizados, depuração de bugs, fundamentos de segurança de aplicações, leitura de documentação técnica, aprendizado rápido, autonomia, organização, pensamento crítico, comunicação clara, atenção a detalhes","workHours":"0","salaryCurrency":"BRL","hiringOrganization":{"@type":"Organization","name":"BM VAGAS","sameAs":"","logo":"https://d2bxzineatl84k.cloudfront.net/storage/files/logos/P0JDnmDSmhB2hDgjNgu9pOqPKgukqC25InMwmNms.png"},"jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"São José dos Campos","addressRegion":"SP","addressCountry":"Brasil"}}}</script>"""

_LD_BREADCRUMB = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"Início","item":"https://empregos.recrutei.com.br"},{"@type":"ListItem","position":2,"name":"SP","item":"https://empregos.recrutei.com.br/vagas/em/sp"},{"@type":"ListItem","position":3,"name":"ENGENHEIRO DE IA JR","item":"https://empregos.recrutei.com.br/vaga/bm-vagas/155283-engenheiro-de-ia-jr"}]}</script>"""

URL_REMOTA = f"{PORTAL_URL}/vaga/thera-consulting/160383-consultor-sap-abap-senior"
TECNOLOGIA = f"{PORTAL_URL}/vagas/tecnologia"

_TITULO_RE = re.compile(r'(<h3 class="d2-jobrow__title">\s*<a [^>]*>)[^<]*(</a>)')


def _pagina(*cards: str) -> str:
    """Envolve os cards no esqueleto da listagem, como o portal devolve."""
    return ('<html><body><div class="row">' + "".join(cards)
            + "</div></body></html>")


def _com_id(card: str, identificador: str) -> str:
    """O mesmo card com outro id, para exercitar dedupe e paginacao."""
    return re.sub(r"/(\d{6})-", f"/{identificador}-", card)


def _com_titulo(card: str, titulo: str) -> str:
    return _TITULO_RE.sub(lambda m: m.group(1) + titulo + m.group(2), card)


def _cheia(inicio: int = 0, anonimo: bool = False) -> str:
    """Pagina cheia de PAGE_SIZE cards distintos; o ultimo pode ser anonimo."""
    cards = [_com_id(CARD_REMOTO, str(900000 + inicio + i)) for i in range(PAGE_SIZE)]
    if anonimo:
        cards[-1] = CARD_ANONIMO
    return _pagina(*cards)


def _detalhe(posting: str = "", breadcrumb: bool = True) -> str:
    """A pagina da vaga, reduzida ao que o coletor le."""
    partes = [posting or _LD_JOB_POSTING]
    if breadcrumb:
        # O breadcrumb vem ANTES na pagina real; e o distrator do seletor.
        partes.insert(0, _LD_BREADCRUMB)
    return "<html><head>" + "".join(partes) + "</head><body></body></html>"


class _Resposta:
    def __init__(self, text: str) -> None:
        self.text = text


class _Sessao:
    """Substitui a PoliteSession. Nenhum teste toca em rede.

    URL que nao esta no dicionario devolve None -- que e como a sessao de
    verdade avisa que desistiu. Guarda o `conta_falha` de cada chamada.
    """

    def __init__(self, respostas: dict | None = None) -> None:
        self.respostas = dict(respostas or {})
        self.chamadas: list[tuple[str, bool]] = []
        self.request_count = 0

    def get(self, url, conta_falha=True, **kwargs):
        self.chamadas.append((url, conta_falha))
        self.request_count += 1
        corpo = self.respostas.get(url)
        return None if corpo is None else _Resposta(corpo)

    @property
    def urls(self) -> list[str]:
        return [u for u, _ in self.chamadas]


def _fonte(sessao=None):
    return RecruteiSource(session=sessao, settings=Settings())


def _parse(card: str):
    return _fonte()._parse_page(_pagina(card))


# ---- parser

def test_parse_mapeia_campos():
    [job] = _parse(CARD_REMOTO)
    assert job.source == "recrutei"
    assert job.external_id == "160383"
    assert job.title == "Consultor SAP ABAP - Sênior"
    assert job.company == "THERA CONSULTING"
    assert job.location == "Brasil"
    assert job.workplace_type == REMOTO
    assert job.seniority == ""  # o portal nao declara; o regex decide
    assert job.description == ""  # so vem do detalhe
    assert job.published_date == ""  # a do card e relativa; a exata vem do detalhe


def test_query_de_rastreio_sai_da_url():
    [job] = _parse(CARD_REMOTO)
    assert job.url == URL_REMOTA


def test_local_com_uf_volta_a_ter_o_pais():
    """O card perdeu o ", Brasil" no redesign, e `location` entra no hash."""
    [job] = _parse(CARD_PRESENCIAL_OU_REMOTO)
    assert job.company == "THERA CONSULTING"
    assert job.location == "São Paulo, SP, Brasil"


def test_card_sem_local_fica_so_com_a_empresa():
    # Forma real de 02/10/2026: `<p class="d2-jobrow__meta">Digisystem</p>`.
    [job] = _parse(CARD_REMOTO.replace("THERA CONSULTING · Brasil", "Digisystem"))
    assert (job.company, job.location) == ("Digisystem", "")


def test_presencial_ou_remoto_e_hibrido_e_nao_remoto():
    [job] = _parse(CARD_PRESENCIAL_OU_REMOTO)
    assert job.workplace_type == HIBRIDO


def test_selo_de_regime_nao_vira_modalidade():
    # "Vaga nova" e "Pessoa Jurídica" vem antes do selo "Remoto" no mesmo card.
    [job] = _parse(CARD_REMOTO)
    assert job.workplace_type == REMOTO


def test_modalidade_presencial():
    [job] = _parse(CARD_REMOTO.replace(">Remoto</span>", ">Presencial</span>"))
    assert job.workplace_type == PRESENCIAL


def test_card_sem_selo_de_modalidade_fica_nao_informado():
    [job] = _parse(CARD_REMOTO.replace(">Remoto</span>", "></span>"))
    assert job.workplace_type == NAO_INFORMADO


def test_card_anonimo_e_descartado_e_contado():
    fonte = _fonte()
    [job] = fonte._parse_page(_pagina(CARD_ANONIMO, CARD_REMOTO))
    assert job.external_id == "160383"
    assert fonte._parse_page(_pagina(CARD_ANONIMO)) == []
    assert fonte._anonimas == 2


def test_pagina_sem_card_devolve_vazio():
    assert _fonte()._parse_page("<html><body></body></html>") == []


# ---- detalhe

def test_descricao_e_data_vem_do_json_ld():
    [job] = _parse(CARD_REMOTO)
    _fonte(_Sessao({URL_REMOTA: _detalhe()}))._preencher_detalhe(job)
    assert job.description.startswith("BM VAGAS em parceria com Bhaskara")
    assert job.published_date == "2026-08-23"


def test_breadcrumb_nao_e_confundido_com_a_vaga():
    assert RecruteiSource._job_posting(_detalhe())["@type"] == "JobPosting"


def test_pagina_sem_json_ld_ou_quebrado_nao_derruba():
    quebrado = '<script type="application/ld+json">{nao e json</script>'
    for pagina in ("<html></html>", f"<html><head>{quebrado}</head></html>"):
        [job] = _parse(CARD_REMOTO)
        _fonte(_Sessao({URL_REMOTA: pagina}))._preencher_detalhe(job)
        assert job.description == ""


def test_falha_no_detalhe_nao_conta_como_falha_da_fonte():
    """Como no LinkedIn: a vaga ja foi listada e segue sem descricao."""
    [job] = _parse(CARD_REMOTO)
    sessao = _Sessao({})
    _fonte(sessao)._preencher_detalhe(job)
    assert sessao.chamadas == [(URL_REMOTA, False)]
    assert job.description == ""


def test_e_a_descricao_que_faz_a_vaga_passar_no_portao_tech():
    """O motivo de abrir a pagina: o titulo sozinho reprova esta vaga.

    Titulo real de 24/09/2026; 8 das 29 vagas finais daquela coleta so passaram
    no portao pela descricao.
    """
    clf = default_classifier()
    [job] = _parse(_com_titulo(CARD_REMOTO, "Analista de Solução de Dados Junior"))
    assert not clf.is_tech(job.title)
    _fonte(_Sessao({URL_REMOTA: _detalhe()}))._preencher_detalhe(job)
    assert clf.is_tech(job.title, job.description)


# ---- paginacao

def test_segue_para_a_pagina_seguinte_quando_a_atual_enche():
    sessao = _Sessao({TECNOLOGIA: _cheia(0), f"{TECNOLOGIA}?page=2": _pagina(CARD_REMOTO)})
    assert len(_fonte(sessao)._listar(TECNOLOGIA)) == PAGE_SIZE + 1


def test_card_anonimo_nao_encerra_a_paginacao():
    """12 cards e 11 vagas: contar vagas parava `tecnologia` em 131 de 521."""
    sessao = _Sessao({TECNOLOGIA: _cheia(0, anonimo=True),
                      f"{TECNOLOGIA}?page=2": _pagina(CARD_REMOTO)})
    jobs = _fonte(sessao)._listar(TECNOLOGIA)
    assert f"{TECNOLOGIA}?page=2" in sessao.urls
    assert len(jobs) == PAGE_SIZE  # 11 da primeira + 1 da segunda


def test_pagina_incompleta_encerra():
    sessao = _Sessao({TECNOLOGIA: _pagina(CARD_REMOTO)})
    _fonte(sessao)._listar(TECNOLOGIA)
    assert sessao.urls == [TECNOLOGIA]


def test_pagina_vazia_encerra():
    sessao = _Sessao({TECNOLOGIA: _cheia(0), f"{TECNOLOGIA}?page=2": _pagina()})
    assert len(_fonte(sessao)._listar(TECNOLOGIA)) == PAGE_SIZE
    assert f"{TECNOLOGIA}?page=3" not in sessao.urls


def test_pagina_repetida_encerra():
    sessao = _Sessao({TECNOLOGIA: _cheia(0), f"{TECNOLOGIA}?page=2": _cheia(0)})
    assert len(_fonte(sessao)._listar(TECNOLOGIA)) == PAGE_SIZE
    assert f"{TECNOLOGIA}?page=3" not in sessao.urls


def test_respeita_o_teto_de_paginas():
    class _SempreCheia(_Sessao):
        def get(self, url, conta_falha=True, **kwargs):
            super().get(url, conta_falha)
            return _Resposta(_cheia(len(self.chamadas) * PAGE_SIZE))

    sessao = _SempreCheia()
    _fonte(sessao)._listar(TECNOLOGIA)
    assert len(sessao.chamadas) == MAX_PAGINAS


def test_falha_de_rede_encerra_sem_derrubar_a_coleta():
    assert _fonte(_Sessao({}))._listar(TECNOLOGIA) == []


# ---- fetch

def test_categorias_medidas():
    # `dados` saiu em 02/10/2026: passou a redirecionar para `tecnologia`.
    assert CATEGORIAS == ("tecnologia",)


def test_fetch_ignora_termos_e_abre_so_vagas_de_entrada_uma_vez():
    junior = _com_titulo(CARD_REMOTO, "Desenvolvedor Júnior")
    pleno = _com_titulo(_com_id(CARD_REMOTO, "160384"), "Desenvolvedor Pleno")
    sessao = _Sessao({TECNOLOGIA: _pagina(junior, pleno), URL_REMOTA: _detalhe()})
    fonte = _fonte(sessao)
    jobs = fonte.fetch(["termo ignorado"])

    assert [j.external_id for j in jobs] == ["160383"]
    assert jobs[0].seniority == "Júnior"
    assert jobs[0].description
    # A pagina da vaga junior abre uma vez so; a da pleno nunca.
    assert sessao.urls == [TECNOLOGIA, URL_REMOTA]
    assert fonte.stats.raw_jobs == 1
    assert fonte.stats.requests_made == 2


def test_vaga_repetida_entre_categorias_abre_uma_vez_so(monkeypatch):
    """Era o caso de `tecnologia` e `dados`; segue valendo se entrar outra."""
    outra = f"{PORTAL_URL}/vagas/outra"
    monkeypatch.setattr("scraper.sources.recrutei.CATEGORIAS", ("tecnologia", "outra"))
    junior = _com_titulo(CARD_REMOTO, "Desenvolvedor Júnior")
    sessao = _Sessao({TECNOLOGIA: _pagina(junior), outra: _pagina(junior),
                      URL_REMOTA: _detalhe()})
    jobs = _fonte(sessao).fetch([])

    assert [j.external_id for j in jobs] == ["160383"]
    assert sessao.urls == [TECNOLOGIA, outra, URL_REMOTA]


def test_fetch_term_nao_e_usado():
    assert _fonte().fetch_term("qualquer") == []
