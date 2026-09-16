"""Checagens de plausibilidade do resultado de uma coleta.

Teste de software pergunta "o codigo funciona?"; estas regras perguntam "o dado
desta execucao e confiavel?". Tudo aqui e puro (sem banco e sem rede): quem le o
historico e `persistence/execucoes.py`, e quem aplica o resultado ao status e
`scraper/pipeline.py`. Regras, limites e acoes em docs/data-quality.md.

As checagens **nunca** corrigem nem apagam dados: so sinalizam.

- **Severidade alta:** sinal de coleta quebrada (portal que zerou sem erro, queda
  brusca, valor fora do dominio, campo essencial vazio). A fonte deixa de ser `ok`
  -- entao nao encerra vagas -- e a execucao sai com exit 1.
- **Severidade baixa:** sinal para investigar; so aparece no resumo e no registro.

Limites calibrados com a coleta completa de 15/09/2026 (1.733 vagas brutas, 603
finais; `seed/vagas.csv`), a unica completa quando as regras foram escritas.
Recalibre quando houver mais historico.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from statistics import median

from api.dates import parse_published_date

from .classifier import default_classifier
from .execucao import OK, PARTIAL
from .models import NAO_INFORMADO, WORKPLACE_ORDER, Job, SourceStats
from .sources import DEFAULT_SOURCES

ALTA = "alta"
BAIXA = "baixa"

# Queda brusca: vagas brutas abaixo desta fracao da mediana das coletas completas
# anteriores. Em 15/09 a menor fonte padrao com vagas foi Trampos.co (24 brutas),
# que oscila demais para comparar; por isso a mediana minima.
FRACAO_MINIMA_DA_MEDIANA = 0.30
HISTORICO_MINIMO = 3
MEDIANA_MINIMA = 30

# Fatias de vazio so fazem sentido com amostra: em 15/09 Vagas.com.br teve 19 vagas
# finais, ProgramaThor 5 e Trampos.co 1.
VAGAS_MINIMAS_POR_FONTE = 20

# "Outros/TI Geral" foi 33% das vagas finais em 15/09 (45% no LinkedIn, que nao
# tem descricao). Acima disto, o classificador ou uma fonte provavelmente mudou.
FATIA_MAXIMA_FALLBACK = 0.55
VAGAS_MINIMAS_FALLBACK = 50


@dataclass(frozen=True)
class Expectativa:
    """Limite de vazios de um campo. `isentas`: fontes que nunca informam o campo."""

    limite: float
    severidade: str
    isentas: frozenset[str] = frozenset()


# Vazios observados em 15/09 (vagas finais por fonte com amostra): descricao 0-1%
# (LinkedIn 100%: o card nao tem descricao); empresa 0%; "Não informado" 0-1%
# (LinkedIn e Vagas.com 100%: a listagem nao informa); sem data 0-13% (ProgramaThor
# 100%); sem tecnologias 3-13% (LinkedIn 88%, Vagas.com 74%).
EXPECTATIVA_VAZIOS: dict[str, Expectativa] = {
    "description": Expectativa(0.20, ALTA, frozenset({"linkedin"})),
    "company": Expectativa(0.20, ALTA),
    "workplace_type": Expectativa(0.40, BAIXA, frozenset({"linkedin", "vagas"})),
    "published_date": Expectativa(0.40, BAIXA, frozenset({"programathor"})),
    "skills": Expectativa(0.50, BAIXA, frozenset({"linkedin", "vagas"})),
}


@dataclass(frozen=True)
class Alerta:
    """Uma regra violada. Nunca carrega URL nem dado de vaga, so contagens."""

    regra: str
    severidade: str
    fonte: str | None
    valor: float | int
    limite: float | int | str
    mensagem: str

    def como_dict(self) -> dict:
        return asdict(self)


def _vazio(job: Job, campo: str, hoje: date) -> bool:
    if campo == "workplace_type":
        return job.workplace_type in ("", NAO_INFORMADO)
    if campo == "published_date":
        return parse_published_date(job.published_date, hoje) is None
    if campo == "skills":
        return not job.skills
    return not (getattr(job, campo) or "").strip()


def _fontes_quebradas(stats: Iterable[SourceStats], escopo_completo: bool) -> list[Alerta]:
    if not escopo_completo:
        return []
    return [
        Alerta("fonte_zerada", ALTA, s.source, 0, "> 0",
               f"{s.source} listou 0 vagas sem nenhuma requisição falha")
        for s in stats
        if s.source in DEFAULT_SOURCES and s.raw_jobs == 0
        and not (s.errors or s.requests_failed)
    ]


def _quedas(
    stats: Iterable[SourceStats], escopo_completo: bool, historico: Mapping[str, Sequence[int]],
) -> list[Alerta]:
    if not escopo_completo:
        return []
    alertas = []
    for s in stats:
        anteriores = list(historico.get(s.source, ()))
        if len(anteriores) < HISTORICO_MINIMO or s.raw_jobs == 0:
            continue  # 0 vagas ja e `fonte_zerada` ou `failed`
        referencia = median(anteriores)
        limite = FRACAO_MINIMA_DA_MEDIANA * referencia
        if referencia >= MEDIANA_MINIMA and s.raw_jobs < limite:
            alertas.append(Alerta(
                "queda_brusca", ALTA, s.source, s.raw_jobs, round(limite),
                f"{s.source} listou {s.raw_jobs} vagas; a mediana das últimas "
                f"{len(anteriores)} coletas completas é {referencia:g}",
            ))
    return alertas


def _dominios(jobs: Sequence[Job], hoje: date) -> list[Alerta]:
    areas = set(default_classifier().area_names)
    # Vazio e legitimo: a persistencia grava nulo, e a tela mostra "Não informado".
    modalidades = {*WORKPLACE_ORDER, ""}
    contagens: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for job in jobs:
        if job.area not in areas:
            contagens[("area_fora_do_dominio", ALTA)][job.source] += 1
        if (job.workplace_type or "") not in modalidades:
            contagens[("modalidade_fora_do_dominio", ALTA)][job.source] += 1
        if job.url and not job.url.strip().lower().startswith(("http://", "https://")):
            contagens[("url_invalida", BAIXA)][job.source] += 1
        publicada = parse_published_date(job.published_date, hoje)
        if publicada is not None and publicada > hoje:
            contagens[("data_no_futuro", BAIXA)][job.source] += 1

    descricoes = {
        "area_fora_do_dominio": "vaga(s) com área fora de areas.yml",
        "modalidade_fora_do_dominio": "vaga(s) com modalidade fora do domínio",
        "url_invalida": "vaga(s) com URL que não é http(s)",
        "data_no_futuro": "vaga(s) com data de publicação no futuro",
    }
    return [
        Alerta(regra, severidade, fonte, total, 0, f"{fonte}: {total} {descricoes[regra]}")
        for (regra, severidade), por_fonte in contagens.items()
        for fonte, total in sorted(por_fonte.items())
    ]


def _vazios(jobs: Sequence[Job], hoje: date) -> list[Alerta]:
    por_fonte: dict[str, list[Job]] = defaultdict(list)
    for job in jobs:
        por_fonte[job.source].append(job)

    alertas = []
    for fonte, vagas in sorted(por_fonte.items()):
        if len(vagas) < VAGAS_MINIMAS_POR_FONTE:
            continue
        for campo, esperado in EXPECTATIVA_VAZIOS.items():
            if fonte in esperado.isentas:
                continue
            fatia = sum(_vazio(job, campo, hoje) for job in vagas) / len(vagas)
            if fatia > esperado.limite:
                alertas.append(Alerta(
                    "campo_vazio", esperado.severidade, fonte, round(fatia, 2), esperado.limite,
                    f"{fonte}: {fatia:.0%} das vagas sem {campo} (limite {esperado.limite:.0%})",
                ))
    return alertas


def _classificacao(jobs: Sequence[Job]) -> list[Alerta]:
    if len(jobs) < VAGAS_MINIMAS_FALLBACK:
        return []
    fallback = default_classifier().fallback_area
    fatia = sum(job.area == fallback for job in jobs) / len(jobs)
    if fatia <= FATIA_MAXIMA_FALLBACK:
        return []
    return [Alerta("classificacao_degenerada", BAIXA, None, round(fatia, 2), FATIA_MAXIMA_FALLBACK,
                   f"{fatia:.0%} das vagas em {fallback} (limite {FATIA_MAXIMA_FALLBACK:.0%})")]


def verificar(
    jobs: Sequence[Job],
    stats: Sequence[SourceStats],
    *,
    escopo_completo: bool,
    historico: Mapping[str, Sequence[int]] | None = None,
    hoje: date,
) -> list[Alerta]:
    """Alertas desta execucao, os de severidade alta primeiro.

    `jobs` sao as vagas finais (depois dos filtros); `historico` traz, por fonte,
    as vagas brutas das coletas completas anteriores. Sem historico suficiente, a
    regra de queda nao roda: a primeira execucao nunca gera falso positivo.
    """
    alertas = [
        *_fontes_quebradas(stats, escopo_completo),
        *_quedas(stats, escopo_completo, historico or {}),
        *_dominios(jobs, hoje),
        *_vazios(jobs, hoje),
        *_classificacao(jobs),
    ]
    return sorted(alertas, key=lambda a: (a.severidade != ALTA, a.regra, a.fonte or ""))


def ajustar_status(status_fontes: Mapping[str, str], alertas: Iterable[Alerta]) -> dict[str, str]:
    """Fonte `ok` com alerta alto vira `partial`: deixa de encerrar vagas. `failed` fica."""
    graves = {a.fonte for a in alertas if a.severidade == ALTA and a.fonte}
    ajustado = dict(status_fontes)
    for fonte in graves:
        if ajustado.get(fonte, OK) == OK:
            ajustado[fonte] = PARTIAL
    return ajustado


def altas(alertas: Iterable[Alerta]) -> list[Alerta]:
    return [a for a in alertas if a.severidade == ALTA]
