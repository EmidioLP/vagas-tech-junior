"""Coletor do LinkedIn Jobs pela API de convidado (sem login).

    GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
        ?keywords=<termo>&geoId=106057199&start=<n>

E o endpoint que o proprio site chama para carregar mais resultados na busca
publica. Devolve um fragmento HTML com 10 cards por chamada, e responde 200 ate
com o User-Agent do projeto -- nao exige navegador nem sessao.

**A localizacao precisa ser o geoId.** Passar `location=Brasil` (em portugues)
falha em silencio: a API responde 200 e devolve vagas dos Estados Unidos
("Brooklyn, NY", "San Francisco Bay Area"). `location=Brazil` em ingles filtra
quase tudo, mas o geoId e o unico que acertou 10 de 10 nos testes.

O card da busca **nao traz a descricao da vaga**, e a modalidade (presencial,
hibrido, remoto) so aparece escrita nela. Por isso, depois da busca, o coletor
pede a pagina de detalhe de cada vaga de entrada:

    GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>

So das vagas cujo titulo passa no filtro de senioridade (as outras o pipeline
descartaria), no maximo `Settings.linkedin_max_detalhes` por coleta, e parando
depois de `FALHAS_SEGUIDAS_MAX` falhas seguidas (sinal de bloqueio). A falha no
detalhe nao conta como falha da fonte: a vaga ja foi listada e segue sem
descricao, como antes.

**O `robots.txt` do LinkedIn proibe `/jobs-guest/`** (e `Disallow: /` para
qualquer robo), tanto a busca quanto o detalhe. A busca do detalhe foi uma
decisao consciente do mantenedor, registrada em `docs/limitacoes.md`.

Esta e a fonte com maior chance de passar a bloquear no futuro. Se isso
acontecer, `PoliteSession.get` devolve None, o coletor devolve o que tiver e a
coleta das outras fontes segue normalmente.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..models import NAO_INFORMADO, REMOTO, Job, normalize
from ..seniority import default_filter
from .base import JobSource

logger = logging.getLogger(__name__)

API_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

# geoId do Brasil no LinkedIn. Ver o docstring: o nome do pais em portugues
# nao filtra nada e traz vagas dos EUA sem qualquer aviso.
GEO_ID_BRASIL = "106057199"

DETALHE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"

RESULTADOS_POR_PAGINA = 10

# Falhas seguidas no detalhe que indicam bloqueio: dali em diante, para de pedir.
FALHAS_SEGUIDAS_MAX = 3

_ID_RE = re.compile(r"(\d+)$")
_WS_RE = re.compile(r"\s+")


class LinkedInSource(JobSource):
    name = "linkedin"
    label = "LinkedIn Jobs"

    def fetch(self, terms: list[str]) -> list[Job]:
        """Busca todos os termos e depois completa a descricao das vagas de entrada."""
        jobs = super().fetch(terms)
        self._completar_descricoes(jobs)
        return jobs

    def _completar_descricoes(self, jobs: list[Job]) -> None:
        # A mesma vaga volta em varios termos: um detalhe por id.
        por_id: dict[str, list[Job]] = {}
        for job in jobs:
            por_id.setdefault(job.external_id, []).append(job)

        entrada = default_filter()
        ids = [i for i, grupo in por_id.items() if entrada.is_entry_level(grupo[0].title)]
        teto = max(self.settings.linkedin_max_detalhes, 0)
        if len(ids) > teto:
            logger.info("[linkedin] %d vagas de entrada, detalhe so das %d primeiras",
                        len(ids), teto)
        ids = ids[:teto]

        obtidas = falhas = seguidas = 0
        for external_id in ids:
            descricao = self._buscar_descricao(external_id)
            if descricao is None:
                falhas += 1
                seguidas += 1
                if seguidas >= FALHAS_SEGUIDAS_MAX:
                    logger.warning("[linkedin] %d falhas seguidas no detalhe; "
                                   "parando (possivel bloqueio)", seguidas)
                    break
                continue
            seguidas = 0
            obtidas += 1
            for job in por_id[external_id]:
                job.description = descricao
        logger.info("[linkedin] detalhe: %d descricoes obtidas, %d falhas, de %d pedidas",
                    obtidas, falhas, len(ids))

    def _buscar_descricao(self, external_id: str) -> str | None:
        """Descricao da pagina de detalhe; None se a requisicao ou o parse falhar."""
        response = self.session.get(DETALHE_URL.format(id=external_id), conta_falha=False)
        if response is None:
            return None
        return self._parse_descricao(response.text)

    @staticmethod
    def _parse_descricao(html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        corpo = soup.select_one("div.show-more-less-html__markup")
        if corpo is None:
            return None
        texto = _WS_RE.sub(" ", corpo.get_text(" ", strip=True)).strip()
        return texto or None

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()

        for page in range(self.settings.max_pages_per_term):
            response = self.session.get(
                API_URL,
                params={
                    "keywords": term,
                    "geoId": GEO_ID_BRASIL,
                    "start": page * RESULTADOS_POR_PAGINA,
                },
            )
            if response is None:
                break

            batch = self._parse_page(response.text, term)
            if not batch:
                break

            novos = 0
            for job in batch:
                if job.external_id in seen:
                    continue
                seen.add(job.external_id)
                jobs.append(job)
                novos += 1

            if novos == 0:
                break  # a API comecou a repetir resultados

        return jobs

    def _parse_page(self, html: str, term: str) -> list[Job]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[Job] = []
        for card in soup.select("div.base-card"):
            job = self._parse_card(card, term)
            if job is not None:
                jobs.append(job)
        return jobs

    def _parse_card(self, card, term: str) -> Job | None:
        urn = card.get("data-entity-urn") or ""
        match = _ID_RE.search(urn)
        title = self._text(card.select_one("h3.base-search-card__title"))
        if match is None or not title:
            return None

        link = card.select_one("a.base-card__full-link")
        url = (link.get("href") or "").split("?")[0] if link else ""

        momento = card.select_one("time")
        publicada = (momento.get("datetime") or "") if momento else ""

        location = self._text(card.select_one("span.job-search-card__location"))

        return Job(
            source=self.name,
            external_id=match.group(1),
            title=title,
            company=self._text(card.select_one("h4.base-search-card__subtitle")),
            url=url,
            description="",  # o card nao traz; `fetch` completa pelo detalhe
            location=location,
            workplace_type=self._modalidade(location),
            published_date=publicada[:10],
            search_term=term,
        )

    @staticmethod
    def _modalidade(location: str) -> str:
        """So afirma remoto quando o proprio texto do local diz isso.

        O card nao tem campo de modalidade; presencial e hibrido sao
        indistinguiveis aqui, entao ficam como nao informado em vez de chute.
        O pipeline tenta de novo pelo texto da descricao (`scraper/modalidade.py`).
        """
        texto = normalize(location)
        if "remoto" in texto or "remote" in texto:
            return REMOTO
        return NAO_INFORMADO

    @staticmethod
    def _text(node) -> str:
        if node is None:
            return ""
        return _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()
