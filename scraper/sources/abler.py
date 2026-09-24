"""Coletor do Abler (candidatos.abler.com.br).

O Abler e um ATS: as empresas clientes publicam as vagas e o portal de
candidatos as reune. A API que o front usa para listar vagas fica fechada para
quem nao e o proprio portal:

    GET https://hulk-smash.abler.com.br/api/candidate/v2/vacancies
    -> 403 {"code": "ORIGIN_NOT_ALLOWED", "message": "Access with your company
       user integration token or from candidates or ats portals."}

Forjar o cabecalho `Origin` passaria, mas seria contornar um bloqueio escrito.
O `robots.txt` (`User-agent: * / Allow: /`) aponta o `sitemap.xml`, e o caminho
aqui e o mesmo da GeekHunter: sitemap -> filtro pelo slug -> pagina da vaga.
Porta do coletor do projeto irmao vagas-remotas-alerta, sem o corte de idade e
de local que la existe.

Medido em 24/09/2026:

  - o sitemap tem 3,5 MB e 13.787 vagas, cada uma com `<lastmod>`;
  - nivel de entrada **e** tecnologia no titulo do slug deixam 94 candidatas.
    So o nivel de entrada deixaria perto de 900 paginas (uns 25 minutos);
  - **nao ha corte por `lastmod`**, e isso e deliberado: 8 candidatas com
    `lastmod` de 428 a 751 dias abertas uma a uma vieram todas com
    `status: "Em andamento"`. O sitemap nao guarda vaga fechada, guarda vaga
    perene -- o mesmo vies do Solides, registrado em `docs/limitacoes.md`;
  - a pagina e Nuxt renderizada no servidor, com a vaga inteira em
    `window.__NUXT__` -- um literal JavaScript, nao JSON (ver `_ler_nuxt`). Cada
    pagina tem ~1,3 MB, entao a coleta baixa ~120 MB;
  - a descricao vem em HTML; `skills` veio vazio e os requisitos `None` nas
    paginas medidas, entao so a descricao entra;
  - `levelOfInterests` NAO e confiavel (medido no irmao): "Analista" numa vaga
    Junior, "Especialista" em "Tecnico de informatica JR". Fica fora de
    `job.seniority`, e o titulo decide.

**Empresa oculta:** quando a empresa marca `hideCompany`, o nome dela vem no
dado mesmo assim. O coletor o descarta: a escolha de nao aparecer e dela. A
empresa fica vazia, e nao "Empresa confidencial" -- com o rotulo, duas vagas
ocultas de mesmo titulo seriam fundidas pela deduplicacao por titulo+empresa.

**Limitacao conhecida:** o pre-filtro le so o titulo embutido na URL. Vaga de
entrada sem sinal de tecnologia no titulo passa batida, como na GeekHunter.
"""

from __future__ import annotations

import json
import logging
import re

from ..classifier import default_classifier
from ..models import HIBRIDO, NAO_INFORMADO, PRESENCIAL, REMOTO, Job, strip_html
from ..seniority import default_filter
from .base import JobSource

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://candidatos.abler.com.br/sitemap.xml"

_URL_VAGA_RE = re.compile(
    r"<loc>(https://candidatos\.abler\.com\.br/vagas/([^<]+))</loc>"
)
# O slug termina num numero que NAO e o id da vaga (slug 637999, vaga 393184).
_SUFIXO_RE = re.compile(r"-\d+$")
_NUXT_RE = re.compile(r"window\.__NUXT__=\(function\(([^)]*)\)\{")

MODALIDADES = {
    "remoto": REMOTO,
    "hibrida": HIBRIDO,
    "hibrido": HIBRIDO,
    "presencial": PRESENCIAL,
}

# Teto de seguranca, como na GeekHunter. Hoje o filtro devolve 94.
MAX_VAGAS = 150


class AblerSource(JobSource):
    name = "abler"
    label = "Abler"

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos: sem a API, nao ha busca por palavra."""
        if terms:
            logger.debug("[%s] termos ignorados; o caminho aqui e o sitemap",
                         self.name)

        resposta = self.session.get(SITEMAP_URL)
        urls = self._candidatas(resposta.text) if resposta is not None else []

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
        """Nao usado: o caminho aqui e o sitemap."""
        return []

    def _candidatas(self, sitemap: str) -> list[str]:
        """URLs que o pipeline nao descartaria pelo que o slug ja diz.

        As funcoes sao as do pipeline, de proposito: se a regra mudar la, muda
        aqui junto. O pipeline reaplica as duas com o titulo verdadeiro.
        """
        entrada, clf = default_filter(), default_classifier()
        urls = []
        for url, slug in _URL_VAGA_RE.findall(sitemap):
            titulo = _SUFIXO_RE.sub("", slug)
            if entrada.is_entry_level(titulo) and clf.is_tech(titulo):
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
        vaga = _ler_vaga(html)
        if vaga is None:
            logger.debug("[%s] %s sem objeto de vaga na pagina", self.name, url)
            return None

        titulo = (vaga.get("title") or "").strip()
        identificador = vaga.get("id")
        if not titulo or not identificador:
            return None

        endereco = vaga.get("address") or {}
        local = ", ".join(p for p in ((endereco.get("cityName") or "").strip(),
                                      (endereco.get("stateAbbr") or "").strip()) if p)

        return Job(
            source=self.name,
            external_id=str(identificador),
            title=titulo,
            company="" if vaga.get("hideCompany") else (vaga.get("companyName") or ""),
            url=url,
            description=strip_html(vaga.get("description") or ""),
            location=local,
            workplace_type=self._modalidade(vaga.get("workTypes")),
            published_date=(vaga.get("publishedAt") or "")[:10],
            # `levelOfInterests` fica de fora: ver o docstring do modulo.
        )

    @staticmethod
    def _modalidade(tipos) -> str:
        """Um valor so e a modalidade; nenhum, ou mais de um, nao e prova.

        Medido no irmao: `workTypes` veio preenchido em 40 de 40 paginas, sempre
        com um valor so (34 `presencial`, 4 `remoto`, 2 `hibrida`).
        """
        ids = {(t or {}).get("id") for t in (tipos or []) if isinstance(t, dict)}
        ids.discard(None)
        if len(ids) != 1:
            return NAO_INFORMADO
        return MODALIDADES.get(ids.pop(), NAO_INFORMADO)


def _ler_vaga(html: str) -> dict | None:
    """O objeto `vacancy` de dentro do `window.__NUXT__`, ja como dict."""
    estado = _ler_nuxt(html)
    if estado is None:
        return None
    return _procurar_vaga(estado)


def _procurar_vaga(no) -> dict | None:
    """O `vacancy` que tem titulo: a pagina tambem traz um `vacancy` vazio."""
    if isinstance(no, dict):
        vaga = no.get("vacancy")
        if isinstance(vaga, dict) and vaga.get("title"):
            return vaga
        for valor in no.values():
            achada = _procurar_vaga(valor)
            if achada is not None:
                return achada
    elif isinstance(no, list):
        for valor in no:
            achada = _procurar_vaga(valor)
            if achada is not None:
                return achada
    return None


def _ler_nuxt(html: str):
    """Le o `window.__NUXT__=(function(a,b,...){return {...}}(null,false,...))`.

    O Nuxt troca os valores repetidos por parametros da funcao, e o que cada
    letra significa muda de pagina para pagina. Por isso os parametros sao
    ligados aos argumentos da chamada antes de ler o objeto.
    """
    cabecalho = _NUXT_RE.search(html)
    if cabecalho is None:
        return None
    fim = html.find("</script>", cabecalho.end())
    corpo = html[cabecalho.end():fim if fim >= 0 else len(html)].rstrip()

    chamada = corpo.rfind("}(")
    if not corpo.startswith("return ") or chamada < 0 or not corpo.endswith("));"):
        return None
    try:
        argumentos = json.loads("[" + corpo[chamada + 2:-3] + "]")
    except json.JSONDecodeError:
        return None
    nomes = [p.strip() for p in cabecalho.group(1).split(",") if p.strip()]
    variaveis = dict(zip(nomes, argumentos))

    try:
        valor, _ = _LiteralJS(corpo, variaveis).ler(len("return "))
    except (ValueError, IndexError):
        return None
    return valor


class _LiteralJS:
    """Leitor do subconjunto de JavaScript que o Nuxt serializa.

    Objetos com chave sem aspas, arrays, strings, numeros, `true`/`false`/
    `null`, `void 0` e as variaveis da funcao. Nada alem disso aparece no
    estado da pagina.
    """

    # JavaScript aceita ".01" sem o zero -- `salaryValue:.01` veio numa pagina
    # real, e o JSON recusaria.
    _NUMERO = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
    _NOME = re.compile(r"[A-Za-z_$][\w$]*")
    _STRING = re.compile(r'"(?:[^"\\]|\\.)*"')

    def __init__(self, texto: str, variaveis: dict) -> None:
        self.texto = texto
        self.variaveis = variaveis

    def ler(self, i: int):
        c = self.texto[i]
        if c == "{":
            return self._objeto(i)
        if c == "[":
            return self._array(i)
        if c == '"':
            m = self._STRING.match(self.texto, i)
            if m is None:
                raise ValueError(f"string sem fim em {i}")
            return json.loads(m.group(0)), m.end()
        m = self._NUMERO.match(self.texto, i)
        if m:
            bruto = m.group(0)
            if any(c in bruto for c in ".eE"):
                return float(bruto), m.end()
            return int(bruto), m.end()
        if self.texto.startswith("void 0", i):
            return None, i + len("void 0")
        m = self._NOME.match(self.texto, i)
        if m:
            nome = m.group(0)
            fixos = {"true": True, "false": False, "null": None}
            if nome in fixos:
                return fixos[nome], m.end()
            return self.variaveis.get(nome), m.end()
        raise ValueError(f"valor inesperado em {i}: {self.texto[i:i + 20]!r}")

    def _objeto(self, i: int):
        obj: dict = {}
        i += 1
        while self.texto[i] != "}":
            if self.texto[i] == '"':
                m = self._STRING.match(self.texto, i)
                chave = json.loads(m.group(0))
            else:
                m = self._NOME.match(self.texto, i)
                if m is None:
                    raise ValueError(f"chave inesperada em {i}")
                chave = m.group(0)
            i = m.end()
            if self.texto[i] != ":":
                raise ValueError(f"esperava ':' em {i}")
            obj[chave], i = self.ler(i + 1)
            if self.texto[i] == ",":
                i += 1
        return obj, i + 1

    def _array(self, i: int):
        itens = []
        i += 1
        while self.texto[i] != "]":
            valor, i = self.ler(i)
            itens.append(valor)
            if self.texto[i] == ",":
                i += 1
        return itens, i + 1
