"""Remocao de vagas duplicadas.

Duplicatas aparecem por tres motivos:
  1. o mesmo termo de busca traz a mesma vaga em paginas diferentes;
  2. termos diferentes ("desenvolvedor junior" e "desenvolvedor jr") trazem a
     mesma vaga;
  3. portais diferentes anunciam a mesma vaga -- e cada um escreve o nome da
     empresa do seu jeito ("Minsait" na Gupy, "Minsait an Indra Company" no
     LinkedIn; "FEI" e "Centro Universitario FEI").

O caso 3 e o mais escorregadio. Nao da para casar so por titulo: "Analista de
Sistemas Junior" aparece em dezenas de empresas diferentes, e uni-las seria
muito pior que manter a duplicata. A regra de texto exige titulo normalizado
IDENTICO e nomes de empresa compativeis -- um conjunto de palavras contido no
outro, depois de descartar sufixos societarios e palavras genericas.

Antes das regras de texto vem uma prova mais dura: o id da vaga embutido no link
de candidatura (`identidade_no_link`). Agregador reescreve titulo e nome de
empresa, entao "Estagio Aurora" e "Programa de Estagios" anunciam a mesma vaga
com texto totalmente diferente -- mas com o mesmo link da Gupy. O link nao
depende de como cada portal escreveu as coisas.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from .models import Job, normalize

# Palavras que nao ajudam a identificar a empresa: sufixos societarios, termos
# genericos de ramo e rotulos de anonimato. "Confidencial" precisa entrar aqui,
# senao duas vagas confidenciais de empresas diferentes virariam a mesma.
_RUIDO_EMPRESA = {
    "ltda", "sa", "eireli", "epp", "me", "mei", "inc", "llc", "corp",
    "group", "grupo", "company", "holding", "participacoes",
    "brasil", "brazil", "do", "da", "de", "dos", "das", "e", "em",
    "solucoes", "servicos", "sistemas", "tecnologia", "tecnologias",
    "informatica", "consultoria", "consultores", "associados",
    "confidencial", "empresa", "multinacional", "vagas",
    # Siglas genericas de 2 letras. Precisam estar aqui desde que palavras
    # curtas passaram a identificar empresa, senao "Consultoria em TI",
    # "Attos RH", "Localiza&Co" e "Software.com.br" se identificariam pela
    # sigla e fundiriam empresas diferentes.
    "ti", "it", "rh", "co", "on", "br", "ia", "ai",
    "na", "no", "ao", "os", "as", "an", "of", "sp",
}


def _identidade_empresa(nome: str) -> frozenset[str]:
    """Palavras que realmente identificam a empresa.

    Palavra de 2 letras conta: descartando-a, marcas inteiras sumiam ("MV"
    virava identidade vazia e nunca cruzava com "MV Saude Digital"; "RD Station"
    virava {station} e cruzaria com qualquer "... Station").

    Letra solitaria continua fora: "S.A." normaliza para `s` + `a` e "Rede D'Or"
    para `d` + `or`. Se contassem, toda S.A. seria a mesma empresa.
    """
    return frozenset(
        p for p in normalize(nome).split()
        if p not in _RUIDO_EMPRESA and len(p) >= 2
    )


def _mesma_empresa(a: str, b: str) -> bool:
    """Um nome e uma variacao do outro? (subconjunto de palavras identificadoras)"""
    pa, pb = _identidade_empresa(a), _identidade_empresa(b)
    if not pa or not pb:
        return False
    return pa <= pb or pb <= pa


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
    sejam diferentes, e mesmo com o nome da empresa escrito de outro jeito. As
    demais formas valem por dominio: numero de cinco digitos se repete entre
    portais, entao "totvs.app:11639" e a chave, nao "11639".
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

    # A ordem abaixo nao e arbitraria:
    #   1. Token antes de digitos: o hex de 24 caracteres do Quickin
    #      ("6a64aa2322a5d000139206bb") tem sequencia de digitos dentro dele, e
    #      recortar so os digitos daria uma chave que duas vagas podem repetir.
    #   2. Digitos longos antes do id-colado-no-slug: o LinkedIn monta
    #      "jobs/view/<slug do titulo>-at-<empresa>-<id>", e titulo que comeca
    #      com numero de requisicao enganava a regra do slug -- "10274-analyst-
    #      analista-de-dados-junior-...-4454450486" daria "linkedin.com:10274"
    #      em vez do id real da vaga. Trampos (6 digitos) e ProgramaThor (5)
    #      nao tem sequencia de 7+, entao seguem caindo na regra do slug.
    segmentos = [seg for seg in caminho.split("/") if seg]
    for segmento in segmentos:
        if _TOKEN.match(segmento):
            return f"{dominio}:{segmento}"
    for segmento in segmentos:
        if _SEGMENTO_DIGITOS.match(segmento):
            return f"{dominio}:{segmento}"
    if achados := _DIGITOS_LONGOS.findall(caminho):
        return f"{dominio}:{max(achados, key=len)}"
    for segmento in segmentos:
        if achado := _DIGITOS_INICIAIS.match(segmento):
            return f"{dominio}:{achado.group(1)}"
    return ""


def deduplicate(jobs: list[Job]) -> tuple[list[Job], int]:
    """Devolve (vagas unicas, quantidade removida).

    Passo 1: identidade exata dentro do portal (`source:external_id`).
    Passo 2: mesmo id no link de candidatura -- prova dura, independente do
             texto que cada portal escreveu.
    Passo 3: mesma vaga anunciada em portais diferentes -- mesmo titulo
             normalizado + mesma empresa normalizada.
    Passo 4: idem, com o nome da empresa escrito de outro jeito.

    Em empate, vence a ocorrencia com descricao mais longa (mais informacao
    para o classificador).
    """
    by_source_key: dict[str, Job] = {}
    for job in jobs:
        existing = by_source_key.get(job.source_key)
        if existing is None or len(job.description) > len(existing.description):
            if existing is not None:
                job.search_term = existing.search_term or job.search_term
            by_source_key[job.source_key] = job

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
    for job in [*por_link.values(), *sem_id_no_link]:
        # Vagas sem empresa identificavel nao sao seguras para cruzar entre
        # portais (titulos genericos colidiriam), entao mantemos como unicas.
        # Vale tanto para o campo vazio quanto para rotulos que nao identificam
        # ninguem: duas vagas "Confidencial" com o mesmo titulo sao de empresas
        # diferentes ate prova em contrario.
        if not _identidade_empresa(job.company):
            by_fingerprint[job.source_key] = job
            continue
        existing = by_fingerprint.get(job.fingerprint)
        if existing is None or len(job.description) > len(existing.description):
            by_fingerprint[job.fingerprint] = job

    # Passo 4: mesma vaga em portais diferentes, com o nome da empresa escrito
    # de outro jeito. Exige titulo identico -- ver o docstring do modulo.
    por_titulo: dict[str, list[Job]] = {}
    for job in by_fingerprint.values():
        por_titulo.setdefault(normalize(job.title), []).append(job)

    unique: list[Job] = []
    for grupo in por_titulo.values():
        representantes: list[Job] = []
        for job in grupo:
            for i, escolhido in enumerate(representantes):
                if _mesma_empresa(job.company, escolhido.company):
                    if len(job.description) > len(escolhido.description):
                        representantes[i] = job
                    break
            else:
                representantes.append(job)
        unique.extend(representantes)

    return unique, len(jobs) - len(unique)
