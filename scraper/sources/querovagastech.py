"""Coletor do Quero Vagas Tech (querovagastech.com.br).

Agregador brasileiro de vagas tech. O robots.txt libera tudo (`Allow: /`, sem
uma linha de Disallow), e a API que o proprio front consome e publica, sem
autenticacao:

    GET /api/jobs?page=<n>&pageSize=100&sort=postedAt:desc   listagem
    GET /api/jobs/<id>                                       vaga com descricao

A API nao tem busca textual, entao esta fonte nao percorre os termos do
projeto: ela lista o acervo inteiro e pagina.

A listagem nao traz descricao, e o portao de relevancia e o extrator de
tecnologias dependem dela. Por isso ha um pre-filtro antes de buscar as
descricoes, e ele chama `filter_entry_level` -- a MESMA funcao do pipeline,
nao uma copia. O pipeline a reaplica depois; isto e so economia de requisicao.

Diferente do projeto de alerta de onde este codigo veio, aqui o pre-filtro e so
de nivel: este projeto analisa vagas de qualquer modalidade e local, entao nao
ha o que cortar por remoto ou cidade. Medido em 2026-09-15: 686 vagas listadas,
192 com nivel de entrada no titulo -- 192 requisicoes de descricao por coleta,
uns 5 minutos com o delay padrao.

**A senioridade declarada pelo portal e ignorada de proposito.** Numa medicao
de 741 vagas, 292 vinham como `Intern`, entre elas "Gerente de Infraestrutura de
TI - LATAM" e "Analista de Produtos de TI Pleno". Na de 2026-09-15, das 192 com
nivel de entrada no titulo, o portal chamava 4 de `Lead` e 4 de `Mid`. Isso
importa porque `filter_entry_level` respeita nivel declarado pela fonte e nem
consulta o titulo -- aceitar esse campo faria passar gerente e pleno. Aqui ele
fica vazio e quem decide e o regex sobre o titulo.

Parte do acervo vem do mesmo portal da Gupy que este projeto ja raspa direto
(65 das 192 na medicao acima); a deduplicacao por titulo+empresa colapsa essas.
O que o portal acrescenta e a curadoria manual dele, mais InfoJobs e Solides.

O envelope da listagem traz `isLimited` e `requiresAuthForMore`. Hoje os dois
vem `false` para cliente anonimo, mas os campos existem -- se um dia comecarem
a morder, a coleta avisa em log em vez de silenciosamente trazer 10 vagas.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from ..models import (
    HIBRIDO,
    NAO_INFORMADO,
    PRESENCIAL,
    REMOTO,
    Job,
    strip_html,
)
from ..seniority import filter_entry_level
from .base import JobSource

logger = logging.getLogger(__name__)

SITE_URL = "https://querovagastech.com.br"
API_URL = f"{SITE_URL}/api/jobs"

# A API limita a pagina a 100: pedir 200 devolve 100 do mesmo jeito.
PAGE_SIZE = 100
# Teto de seguranca. Hoje o acervo cabe em 7 paginas.
MAX_PAGINAS = 20

# O portal declara a modalidade no vocabulario dele; este e o de-para.
MODALIDADES = {
    "Remote": REMOTO,
    "Onsite": PRESENCIAL,
    "Hybrid": HIBRIDO,
    "Unknown": NAO_INFORMADO,
}


class QueroVagasTechSource(JobSource):
    name = "querovagastech"
    label = "Quero Vagas Tech"

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos: a API lista o acervo e pagina, sem busca textual."""
        if terms:
            logger.debug("[%s] termos ignorados; a API nao tem busca textual",
                         self.name)

        listadas = self._listar()
        candidatas = self._pre_filtrar(listadas)
        for job in candidatas:
            try:
                self._preencher_descricao(job)
            except Exception as exc:  # uma vaga nao derruba a coleta
                message = f"{self.name}/{job.external_id}: {exc}"
                logger.warning("Erro buscando descricao de %s", message)
                self.stats.errors.append(message)

        logger.info("[%s] %d listadas -> %d candidatas -> %d com descricao",
                    self.name, len(listadas), len(candidatas),
                    sum(1 for j in candidatas if j.description))
        self.stats.raw_jobs = len(candidatas)
        self.stats.requests_made = self.session.request_count
        return candidatas

    def fetch_term(self, term: str) -> list[Job]:
        """Nao usado: a API nao expoe busca por termo."""
        return []

    def _listar(self) -> list[Job]:
        jobs: list[Job] = []
        vistos = 0
        total = None

        for pagina in range(1, MAX_PAGINAS + 1):
            payload = self.session.get_json(API_URL, params={
                "page": pagina, "pageSize": PAGE_SIZE, "sort": "postedAt:desc",
            })
            if not payload:
                break

            if payload.get("isLimited") or payload.get("requiresAuthForMore"):
                logger.warning(
                    "[%s] o portal passou a limitar cliente anonimo "
                    "(isLimited=%s, requiresAuthForMore=%s, visivel=%s)",
                    self.name, payload.get("isLimited"),
                    payload.get("requiresAuthForMore"),
                    payload.get("anonymousVisibleLimit"),
                )

            itens = payload.get("items") or []
            if not itens:
                break

            vistos += len(itens)
            jobs.extend(j for j in (self._parse(i) for i in itens) if j is not None)

            total = payload.get("total") or total
            if len(itens) < PAGE_SIZE:
                break
            if isinstance(total, int) and vistos >= total:
                break

        return jobs

    def _pre_filtrar(self, jobs: list[Job]) -> list[Job]:
        """Corta o que o pipeline cortaria, para nao buscar descricao em vao.

        So nivel de entrada, e so quando a coleta pede nivel de entrada: com
        `--all-levels` o pipeline nao corta nada, entao aqui tambem nao.
        """
        if not self.settings.only_junior:
            return jobs
        return filter_entry_level(jobs)

    def _preencher_descricao(self, job: Job) -> None:
        payload = self.session.get_json(f"{API_URL}/{job.external_id}")
        if not payload:
            return
        # A descricao chega em texto puro na maioria das fontes agregadas, mas
        # algumas trazem HTML -- entao passa pelo mesmo limpador do modelo.
        job.description = strip_html(payload.get("description") or "")

    @staticmethod
    def _link(raw: dict, identificador: str) -> str:
        """Link da vaga, com a pagina do portal como reserva.

        Medido: 32 de 741 vagas nao trazem URL navegavel em `applyUrl` -- 31
        vem como `manual://jobs/<uuid>` e uma traz um endereco de e-mail, que e
        como aquela vaga recebe candidatura. Todas sao da curadoria manual.
        Sem reserva essas ficariam no CSV e na API com um link que nao abre; a
        pagina do portal existe para toda vaga e mostra como se candidatar.
        """
        candidatura = (raw.get("applyUrl") or "").strip()
        if urlsplit(candidatura).scheme in ("http", "https"):
            return candidatura
        return f"{SITE_URL}/vagas/{identificador}"

    def _parse(self, raw: dict) -> Job | None:
        identificador = raw.get("id")
        titulo = (raw.get("title") or "").strip()
        if not identificador or not titulo:
            return None

        return Job(
            source=self.name,
            external_id=str(identificador),
            title=titulo,
            company=raw.get("company") or "",
            url=self._link(raw, str(identificador)),
            location=raw.get("location") or "",
            workplace_type=MODALIDADES.get(raw.get("workMode"), NAO_INFORMADO),
            published_date=(raw.get("postedAt") or "")[:10],
            # `seniority` fica vazio de proposito: ver o docstring do modulo.
        )
