"""Coletor da GeekHunter (geekhunter.com).

Este portal e coletado de um jeito diferente dos outros, e a diferenca vem do
robots.txt dele:

    Disallow: /api/
    Disallow: /feeds/

As superficies de maquina estao explicitamente proibidas -- a tecnica usada na
Gupy e no Quero Vagas Tech, de consumir a API que o front chama, esta fora de
questao aqui. O proprio arquivo aponta o sitemap, que lista a pagina HTML de
cada vaga com dados estruturados JobPosting. Por isso nao existe busca por
termo: o caminho e sitemap -> filtro pelo slug -> pagina da vaga.

O robots.txt tambem tem `Disallow: /jobs`, e vale ser preciso sobre isso: regra
de robots.txt casa prefixo a partir da raiz, entao cobre `/jobs...` e nao
`/pt/<empresa>/jobs/<vaga>` -- que e justamente o formato que o sitemap lista.

O sitemap repete a mesma vaga em quatro idiomas; so as URLs `/pt/` entram.

Medido em 2026-09-15: 773 vagas em `/pt/`, das quais 44 trazem marca de nivel
de entrada no slug. A pagina de vaga traz titulo, empresa, local, data,
descricao, modalidade e um campo `skills` com as tecnologias declaradas.

**Limitacao conhecida:** o pre-filtro le so o titulo embutido na URL. Vaga
junior anunciada como "Desenvolvedor Front-end", sem marca de nivel no titulo,
passa batido. Buscar as 773 paginas resolveria e custaria uns 20 minutos de
requisicao com o delay de educacao.
"""

from __future__ import annotations

import json
import logging
import re

from ..models import NAO_INFORMADO, REMOTO, Job, normalize_workplace
from ..seniority import default_filter
from .base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://www.geekhunter.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

# Aceita os dois dominios: o portal responde em .com e .com.br com o mesmo
# sitemap, e cada um lista as vagas no proprio dominio.
_URL_VAGA_RE = re.compile(
    r"<loc>(https://www\.geekhunter\.com(?:\.br)?/pt/[^<]+/jobs/[^<]+)</loc>"
)
_LD_JSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)
# Rotulo de modalidade que a propria pagina mostra. Serve de complemento ao
# JobPosting: o schema so marca vaga remota (`TELECOMMUTE`) e nao distingue
# presencial de hibrida.
_CHIP_RE = re.compile(r">\s*(Remoto|H[íi]brido|Presencial)\s*<")

# Teto de seguranca: se um dia o sitemap crescer muito, a coleta nao vira uma
# varredura de horas. Hoje o filtro por slug devolve algo perto de 50.
MAX_VAGAS = 120


class GeekHunterSource(JobSource):
    name = "geekhunter"
    label = "GeekHunter"

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos: a superficie liberada nao tem busca por palavra."""
        if terms:
            logger.debug("[%s] termos ignorados; o caminho aqui e o sitemap",
                         self.name)

        urls = self._urls_de_entrada()
        jobs: list[Job] = []
        for url in urls:
            try:
                job = self._buscar_vaga(url)
            except Exception as exc:  # uma vaga quebrada nao derruba a coleta
                message = f"{self.name}/{url}: {exc}"
                logger.warning("Erro coletando %s", message)
                self.stats.errors.append(message)
                continue
            if job is not None:
                jobs.append(job)

        logger.info("[%s] sitemap -> %d candidatas -> %d vagas",
                    self.name, len(urls), len(jobs))
        self.stats.raw_jobs = len(jobs)
        self.stats.requests_made = self.session.request_count
        return jobs

    def fetch_term(self, term: str) -> list[Job]:
        """Nao usado: o portal nao expoe busca por termo na superficie liberada."""
        return []

    def _urls_de_entrada(self) -> list[str]:
        """URLs cujo slug ja denuncia nivel de entrada.

        O slug e o titulo da vaga com hifens, e `normalize` troca pontuacao por
        espaco -- entao o mesmo `seniority.yml` que filtra titulos serve aqui,
        sem vocabulario duplicado.
        """
        resposta = self.session.get(SITEMAP_URL)
        if resposta is None:
            return []

        filtro = default_filter()
        urls = []
        for url in _URL_VAGA_RE.findall(resposta.text):
            slug = url.rsplit("/jobs/", 1)[-1]
            if filtro.is_entry_level(slug):
                urls.append(url)

        if len(urls) > MAX_VAGAS:
            logger.warning("[%s] %d candidatas; coletando as primeiras %d",
                           self.name, len(urls), MAX_VAGAS)
        return urls[:MAX_VAGAS]

    def _buscar_vaga(self, url: str) -> Job | None:
        resposta = self.session.get(url)
        if resposta is None:
            return None
        return self._parse(resposta.text, url)

    def _parse(self, html: str, url: str) -> Job | None:
        dados = self._job_posting(html)
        if dados is None:
            return None

        titulo = (dados.get("title") or "").strip()
        identificador = self._identificador(dados, url)
        if not titulo or not identificador:
            return None

        return Job(
            source=self.name,
            external_id=identificador,
            title=titulo,
            company=(dados.get("hiringOrganization") or {}).get("name") or "",
            url=url,
            description=self._descricao(dados),
            location=self._local(dados),
            workplace_type=self._modalidade(dados, html),
            published_date=(dados.get("datePosted") or "")[:10],
        )

    @staticmethod
    def _job_posting(html: str) -> dict | None:
        """A pagina traz varios blocos ld+json; so um e a vaga."""
        for bruto in _LD_JSON_RE.findall(html):
            try:
                dados = json.loads(bruto)
            except json.JSONDecodeError:
                continue
            if isinstance(dados, dict) and dados.get("@type") == "JobPosting":
                return dados
        return None

    @staticmethod
    def _descricao(dados: dict) -> str:
        """Descricao da vaga, precedida das tecnologias que o portal declara.

        O `skills` do JobPosting e o equivalente das tags da ProgramaThor: sinal
        direto para o extrator de tecnologias e para o classificador. Vem como
        lista ou texto, conforme a vaga.
        """
        partes: list[str] = []
        skills = dados.get("skills")
        if isinstance(skills, list):
            skills = ", ".join(str(s).strip() for s in skills if str(s).strip())
        if isinstance(skills, str) and skills.strip():
            partes.append(f"Tecnologias: {skills.strip()}.")
        if dados.get("description"):
            partes.append(str(dados["description"]))
        return " ".join(partes)

    @staticmethod
    def _identificador(dados: dict, url: str) -> str:
        """`identifier` vem como PropertyValue; o slug e o plano B."""
        identificador = dados.get("identifier")
        if isinstance(identificador, dict):
            valor = identificador.get("value")
            if valor:
                return str(valor)
        elif identificador:
            return str(identificador)
        return url.rsplit("/jobs/", 1)[-1]

    @staticmethod
    def _local(dados: dict) -> str:
        locais = dados.get("jobLocation") or []
        if isinstance(locais, dict):
            locais = [locais]
        if not locais:
            return ""
        endereco = (locais[0] or {}).get("address") or {}
        partes = (endereco.get("addressLocality"), endereco.get("addressRegion"))
        return ", ".join(p for p in partes if p)

    @staticmethod
    def _modalidade(dados: dict, html: str) -> str:
        """`TELECOMMUTE` prova remoto; o resto vem do rotulo da pagina.

        O schema.org so tem marca para vaga remota, entao presencial e hibrida
        ficariam indistinguiveis sem o rotulo. Quando a pagina mostra mais de um
        rotulo, nenhum deles e desta vaga -- fica "nao informado".
        """
        if dados.get("jobLocationType") == "TELECOMMUTE":
            return REMOTO
        chips = set(_CHIP_RE.findall(html))
        if len(chips) == 1:
            return normalize_workplace(chips.pop())
        return NAO_INFORMADO
