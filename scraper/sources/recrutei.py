"""Coletor do Recrutei Empregos (empregos.recrutei.com.br).

Agregador das vagas publicadas pelas consultorias de R&S que usam a plataforma
Recrutei. As listagens sao renderizadas no servidor -- os cards ja vem no HTML,
como no Vagas.com --, entao `requests` + BeautifulSoup bastam, e o User-Agent do
projeto passa sem 403. Porta do coletor do projeto irmao vagas-remotas-alerta;
la a superficie e a de remotas mais a de RN e Fortaleza, aqui e nacional.

**Esta fonte nao tem busca por termo, e o `robots.txt` e quem decide isso.** O
formulario do portal e `GET /busca?keyword=<termo>`, e o `robots.txt` bloqueia
exatamente essa forma:

    Disallow: /api/  /recrutest/  /candidato/  /empresa/  /r/knowledge/
    Disallow: /*?*keyword=*
    Disallow: /*?*q=*

As listagens por categoria (`/vagas/<categoria>?page=N`) nao sao bloqueadas.
Por isso `fetch_term` devolve `[]` e o `fetch` daqui e reescrito, como na
GeekHunter, no lugar de fingir uma busca textual que o portal proibe.

Categorias medidas em 24/09/2026 (vagas; com nivel de entrada no titulo):

    tecnologia 521; 47    dados     208; 21    produto 202; 15
    ti         153; 14    design     83; 13    suporte  10;  2
    seguranca   18;  1    erp        15;  0

Todas as de entrada de `ti`, `suporte`, `seguranca` e `erp` ja estavam em
`tecnologia`. Fora dela, `produto` e `design` so trouxeram marketing,
arquitetura e direcao de arte; `dados` trouxe um estagio de dados que nao
aparece em `tecnologia`. Dai `CATEGORIAS` -- a taxonomia do portal e barulhenta
("Vendedor Interno Junior" aparece em tecnologia), e quem decide e o portao
tech do pipeline.

**A descricao e buscada vaga a vaga, porque o card nao tem nenhuma.** O card
mostra titulo, empresa, local, salario, data e selos -- e so. Isso derruba o
portao tech: na coleta de 24/09/2026, 8 das 29 vagas finais so passaram em
`is_tech` pela descricao ("Analista de Solucao de Dados Junior", "Analista de
IAM (Gestao de Acessos) Junior"). A pagina de cada vaga traz um `JobPosting`
em JSON-LD com `description` e `datePosted` (ISO, mais exato que o "ha 1 mes" do
card). O pre-filtro de nivel usa a MESMA funcao do pipeline, e so as que passam
tem a pagina aberta -- sem `is_tech` no titulo, pelo motivo acima. A falha no
detalhe nao conta como falha da fonte (`conta_falha=False`), como no LinkedIn:
a vaga ja foi listada e segue sem descricao.

Os termos de uso (`https://api.recrutei.com.br/files/termos.pdf`) sao dirigidos
ao candidato e nao proibem crawler nem reproducao de conteudo; a descricao sai
do JSON-LD, marcacao que o portal publica justamente para ser sindicada.

Armadilhas, todas medidas no irmao e tratadas abaixo:

  - **"Presencial ou Remoto" nao e remoto.** O portal distingue quatro
    modalidades no filtro lateral e deixa `presential-remote` fora da propria
    listagem de home office. `normalize_workplace` leria o selo como REMOTO,
    porque procura "remoto" dentro da string -- dai o de-para explicito.
  - Pagina alem do fim responde 200 com zero card (`?page=99`), e nao repete a
    primeira -- por isso a parada por pagina vazia e confiavel.
  - O link do card vem com query de rastreio (`?has_bot=1`,
    `?utm_source=...`), que e descartada: o id da vaga esta no caminho, e a
    pagina responde 200 sem a query.
  - O portal nao declara nivel nenhum no card, entao `job.seniority` fica vazio
    e quem decide e o regex de `seniority.py`.

**Vaga de empresa anonima e descartada** (medido aqui, 24/09/2026; o irmao nao
a viu nas listagens dele). O card vem com "Empresa anonima" e link
`/vaga/anonimo/<uuid>`, e essa pagina responde 404 para qualquer cliente, com
o User-Agent do projeto ou de navegador, com ou sem `?has_bot=1`. Sem pagina
nao ha descricao, e o link gravado levaria o leitor do dashboard a um 404. A
contagem sai no log.
"""

from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from ..models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO, Job, normalize, strip_html
from ..seniority import filter_entry_level
from .base import JobSource

logger = logging.getLogger(__name__)

PORTAL_URL = "https://empregos.recrutei.com.br"
# Ver o docstring do modulo para a medicao que escolheu estas duas.
CATEGORIAS = ("tecnologia", "dados")

# 12 cards por pagina, medido em todas as categorias.
PAGE_SIZE = 12
# Teto de seguranca: `tecnologia` coube em 45 paginas.
MAX_PAGINAS = 80

MODALIDADES = {
    "remoto": REMOTO,
    "presencial": PRESENCIAL,
    "hibrido": HIBRIDO,
    "presencial ou remoto": HIBRIDO,
}

# `/vaga/<empresa>/<id>-<slug>`: o id da vaga e o numero antes do primeiro
# hifen do ultimo segmento. A vaga de empresa anonima vem como
# `/vaga/anonimo/<uuid>` e nao casa -- de proposito, ver o docstring do modulo.
_ID_NO_CAMINHO = re.compile(r"/vaga/[^/]+/(\d+)-")
_WS_RE = re.compile(r"\s+")


def _texto(node) -> str:
    if node is None:
        return ""
    return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()


class RecruteiSource(JobSource):
    name = "recrutei"
    label = "Recrutei Empregos"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._anonimas = 0  # cards descartados na coleta, so para o log

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos: o `robots.txt` fecha a busca por palavra-chave."""
        if terms:
            logger.debug("[%s] termos ignorados; o robots.txt bloqueia "
                         "/busca?keyword=", self.name)

        listadas: list[Job] = []
        for categoria in CATEGORIAS:
            listadas.extend(self._categoria(categoria))

        # Uma vaga de dados aparece em `tecnologia` e em `dados`; sem isto a
        # pagina dela seria aberta duas vezes.
        unicas = self._sem_repetidas(listadas)
        # Mesma funcao do pipeline: se a regra mudar la, muda aqui junto.
        candidatas = filter_entry_level(unicas)

        for job in candidatas:
            try:
                self._preencher_detalhe(job)
            except Exception as exc:  # uma vaga nao derruba a coleta
                message = f"{self.name}/{job.external_id}: {exc}"
                logger.warning("Erro buscando descricao de %s", message)
                self.stats.errors.append(message)

        logger.info("[%s] %d listadas (%d anonimas descartadas) -> %d candidatas "
                    "-> %d com descricao", self.name, len(unicas), self._anonimas,
                    len(candidatas), sum(1 for j in candidatas if j.description))
        self.stats.raw_jobs = len(candidatas)
        self.stats.requests_made = self.session.request_count
        return candidatas

    def fetch_term(self, term: str) -> list[Job]:
        """Nao usado: o `robots.txt` bloqueia `/busca?keyword=`."""
        return []

    def _categoria(self, categoria: str) -> list[Job]:
        """Uma listagem inteira, com a falha dela isolada das outras."""
        try:
            jobs = self._listar(f"{PORTAL_URL}/vagas/{categoria}")
        except Exception as exc:  # o mesmo isolamento que `JobSource.fetch` da
            message = f"{self.name}/{categoria}: {exc}"
            logger.warning("Erro coletando %s", message)
            self.stats.errors.append(message)
            return []
        logger.info("[%s] '%s' -> %d vagas", self.name, categoria, len(jobs))
        return jobs

    def _listar(self, base: str) -> list[Job]:
        jobs: list[Job] = []
        vistos: set[str] = set()

        for pagina in range(1, MAX_PAGINAS + 1):
            url = base if pagina == 1 else f"{base}?page={pagina}"
            resposta = self.session.get(url)
            if resposta is None:
                break

            # Os cortes olham o card, nao a vaga parseada: uma pagina com um card
            # anonimo (descartado em `_parse`) tem 12 cards e 11 vagas, e contar
            # vagas encerrava a listagem ali -- `tecnologia` parava em 131 de 521.
            cards = self._cards(resposta.text)
            novos = 0
            for card in cards:
                link = card.select_one("a.job-title")
                href = ((link.get("href") or "") if link else "").split("?")[0]
                if href in vistos:
                    continue
                vistos.add(href)
                novos += 1
                job = self._parse(card)
                if job is not None:
                    jobs.append(job)

            if novos == 0:
                break  # pagina vazia (`?page=99`) ou repetida
            if len(cards) < PAGE_SIZE:
                break  # ultima pagina

        return jobs

    @staticmethod
    def _cards(html: str) -> list:
        return BeautifulSoup(html, "html.parser").select("div.list-grid-item")

    def _parse_page(self, html: str) -> list[Job]:
        return [job for job in (self._parse(c) for c in self._cards(html))
                if job is not None]

    def _parse(self, card) -> Job | None:
        link = card.select_one("a.job-title")
        titulo = _texto(link)
        href = (link.get("href") or "") if link else ""
        # A query e so rastreio (`?has_bot=1`, `?utm_source=...`); o id esta no
        # caminho, e a pagina responde 200 sem ela.
        endereco = href.split("?")[0]
        if "/vaga/anonimo/" in endereco:
            self._anonimas += 1
            return None
        achado = _ID_NO_CAMINHO.search(endereco)
        if not titulo or not achado:
            return None

        return Job(
            source=self.name,
            external_id=achado.group(1),
            title=titulo,
            company=self._campo(card, "mdi-bank"),
            url=endereco,
            location=self._campo(card, "mdi-map-marker"),
            workplace_type=self._modalidade(card),
            # A data do card e relativa ("ha 1 mes"); a exata vem do detalhe.
        )

    @staticmethod
    def _campo(card, icone: str) -> str:
        """Empresa e local sao `<p>` irmaos, distinguidos pelo icone."""
        for paragrafo in card.select("div.grid-list-desc p"):
            if paragrafo.select_one(f"i.{icone}"):
                return _texto(paragrafo)
        return ""

    @staticmethod
    def _modalidade(card) -> str:
        """O primeiro selo que e modalidade; os outros sao regime e PCD.

        Medido no irmao, nas 134 remotas: cada card traz um selo de regime
        ("CLT", "Pessoa Juridica", "Cooperado", "CLT ou PJ", "Estagio") antes
        do selo de modalidade, e 5 deles vieram so com a modalidade.
        """
        for selo in card.select("span.badge"):
            modalidade = MODALIDADES.get(normalize(_texto(selo)))
            if modalidade:
                return modalidade
        return NAO_INFORMADO

    @staticmethod
    def _sem_repetidas(jobs: list[Job]) -> list[Job]:
        vistos: set[str] = set()
        unicas: list[Job] = []
        for job in jobs:
            if job.external_id in vistos:
                continue
            vistos.add(job.external_id)
            unicas.append(job)
        return unicas

    def _preencher_detalhe(self, job: Job) -> None:
        """Descricao e data exata, do `JobPosting` em JSON-LD da pagina."""
        resposta = self.session.get(job.url, conta_falha=False)
        if resposta is None:
            return

        dados = self._job_posting(resposta.text)
        if dados is None:
            logger.debug("[%s] %s sem JobPosting na pagina", self.name, job.url)
            return

        job.description = strip_html(dados.get("description") or "")
        job.published_date = (dados.get("datePosted") or "")[:10]

    @staticmethod
    def _job_posting(html: str) -> dict | None:
        """A pagina tambem traz um `BreadcrumbList` no mesmo formato."""
        sopa = BeautifulSoup(html, "html.parser")
        for script in sopa.select('script[type="application/ld+json"]'):
            try:
                dados = json.loads(script.string or "")
            except (ValueError, TypeError):
                continue
            if isinstance(dados, dict) and dados.get("@type") == "JobPosting":
                return dados
        return None
