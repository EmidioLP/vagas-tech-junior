"""Coletor do Solides (vagas.solides.com.br).

O portal e uma SPA; o que serve e a API JSON que o proprio front chama,
publica e sem autenticacao, descoberta inspecionando a aba Network:

    GET https://apigw.solides.com.br/jobs/v3/portal-vacancies?title=<termo>&page=<n>&take=<n>

O robots.txt de `vagas.solides.com.br` e de `solides.jobs` libera tudo
(`User-agent: * / Allow: /`, sem uma linha de Disallow); o `apigw` nao serve
robots.txt. O User-Agent identificavel do projeto e aceito -- nao e preciso
fingir navegador.

Parametros, mapeados por tentativa contra a API:
  `title` busca textual, e o UNICO filtro que funciona: `search`, `q`,
        `keyword`, `term` e `name` sao aceitos e silenciosamente ignorados
        (devolvem o acervo inteiro). Casa por palavra, sem acento e com
        abreviacao -- `title=devops junior` traz "Analista DevOps Jr" --, mas
        olha so o titulo: a descricao nao entra na busca.
  `page` paginacao, 1-based. Pagina depois da ultima devolve lista vazia.
  `take` tamanho da pagina, **maximo 25**: acima disso a API responde HTTP 400
        ("take deve ser menos ou igual a 25"). Sem `take` o default e 10.
        `limit`, `perPage` e `pageSize` sao ignorados.

Particularidades que o codigo trata:

- O Solides e um SaaS de RH: o acervo tem ~73 mil vagas de todas as areas
  (RH, logistica, industria). Quem corta o que nao e tecnologia e o portao de
  relevancia do projeto, nao a fonte.
- `id` vem inteiro OU alfanumerico curto ("vgV6ou5UrL") -- medidos 5 de 40 nao
  numericos. Por isso sempre `str()`.
- A modalidade vem afirmada em `jobType` (presencial/hibrido/remoto), preenchida
  em 200 de 200 vagas medidas. `homeOffice` e uma flag separada e legada: veio
  `True` em so 2 de 200, enquanto 18 tinham `jobType=remoto` -- serve de reserva,
  nunca de fonte principal.
- **`showModality` e ignorado de proposito.** Ele veio `false` em 7 de 40 vagas,
  sempre COM `jobType` preenchido: o campo controla a exibicao no portal, nao a
  validade do dado. A coleta grava a modalidade nas duas situacoes.
- **A senioridade declarada pelo portal e ignorada**, pela mesma razao do Quero
  Vagas Tech: numa medicao de 6 vagas de "desenvolvedor junior", 3 vinham com
  `seniority` vazio e uma vaga chamada "vaga testre" vinha como `Junior`; outra,
  "Analista Full Stack Junior / Pleno", vinha como `['Pleno', 'Junior']`. Isso
  importa porque `filter_entry_level` respeita nivel declarado pela fonte e nem
  consulta o titulo. Aqui ele fica vazio e quem decide e o regex sobre o titulo.
- `currentState` veio "em_andamento" em 200 de 200: a listagem ja traz so vagas
  abertas, diferente da ProgramaThor. A guarda existe mesmo assim, barata, para
  que vaga encerrada nao entre sem ninguem perceber.
- **O acervo tem muita vaga antiga que o portal segue chamando de aberta.** Nas
  39 vagas finais de 22/09/2026, a idade mediana era de 235 dias e 14 passavam
  de um ano (a mais velha, de 16/05/2019). Quatro traziam "Banco de Talentos" no
  titulo -- anuncio perene que a empresa nunca encerra. A coleta NAO filtra por
  idade: grava a `createdAt` que o portal publica e deixa o vies registrado em
  `docs/limitacoes.md`, como se faz com os demais portais.

Medido em 2026-09-22 com os 13 termos do projeto: 13 requisicoes, 40 vagas
unicas, todas com descricao, empresa, link e data. Todo termo coube em uma
pagina de 25.

Parte deste acervo ja chegava ao projeto de forma indireta, pela curadoria do
Quero Vagas Tech; a deduplicacao por titulo+empresa colapsa a sobreposicao.
"""

from __future__ import annotations

import logging

from ..models import Job, normalize_workplace
from .base import JobSource

logger = logging.getLogger(__name__)

SITE_URL = "https://vagas.solides.com.br"
API_URL = "https://apigw.solides.com.br/jobs/v3/portal-vacancies"

# Acima de 25 a API responde HTTP 400.
MAX_TAKE = 25
# Unico `currentState` observado na listagem; o resto e vaga que nao esta aberta.
ABERTA = "em_andamento"


class SolidesSource(JobSource):
    name = "solides"
    label = "Solides (vagas.solides.com.br)"

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        vistos: set[str] = set()
        take = min(self.settings.page_size, MAX_TAKE)

        for pagina in range(1, self.settings.max_pages_per_term + 1):
            payload = self.session.get_json(
                API_URL, params={"title": term, "page": pagina, "take": take},
            )
            if not payload:
                break

            # O envelope aninha: {"data": {"data": [...], "totalPages": n}}.
            envelope = payload.get("data") or {}
            batch = envelope.get("data") or []
            if not batch:
                break  # fim real da paginacao

            novas_na_pagina = 0
            for raw in batch:
                job = self._parse(raw, term)
                if job is None or job.external_id in vistos:
                    continue
                vistos.add(job.external_id)
                jobs.append(job)
                novas_na_pagina += 1

            if len(batch) < take:
                break  # ultima pagina
            total_pages = envelope.get("totalPages")
            if isinstance(total_pages, int) and pagina >= total_pages:
                break
            if novas_na_pagina == 0:
                break  # API repetindo resultados; evita loop inutil

        return jobs

    def _parse(self, raw: dict, term: str) -> Job | None:
        identificador = raw.get("id")
        titulo = (raw.get("title") or "").strip()
        if identificador is None or identificador == "" or not titulo:
            return None

        estado = raw.get("currentState")
        if estado and estado != ABERTA:
            logger.debug("[%s] vaga %s ignorada: currentState=%s",
                         self.name, identificador, estado)
            return None

        return Job(
            source=self.name,
            external_id=str(identificador),
            title=titulo,
            # Vem "Empresa confidencial" quando `isHiddenJob`; e o que o portal
            # publica, entao e o que se grava.
            company=raw.get("companyName") or "",
            url=self._link(raw, str(identificador)),
            description=raw.get("description") or "",
            location=self._local(raw),
            workplace_type=self._modalidade(raw),
            published_date=(raw.get("createdAt") or "")[:10],
            search_term=term,
            # `seniority` fica vazio de proposito: ver o docstring do modulo.
        )

    @staticmethod
    def _link(raw: dict, identificador: str) -> str:
        """Link da vaga, com a pagina do portal como reserva.

        `redirectLink` veio em 200 de 200 vagas medidas, sempre https. A reserva
        existe para nao gravar link vazio, que a checagem de qualidade acusa.
        """
        link = (raw.get("redirectLink") or "").strip()
        return link or f"{SITE_URL}/vaga/{identificador}"

    @staticmethod
    def _local(raw: dict) -> str:
        """Cidade e UF. Os dois objetos existem sempre, os campos nem sempre."""
        cidade = ((raw.get("city") or {}).get("name") or "").strip()
        estado = raw.get("state") or {}
        uf = (estado.get("code") or estado.get("name") or "").strip()
        return ", ".join(parte for parte in (cidade, uf) if parte)

    @staticmethod
    def _modalidade(raw: dict) -> str:
        """`jobType` manda; `homeOffice` so cobre quando ele nao vem.

        `showModality` NAO entra na decisao -- ver o docstring do modulo.
        """
        return normalize_workplace(
            raw.get("jobType") or ("remoto" if raw.get("homeOffice") else "")
        )
