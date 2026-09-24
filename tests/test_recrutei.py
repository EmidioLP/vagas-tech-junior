"""Coletor do Recrutei, com recortes reais do portal (offline).

Os cards `CARD_REMOTO` e `CARD_PRESENCIAL_OU_REMOTO` e os dois JSON-LD vieram do
projeto irmao vagas-remotas-alerta (capturados em 22/09/2026, sem corte nenhum:
a indentacao larga e os `?has_bot=1` sao como chegaram). `CARD_ANONIMO` foi
capturado aqui, de `/vagas/tecnologia?page=11`, em 24/09/2026.
"""

from __future__ import annotations

import re

from scraper.classifier import default_classifier
from scraper.config import Settings
from scraper.models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO
from scraper.sources.recrutei import (CATEGORIAS, MAX_PAGINAS, PAGE_SIZE, PORTAL_URL,
                                      RecruteiSource)

# Vaga remota, a forma mais comum na listagem de home office do irmao.
CARD_REMOTO = """<div class="list-grid-item rounded position-relative">
                        <a href="https://empregos.recrutei.com.br/vaga/gex-corporation/158928-analista-de-atendimento?has_bot=1" 
                    class="position-absolute w-100 h-100"></a>
                        <div class="grid-item-content p-3">
                <div class="grid-list-img mt-3">
                                            <a href="https://empregos.recrutei.com.br/vaga/gex-corporation/158928-analista-de-atendimento?has_bot=1">
                                                                        <img src="https://recrutei-web.s3.amazonaws.com/storage/files/logos/BBQWfUgye4Sr6wUjaGVQbdXoGJ3NVceifvdqr19V.jpg" alt="Logo GEX Corporation" class="img-fluid d-block" loading="lazy">
                                            </a>
                </div>
                <div class="grid-list-desc mt-3">
                    <h6 class="mb-1">
                                                    <a href="https://empregos.recrutei.com.br/vaga/gex-corporation/158928-analista-de-atendimento?has_bot=1"
                        class="job-title">Analista de Atendimento</a>
                                            </h6>
                                                    <p class="text-muted f-14 mb-1"><i class="mdi mdi-bank mr-2 text-primary-light"></i>GEX Corporation</p>
                                                                            <p class="text-muted mb-1"><i class="mdi mdi-map-marker text-primary-light"></i>
                                                                    Brasil
                                                            </p>
                                                                                                    <p class="text-muted mb-1 small"><i class="fa fa-solid fa-comments-dollar text-primary-light"></i> Não informado</p>
                                            <p class="text-muted mb-1"><i
                        class="mdi mdi-clock-outline text-primary-light"></i>
                        <span class="small">
                            Publicada há 6 horas
                        </span>
                   </p>
                </div>
                <ul class="list-inline">
                    <li class="list-inline-item">
                                                <span class="badge bg-primary-light text-white">
                            Pessoa Jurídica
                        </span>
                                            </li>
                    <li class="list-inline-item ">
                        <span class="badge bg-primary text-white">Remoto</span>
                    </li>
                    <li class="list-inline-item">
                                            </li>
                </ul>
            </div>
            <div class="apply-button p-3 border-top bg-light text-right">
                                <a href="https://empregos.recrutei.com.br/vaga/gex-corporation/158928-analista-de-atendimento?has_bot=1" class="btn btn-sm btn-success mb-2">Candidate-se por <i class="fa fa-brands fa-whatsapp"></i> Whatsapp</a>
                                                    <a href="https://empregos.recrutei.com.br/vaga/gex-corporation/158928-analista-de-atendimento?has_bot=1" class="btn btn-sm btn-secondary">Candidatar-se</a>
                            </div>
        </div>"""

# A quarta modalidade: o portal a separa de "Remoto" no proprio filtro
# (`model=presential-remote`). Veio de /vagas/tecnologia?page=2.
CARD_PRESENCIAL_OU_REMOTO = """<div class="list-grid-item rounded position-relative">
                        <a href="https://empregos.recrutei.com.br/vaga/digisystem/158985-consultor-funcional-tasy-assistencialfarmacia?has_bot=1" 
                    class="position-absolute w-100 h-100"></a>
                        <div class="grid-item-content p-3">
                <div class="grid-list-img mt-3">
                                            <a href="https://empregos.recrutei.com.br/vaga/digisystem/158985-consultor-funcional-tasy-assistencialfarmacia?has_bot=1">
                                                                        <img src="https://recrutei-web.s3.amazonaws.com/storage/files/logos/5p97eAOMjCHuQnd35hN7bhpEEwxRVZW9y9JlRZhq.jpg" alt="Logo Digisystem" class="img-fluid d-block" loading="lazy">
                                            </a>
                </div>
                <div class="grid-list-desc mt-3">
                    <h6 class="mb-1">
                                                    <a href="https://empregos.recrutei.com.br/vaga/digisystem/158985-consultor-funcional-tasy-assistencialfarmacia?has_bot=1"
                        class="job-title">Consultor Funcional Tasy Assistencial/Farmácia</a>
                                            </h6>
                                                    <p class="text-muted f-14 mb-1"><i class="mdi mdi-bank mr-2 text-primary-light"></i>Digisystem</p>
                                                                            <p class="text-muted mb-1"><i class="mdi mdi-map-marker text-primary-light"></i>
                                                                    São Paulo, SP, Brasil
                                                            </p>
                                                                                                    <p class="text-muted mb-1 small"><i class="fa fa-solid fa-comments-dollar text-primary-light"></i> Não informado</p>
                                            <p class="text-muted mb-1"><i
                        class="mdi mdi-clock-outline text-primary-light"></i>
                        <span class="small">
                            Publicada há 3 horas
                        </span>
                   </p>
                </div>
                <ul class="list-inline">
                    <li class="list-inline-item">
                                            </li>
                    <li class="list-inline-item ">
                        <span class="badge bg-primary text-white">Presencial ou Remoto</span>
                    </li>
                    <li class="list-inline-item">
                                            </li>
                </ul>
            </div>
            <div class="apply-button p-3 border-top bg-light text-right">
                                <a href="https://empregos.recrutei.com.br/vaga/digisystem/158985-consultor-funcional-tasy-assistencialfarmacia?has_bot=1" class="btn btn-sm btn-success mb-2">Candidate-se por <i class="fa fa-brands fa-whatsapp"></i> Whatsapp</a>
                                                    <a href="https://empregos.recrutei.com.br/vaga/digisystem/158985-consultor-funcional-tasy-assistencialfarmacia?has_bot=1" class="btn btn-sm btn-secondary">Candidatar-se</a>
                            </div>
        </div>"""

# Empresa anonima: link com UUID, e a pagina da vaga responde 404.
CARD_ANONIMO = """<div class="list-grid-item rounded position-relative">
                        <a href="https://empregos.recrutei.com.br/vaga/anonimo/429b74b6-fe77-47a8-95b0-fb4d6647683d" 
                    class="position-absolute w-100 h-100"></a>
                        <div class="grid-item-content p-3">
                <div class="grid-list-img mt-3">
                                            <a href="https://empregos.recrutei.com.br/vaga/anonimo/429b74b6-fe77-47a8-95b0-fb4d6647683d">
                                                                        <img src="https://empregos.recrutei.com.br/assets/images/company.png" alt="Logo de empresa anônima" class="img-fluid d-block" loading="lazy">
                                            </a>
                </div>
                <div class="grid-list-desc mt-3">
                    <h6 class="mb-1">
                                                    <a href="https://empregos.recrutei.com.br/vaga/anonimo/429b74b6-fe77-47a8-95b0-fb4d6647683d"
                        class="job-title">Desenvolvedor Pleno | PHP/Lavarel + Angular</a>
                                            </h6>
                                                    <p class="text-muted f-14 mb-1"><i class="mdi mdi-bank mr-2 text-primary-light"></i>Empresa anônima</p>
                                                                            <p class="text-muted mb-1"><i class="mdi mdi-map-marker text-primary-light"></i>
                                                                    São José dos Campos, SP, Brasil
                                                            </p>
                                                                                                    <p class="text-muted mb-1 small"><i class="fa fa-solid fa-comments-dollar text-primary-light"></i> Não informado</p>
                                            <p class="text-muted mb-1"><i
                        class="mdi mdi-clock-outline text-primary-light"></i>
                        <span class="small">
                            Publicada há 1 semana
                        </span>
                   </p>
                </div>
                <ul class="list-inline">
                    <li class="list-inline-item">
                                                <span class="badge bg-primary-light text-white">
                            Pessoa Jurídica
                        </span>
                                            </li>
                    <li class="list-inline-item ">
                        <span class="badge bg-primary text-white">Presencial</span>
                    </li>
                    <li class="list-inline-item">
                                            </li>
                </ul>
            </div>
            <div class="apply-button p-3 border-top bg-light text-right">
                                                    <a href="https://empregos.recrutei.com.br/vaga/anonimo/429b74b6-fe77-47a8-95b0-fb4d6647683d" class="btn btn-sm btn-secondary">Candidatar-se</a>
                            </div>
        </div>"""

# Os dois JSON-LD da pagina da vaga, na ordem em que ela os traz.
_LD_JOB_POSTING = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"ENGENHEIRO DE IA JR","description":"BM VAGAS em parceria com Bhaskara Consultoria em Inteligencia Artificial seleciona ENGENHEIRO DE IA JR para cidade de São José dos Campos.ResponsabilidadesDesenvolver e evoluir o Post4u, produto de IA para planejamento, criação e publicação de conteúdo em redes sociais.Implementar funcionalidades no frontend e backend, integrar APIs de IA, redes sociais, pagamentos e banco de dados, corrigir bugs e melhorar a experiência do usuário.Trabalhar a partir de prioridades e critérios de aceite, registrar decisões e evidências das entregas, escrever e executar testes proporcionais ao risco e acompanhar o produto em produção.Usar ferramentas de IA intensivamente para acelerar pesquisa, implementação, revisão e documentação, mantendo raciocínio crítico, segurança e qualidade técnica.RequisitosAprendizado rápido, abertura a feedback, curiosidade, autonomia, organização, pensamento crítico, uso prático de inteligência artificial, criação de prompts, programação com IA assistida (SDD, TDD), Python, RAG, tools, MCP, Git e GitHub, banco de dados SQL, PostgreSQL, integração com APIs externas, autenticação, testes automatizados, depuração de bugs, fundamentos de segurança de aplicações, leitura de documentação técnica, comunicação clara, atenção a detalhesSuperior Incompleto / cursandoDeterminado e gosta de desafiosHorário0","datePosted":"2026-08-23T01:58:05.000000Z","validThrough":"2026-10-23T01:58:05+00:00","employmentType":["FULL_TIME"],"jobBenefits":"","industry":"","skills":"TypeScript, JavaScript, React, HTML, CSS, APIs REST, programação com IA assistida (SDD, TDD), Python, RAG, tools, MCP, Git e GitHub, banco de dados SQL, PostgreSQL, integração com APIs externas, autenticação, testes automatizados, depuração de bugs, fundamentos de segurança de aplicações, leitura de documentação técnica, aprendizado rápido, autonomia, organização, pensamento crítico, comunicação clara, atenção a detalhes","workHours":"0","salaryCurrency":"BRL","hiringOrganization":{"@type":"Organization","name":"BM VAGAS","sameAs":"","logo":"https://d2bxzineatl84k.cloudfront.net/storage/files/logos/P0JDnmDSmhB2hDgjNgu9pOqPKgukqC25InMwmNms.png"},"jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"São José dos Campos","addressRegion":"SP","addressCountry":"Brasil"}}}</script>"""

_LD_BREADCRUMB = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"Início","item":"https://empregos.recrutei.com.br"},{"@type":"ListItem","position":2,"name":"SP","item":"https://empregos.recrutei.com.br/vagas/em/sp"},{"@type":"ListItem","position":3,"name":"ENGENHEIRO DE IA JR","item":"https://empregos.recrutei.com.br/vaga/bm-vagas/155283-engenheiro-de-ia-jr"}]}</script>"""

URL_REMOTA = f"{PORTAL_URL}/vaga/gex-corporation/158928-analista-de-atendimento"
TECNOLOGIA = f"{PORTAL_URL}/vagas/tecnologia"
DADOS = f"{PORTAL_URL}/vagas/dados"

_TITULO_RE = re.compile(r'(class="job-title">)[^<]*(</a>)')


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
    assert job.external_id == "158928"
    assert job.title == "Analista de Atendimento"
    assert job.company == "GEX Corporation"
    assert job.location == "Brasil"
    assert job.workplace_type == REMOTO
    assert job.seniority == ""  # o portal nao declara; o regex decide
    assert job.description == ""  # so vem do detalhe
    assert job.published_date == ""  # a do card e relativa; a exata vem do detalhe


def test_query_de_rastreio_sai_da_url():
    [job] = _parse(CARD_REMOTO)
    assert job.url == URL_REMOTA


def test_presencial_ou_remoto_e_hibrido_e_nao_remoto():
    [job] = _parse(CARD_PRESENCIAL_OU_REMOTO)
    assert job.workplace_type == HIBRIDO


def test_selo_de_regime_nao_vira_modalidade():
    # "Pessoa Jurídica" vem antes do selo "Remoto" no mesmo card.
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
    assert job.external_id == "158928"
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
    assert CATEGORIAS == ("tecnologia", "dados")


def test_fetch_ignora_termos_e_abre_so_vagas_de_entrada_uma_vez():
    junior = _com_titulo(CARD_REMOTO, "Desenvolvedor Júnior")
    pleno = _com_titulo(_com_id(CARD_REMOTO, "158929"), "Desenvolvedor Pleno")
    # A mesma vaga junior aparece nas duas categorias.
    sessao = _Sessao({TECNOLOGIA: _pagina(junior, pleno), DADOS: _pagina(junior),
                      URL_REMOTA: _detalhe()})
    fonte = _fonte(sessao)
    jobs = fonte.fetch(["termo ignorado"])

    assert [j.external_id for j in jobs] == ["158928"]
    assert jobs[0].seniority == "Júnior"
    assert jobs[0].description
    # A pagina da vaga junior abre uma vez so; a da pleno nunca.
    assert sessao.urls == [TECNOLOGIA, DADOS, URL_REMOTA]
    assert fonte.stats.raw_jobs == 1
    assert fonte.stats.requests_made == 3


def test_fetch_term_nao_e_usado():
    assert _fonte().fetch_term("qualquer") == []
