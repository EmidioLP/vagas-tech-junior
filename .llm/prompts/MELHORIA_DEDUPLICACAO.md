# Melhoria da deduplicação de vagas

Este documento descreve duas correções feitas no `scraper/dedupe.py` do projeto
irmão **vagas-remotas-alerta** (o bot de alerta no Discord, que herdou este
código). As duas se aplicam aqui, porque o `dedupe.py` deste projeto está na
versão anterior: `len(p) > 2` na identidade da empresa e três passos de
deduplicação, sem a regra do link.

Tudo abaixo foi **medido em dados reais**, não deduzido. Os números estão nas
seções, e o final traz um script para você medir neste projeto antes de mexer.

**Evidência que já existe aqui:** rodei a regra nova sobre
`output/vagas_20260916_160730.csv` — uma exportação **já deduplicada** pelas
regras atuais, com 408 vagas. Ela encontrou **3 duplicatas que escaparam**:

```
gupy.io:eyJqb2JJZCI6MTIwMjk4Mjci...
   [querovagastech] VempraFTD              Programa de Estágio em Tecnologia | Afirmativo…
   [gupy         ] VempraFTD              Programa de Estágio em Tecnologia | Afirmativo…

gupy.io:eyJqb2JJZCI6MTI0Mzg0MDQi...
   [gupy         ] Estágio Aurora         Estágio Superior Não Obrigatório - Tecnologia…
   [querovagastech] Programa de Estágios   Estágio Superior Não Obrigatório - Tecnologia…

vagas.com.br:2834795
   [querovagastech] União Química Farmacêu Analista de Suporte JR
   [vagas        ] UNIÃO QUÍMICA          Analista de Suporte Junior - Service Desk
```

Repare no segundo e no terceiro caso: **a mesma vaga**, com nome de empresa e
título escritos de outro jeito por cada portal. Nenhuma regra baseada em texto
pegaria. O link pega.

---

## Melhoria 1 — marca de duas letras precisa identificar a empresa

### O que acontecia

Em `_identidade_empresa`, o filtro `len(p) > 2` descartava toda palavra de até
duas letras do nome da empresa. Isso apagava **marcas inteiras**:

| Nome da empresa | Identidade com `len > 2` | Consequência |
|---|---|---|
| `MV` | `∅` (vazia) | nunca cruza com `MV Saúde Digital` |
| `RD Station` | `{station}` | cruza com qualquer "… Station" |
| `Gi Group` | `∅` (`group` é ruído) | nunca cruza com nada |
| `BP`, `Q2`, `L3`, `DB` | `∅` | idem |

E empresa sem identidade **nunca é cruzada entre portais** — isso é
intencional no código (duas vagas "Confidencial" com o mesmo título não são a
mesma vaga). O efeito colateral era perder marcas curtas legítimas.

Caso real medido no projeto irmão: "Desenvolvedor(a) Java Fullstack Júnior"
chegou duas vezes ao Discord — como `MV` (LinkedIn) e como `MV Saúde Digital`
(GeekHunter).

### O que fazer

Em `scraper/dedupe.py`:

1. Trocar `len(p) > 2` por `len(p) >= 2` em `_identidade_empresa`.
2. Acrescentar as siglas genéricas de duas letras ao `_RUIDO_EMPRESA`, senão
   elas passam a "identificar" empresa.

```python
_RUIDO_EMPRESA = {
    # ... tudo que já está lá ...
    "confidencial", "empresa", "multinacional", "vagas",
    # Siglas genericas de 2 letras. Precisam estar aqui desde que palavras
    # curtas passaram a identificar empresa: "Consultoria em TI", "Attos RH",
    # "Localiza&Co", "Software.com.br".
    "ti", "it", "rh", "co", "on", "br", "ia", "ai",
    "na", "no", "ao", "os", "as", "an", "of", "sp",
}
```

**Letra solitária continua fora** (`>= 2`, não `>= 1`): "S.A." normaliza para
`s` + `a`, e "Rede D'Or" para `d` + `or`. Se contassem, toda S.A. seria a mesma
empresa.

A lista de ruído acima não foi chutada: saiu de uma varredura das palavras de
até duas letras que aparecem em 741 nomes de empresa reais. As que sobraram
(`mv`, `rd`, `gi`, `bp`, `cm`, `db`, `fb`, `bk`, `wi`, `rk`, `q2`, `l3`) são
marcas de verdade.

### Impacto medido

Rodando a regra antiga e a nova sobre 741 vagas reais: a nova junta **1 par a
mais** (duas "Supervisor De Projeto" da Gi Group, que são a mesma vaga) e
**nenhum par errado**.

---

## Melhoria 2 — deduplicar pelo id que o link de candidatura carrega

### O que acontecia

As regras de texto exigem **título normalizado idêntico**. Agregador reescreve
título e nome de empresa, então a mesma vaga passava duas vezes:

```
[querovagastech] BMP   "DESENVOLVEDOR JÚNIOR"
[inhire       ] BMP   "Desenvolvedor(a) Júnior – Engenharia / Projetos Técnicos"
```

Mas os dois links apontavam para a mesma página do ATS, com o mesmo UUID. O id
do link é **prova mais forte que o texto**, porque não depende de como cada
portal escreveu as coisas.

### O que fazer

#### a) Acrescentar a extração do id (no topo do `dedupe.py`)

```python
import re
from urllib.parse import unquote, urlsplit

# Formas de id que os links de vaga realmente usam, medidas nas fontes:
#   UUID .................. inhire.app/vagas/53e6e9da-81ce-4a1b-98bc-e32a77eea102
#   digitos longos ........ linkedin.com/jobs/view/4464615185
#                           infojobs.com.br/vaga-de-auxiliar-ti__12005412.aspx
#   segmento de digitos ... totvs.app/vempratotvs/11639/tech-analista
#   id antes do slug ...... trampos.co/oportunidades/774266-estagiario-a-em-qa
#                           programathor.com.br/jobs/31809-desenvolvedor-a-php
#   token com digito ...... gupy.io/job/eyJqb2JJZCI6MTI0NTk3Mzh9=
# Slug de titulo NAO vira id: "desenvolvedor--a--junior---net--1" tem hifen e
# seria igual em duas empresas diferentes do mesmo portal.
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_DIGITOS_LONGOS = re.compile(r"\d{7,}")
_SEGMENTO_DIGITOS = re.compile(r"^\d{4,6}$")
# Id no comeco do segmento, antes do slug do titulo. Cinco digitos no minimo --
# com quatro, "2026-programa-de-estagio" viraria id e juntaria vagas diferentes
# que so compartilham o ano.
_DIGITOS_INICIAIS = re.compile(r"^(\d{5,})-")
# Token de id tem digito. Sem exigir isso, a regra casava trecho fixo de URL:
# "carreiratotvslinx" (pagina de carreiras) juntou tres vagas diferentes da
# Linx, e "CandidateExperience" (caminho padrao do Oracle Recruiting) juntou
# seis vagas de empresas diferentes.
_TOKEN = re.compile(r"^(?=[^\d]*\d)[A-Za-z0-9_=+%]{16,}$")

# Segundo nivel de dominio que nao identifica ninguem: "infojobs.com.br" e
# "vagas.com.br" viram os dois "com.br" se cortarmos so dois rotulos, e ai um
# id numerico repetido fundiria vagas de portais diferentes.
_SUFIXO_COMPOSTO = {"com", "net", "org", "gov", "edu", "adv", "eng", "esp", "ind"}


def _dominio(netloc: str) -> str:
    """Dominio que identifica o portal, tratando sufixo composto (.com.br)."""
    host = netloc.lower().split("@")[-1].split(":")[0].strip(".")
    rotulos = [r for r in host.split(".") if r]
    if len(rotulos) < 2:
        return ""
    if len(rotulos) >= 3 and len(rotulos[-1]) == 2 and rotulos[-2] in _SUFIXO_COMPOSTO:
        return ".".join(rotulos[-3:])
    return ".".join(rotulos[-2:])


def identidade_no_link(url: str) -> str:
    """Id da vaga embutido no link, ou "" quando o link nao carrega nenhum.

    UUID vale sozinho, porque e unico no mundo -- serve para casar o link da
    pagina do ATS com o link que o agregador publica, ainda que os caminhos
    sejam diferentes. As demais formas valem por dominio: numero de cinco
    digitos se repete entre portais, entao "totvs.app:11639" e a chave, nao
    "11639".
    """
    partes = urlsplit(url or "")
    if partes.scheme not in ("http", "https"):
        return ""

    caminho = unquote(partes.path)
    if achado := _UUID.search(caminho):
        return f"uuid:{achado.group(0).lower()}"

    dominio = _dominio(partes.netloc)
    if not dominio:
        return ""

    # Token antes de digitos: hex de 24 caracteres tem sequencia de digitos
    # dentro dele ("6a64aa2322a5d000139206bb"), e recortar so os digitos daria
    # uma chave que duas vagas diferentes podem repetir.
    segmentos = [seg for seg in caminho.split("/") if seg]
    for segmento in segmentos:
        if _TOKEN.match(segmento):
            return f"{dominio}:{segmento}"
    for segmento in segmentos:
        if _SEGMENTO_DIGITOS.match(segmento):
            return f"{dominio}:{segmento}"
    for segmento in segmentos:
        if achado := _DIGITOS_INICIAIS.match(segmento):
            return f"{dominio}:{achado.group(1)}"
    if achados := _DIGITOS_LONGOS.findall(caminho):
        return f"{dominio}:{max(achados, key=len)}"
    return ""
```

**As duas fontes exclusivas deste projeto estão cobertas pela regra do id antes
do slug**, e isso foi conferido nos links reais do seu `output/`:

| Fonte | Link | Chave |
|---|---|---|
| Trampos | `trampos.co/oportunidades/774266-estagiario-a-em-qa` | `trampos.co:774266` |
| ProgramaThor | `programathor.com.br/jobs/31809-desenvolvedor-a-php-junior` | `programathor.com.br:31809` |

Sem essa regra, os dois ficavam sem chave: o id tem 5 ou 6 dígitos e vem colado
no slug, então nem a regra de "segmento só de dígitos" nem a de "7 dígitos ou
mais" alcançava.

#### b) Inserir o passo novo em `deduplicate`, entre o passo 1 e o de fingerprint

```python
    # Passo 2: mesma vaga provada pelo id no link de candidatura. Vem antes das
    # regras de titulo porque e prova dura -- nao depende de como cada portal
    # escreveu o titulo nem o nome da empresa.
    por_link: dict[str, Job] = {}
    sem_id_no_link: list[Job] = []
    for job in by_source_key.values():
        chave = identidade_no_link(job.url)
        if not chave:
            sem_id_no_link.append(job)
            continue
        existing = por_link.get(chave)
        if existing is None or len(job.description) > len(existing.description):
            por_link[chave] = job

    by_fingerprint: dict[str, Job] = {}
    for job in [*por_link.values(), *sem_id_no_link]:   # <- era by_source_key.values()
        ...
```

O resto de `deduplicate` continua igual; só renumere os comentários dos passos
seguintes (o antigo "Passo 2" vira 3, e o "Passo 3" vira 4). O critério de
desempate segue o mesmo do projeto: **vence quem tem a descrição mais longa**.

### As duas armadilhas — e por que o código é assim

Estas duas decisões não são preciosismo. Elas vieram de fusões falsas que
apareceram ao medir com dados reais:

1. **Slug de título não pode valer como id.** `desenvolvedor--a--junior---net--1`
   seria igual em duas empresas diferentes do mesmo portal. Daí a exigência de
   não haver hífen no token.
2. **Token precisa ter dígito.** A primeira versão aceitava qualquer segmento
   longo sem hífen, e isso juntou vaga que não devia:
   - `carreiratotvslinx` (nome da página de carreiras) fundiu **três** vagas
     diferentes da Linx;
   - `CandidateExperience` (caminho fixo do Oracle Recruiting) fundiu **seis**
     vagas de **empresas diferentes**.

   Com a exigência de dígito, as fusões caíram de 15 para 8 — as 7 que saíram
   eram todas falsas.

### Impacto medido

Em 1.466 vagas reais de três fontes: **8 duplicatas que as regras de título não
pegavam**, e zero fusões falsas. Todos os 8 grupos foram conferidos um por um:

| Caso | Por que o texto falhava |
|---|---|
| BMP | título reescrito pelo agregador |
| Lima Consulting Group | um portal põe o id no começo do título |
| Zeta Dados / Zetadados | grafia da empresa |
| dti digital | redação do título diferente |
| St. Marche | "Analista de BI" contra "Analista de Business Intelligence" |
| SiDi, FAST2 MINE | um portal acrescenta "Estágio" ao fim do título |
| AP Digital Services | apelido da empresa ("AP (Amazing People)") |

---

## Testes para acrescentar em `tests/test_dedupe.py`

```python
import pytest

from scraper.dedupe import deduplicate, identidade_no_link
from scraper.models import Job


@pytest.mark.parametrize("url,esperado", [
    ("https://agtaxtech.inhire.app/vagas/53e6e9da-81ce-4a1b-98bc-e32a77eea102",
     "uuid:53e6e9da-81ce-4a1b-98bc-e32a77eea102"),
    ("https://agtaxtech.inhire.app/vagas/53e6e9da-81ce-4a1b-98bc-e32a77eea102/dev-jr",
     "uuid:53e6e9da-81ce-4a1b-98bc-e32a77eea102"),
    ("https://jobs.quickin.io/infovagas/jobs/6a64aa2322a5d000139206bb",
     "quickin.io:6a64aa2322a5d000139206bb"),
    ("https://gruposeb.gupy.io/job/eyJqb2JJZCI6MTI0NTk3MzhpfQ==?x=1",
     "gupy.io:eyJqb2JJZCI6MTI0NTk3MzhpfQ=="),
    # Sufixo composto: sem tratar, os dois virariam "com.br".
    ("https://www.infojobs.com.br/vaga-de-auxiliar__12005412.aspx", "infojobs.com.br:12005412"),
    ("https://www.vagas.com.br/vagas/v2824782/dev-jr", "vagas.com.br:2824782"),
    # Subdominio nao atrapalha.
    ("https://br.linkedin.com/jobs/view/estagiario-de-ti-at-x-4464615185", "linkedin.com:4464615185"),
    ("https://www.linkedin.com/jobs/view/4464615185/", "linkedin.com:4464615185"),
    ("https://atracaodetalentos.totvs.app/vempratotvs/11639/tech", "totvs.app:11639"),
])
def test_identidade_no_link_reconhece_o_id(url, esperado):
    assert identidade_no_link(url) == esperado


@pytest.mark.parametrize("url", [
    # Slug de titulo NAO e id: seria igual em duas empresas do mesmo portal.
    "https://www.geekhunter.com/pt/locaweb/jobs/desenvolvedor--a--junior---net--1",
    "https://vaga-ja.com/vagas/empresa-x/estagio-em-comercio-exterior",
    "https://empresa.gupy.io/",
    "#",
    "",
])
def test_link_sem_id_nao_gera_chave(url):
    assert identidade_no_link(url) == ""


@pytest.mark.parametrize("url", [
    # "carreiratotvslinx" juntava 3 vagas da Linx.
    "https://carreiratotvslinx.totvs.app/carreiratotvslinx/vagas",
    # "CandidateExperience" juntava 6 vagas de empresas diferentes.
    "https://x.test/hcmUI/CandidateExperience/requisitions",
])
def test_palavra_sem_digito_nao_e_id(url):
    assert identidade_no_link(url) == ""


@pytest.mark.parametrize("url,esperado", [
    # As duas fontes exclusivas deste projeto.
    ("https://trampos.co/oportunidades/774266-estagiario-a-em-qa", "trampos.co:774266"),
    ("https://trampos.co/oportunidades/774266-estagiario-a-em-qa/share/email",
     "trampos.co:774266"),
    ("https://programathor.com.br/jobs/31809-desenvolvedor-a-php-junior",
     "programathor.com.br:31809"),
])
def test_id_antes_do_slug(url, esperado):
    assert identidade_no_link(url) == esperado


def test_ano_no_comeco_do_slug_nao_e_id():
    """Com quatro dígitos, "2026-programa-de-estagio" juntaria vagas que só
    compartilham o ano."""
    assert identidade_no_link("https://x.test/vagas/2026-programa-de-estagio") == ""


def test_mesmo_link_funde_mesmo_com_titulo_reescrito():
    """Caso real: mesma vaga da BMP, titulo reescrito pelo agregador."""
    jobs = [
        Job(source="inhire", external_id="5e4fc0bc", company="BMP",
            title="Desenvolvedor(a) Júnior – Engenharia / Projetos Técnicos",
            url="https://bmp.inhire.app/vagas/5e4fc0bc-1111-2222-3333-444455556666",
            description="descricao completa da vaga"),
        Job(source="querovagastech", external_id="99", company="BMP",
            title="DESENVOLVEDOR JÚNIOR",
            url="https://bmp.inhire.app/vagas/5e4fc0bc-1111-2222-3333-444455556666/dev-junior"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1 and removed == 1
    assert unique[0].description == "descricao completa da vaga"


def test_links_diferentes_do_mesmo_portal_nao_fundem():
    jobs = [
        Job(source="linkedin", external_id="1", title="Dev Júnior", company="Acme",
            url="https://www.linkedin.com/jobs/view/4464615185"),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="Outra Empresa",
            url="https://www.linkedin.com/jobs/view/4464615186"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_id_numerico_igual_em_portais_diferentes_nao_funde():
    jobs = [
        Job(source="a", external_id="1", title="Dev Júnior", company="Empresa A",
            url="https://atracaodetalentos.totvs.app/vempratotvs/11639/x"),
        Job(source="b", external_id="2", title="Dev Júnior", company="Empresa B",
            url="https://prezensa.com/vagas/11639"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


# --- marcas de duas letras (Melhoria 1) --------------------------------------

def test_marca_de_duas_letras_funde_entre_portais():
    jobs = [
        Job(source="linkedin", external_id="1", company="MV",
            title="DESENVOLVEDOR(A) JAVA FULLSTACK JÚNIOR"),
        Job(source="geekhunter", external_id="2", company="MV Saúde Digital",
            title="Desenvolvedor(a) Java Fullstack Júnior"),
    ]
    assert len(deduplicate(jobs)[0]) == 1


def test_letra_solitaria_nao_identifica_empresa():
    """"S.A." vira "s" e "a" — se contassem, toda S.A. seria a mesma empresa."""
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="S.A."),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="S/A"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_sigla_generica_de_duas_letras_nao_funde_empresas():
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Suporte Jr",
            company="4INFRA Consultoria em TI"),
        Job(source="linkedin", external_id="2", title="Analista de Suporte Jr",
            company="Digitech Soluções em TI"),
    ]
    assert len(deduplicate(jobs)[0]) == 2
```

---

## Como medir neste projeto antes e depois

Este script roda offline, sobre a última exportação de `output/`, e lista as
duplicatas que as regras atuais deixaram passar. Rode antes de mexer (para ver
o problema) e depois (deve encontrar zero, porque a deduplicação já as removeu
na coleta seguinte).

```python
import csv, glob, os
from scraper.dedupe import identidade_no_link

caminho = sorted(glob.glob("output/vagas_*.csv"), key=os.path.getmtime)[-1]
linhas = list(csv.DictReader(open(caminho, encoding="utf-8-sig")))

grupos = {}
for linha in linhas:
    chave = identidade_no_link(linha.get("url") or "")
    if chave:
        grupos.setdefault(chave, []).append(linha)

duplicados = {c: g for c, g in grupos.items() if len(g) > 1}
print(f"{os.path.basename(caminho)}: {len(linhas)} vagas exportadas")
print(f"duplicatas que escaparam: {sum(len(g) - 1 for g in duplicados.values())}")
for chave, grupo in duplicados.items():
    print(f"\n  {chave}")
    for linha in grupo:
        print(f"     [{linha['source']:14}] {linha['company'][:24]:26} {linha['title'][:46]}")
```

Para conferir que **nenhuma fusão nova é falsa**, imprima os grupos e olhe um
por um: eles devem ser sempre a mesma vaga com texto diferente. Foi assim que
as armadilhas do `carreiratotvslinx` e do `CandidateExperience` apareceram.

---

## Cuidados neste projeto

Diferente do bot de alerta, aqui a deduplicação alimenta CSV, banco, gráficos e
API. Então:

1. **Números de relatório vão mudar um pouco** (para menos, que é o correto).
   Se algum teste fixa contagem — olhe `tests/test_qualidade.py`,
   `tests/cenario_historico.py`, `tests/test_export.py` e os de API — ele pode
   quebrar legitimamente. Ajuste o número esperado, não a regra.
2. **O banco já gravado não é reprocessado.** Vagas duplicadas que entraram
   antes continuam lá; a melhoria só vale para coletas novas. Se quiser limpar
   o histórico, é um passo separado — dá para usar `identidade_no_link` sobre a
   coluna `url` para achar os pares.
3. **Rode a suíte inteira** (`python -m pytest -q`). No projeto irmão, as duas
   melhorias passaram sem quebrar nada: 353 testes.
4. **A ordem das regras importa.** Token antes de dígitos, senão o hex de 24
   caracteres do Quickin (`6a64aa2322a5d000139206bb`) vira a chave
   `000139206`, que duas vagas diferentes podem repetir por acaso.
5. **UUID vale mesmo com nome de empresa diferente.** Dois casos reais que a
   comparação de empresa reprovaria e que são a mesma vaga: `Zeta Dados` contra
   `Zetadados`, e `AP (Amazing People)` contra `AP Digital Services`. O UUID é
   único no mundo — não faça a fusão por UUID depender do nome da empresa.
