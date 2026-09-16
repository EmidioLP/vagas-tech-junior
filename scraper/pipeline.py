"""Orquestracao: coleta -> senioridade -> dedupe -> classificacao -> banco -> CSV opcional.

O banco (`jobs` + `job_snapshots`) e a fonte de verdade. A exportacao de CSV,
relatorio e graficos e opcional e nao e pre-requisito da gravacao.

Cada execucao com banco fica registrada em `collection_runs`, inclusive quando a
guarda de intervalo (`respeitar_intervalo`) decide pular a coleta. As regras de
intervalo e de status por fonte estao em `scraper/execucao.py`; as checagens de
qualidade do resultado, em `scraper/qualidade.py`.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .classifier import classify_jobs, default_classifier, filter_tech
from .config import ConfiguracaoError, Settings, obter_intervalo_dias
from .dedupe import deduplicate
from .execucao import (
    FAILED,
    OK,
    PARTIAL,
    SKIPPED,
    STATUS_QUE_CONTAM,
    SUCCESS,
    Agenda,
    Decisao,
    calcular_agenda,
    decidir,
    escopo_completo,
    status_execucao,
    status_por_fonte,
)
from . import qualidade
from .export import build_ranking, export_all
from .http_client import PoliteSession
from .models import Job, SourceStats
from .seniority import SeniorityFilter, filter_entry_level
from .skills import attach_skills
from .sources import SOURCE_REGISTRY

if TYPE_CHECKING:  # pragma: no cover
    from persistence.repositorio import ResumoEncerramento, ResumoPersistencia

logger = logging.getLogger(__name__)

# Tabelas e coluna que as ultimas migrations exigidas pelo pipeline criam.
_SCHEMA_EXIGIDO = {"jobs": None, "job_snapshots": "content_hash", "collection_runs": None}


@dataclass
class PipelineResult:
    jobs: list[Job]
    ranking: list[dict]
    files: dict[str, Path] = field(default_factory=dict)
    stats: list[SourceStats] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    persistencia: ResumoPersistencia | None = None
    # Politica de execucao (scraper/execucao.py).
    status: str | None = None
    exit_code: int = 0
    status_fontes: dict[str, str] = field(default_factory=dict)
    decisao: Decisao | None = None
    # Ultima coleta completa e proxima prevista; so com banco e X conhecido.
    agenda: Agenda | None = None
    # Vagas que sumiram da listagem; so em coleta completa com banco.
    encerramento: ResumoEncerramento | None = None
    # external_id brutos por fonte, antes dos filtros: o que os portais ainda listam.
    vistas: dict[str, set[str]] = field(default_factory=dict, repr=False)
    # Checagens de plausibilidade (scraper/qualidade.py), as altas primeiro.
    alertas: list[qualidade.Alerta] = field(default_factory=list)

    @property
    def top_area(self) -> str | None:
        return self.ranking[0]["area"] if self.ranking else None

    @property
    def pulada(self) -> bool:
        return self.status == SKIPPED


def _agora() -> datetime:
    """Relogio da execucao. Os testes o substituem para simular dias passando."""
    return datetime.now(timezone.utc)


def _intervalo_informativo(persistir: bool) -> int | None:
    """X numa execucao forcada: so serve para informar a proxima coleta, entao
    ausente (ou invalido) nao e erro."""
    if not persistir:
        return None
    try:
        return obter_intervalo_dias()
    except ConfiguracaoError as exc:
        logger.debug("Sem intervalo para informar a próxima coleta: %s", exc)
        return None


def collect(settings: Settings) -> tuple[list[Job], list[SourceStats], int]:
    """Roda todos os portais selecionados e devolve as vagas brutas.

    Uma fonte que quebra por inteiro (excecao fora do isolamento por termo de
    `JobSource.fetch`) vira erro nas estatisticas dela, e as outras seguem.
    """
    all_jobs: list[Job] = []
    stats: list[SourceStats] = []
    total_requests = 0

    for source_name in settings.sources:
        source_cls = SOURCE_REGISTRY.get(source_name)
        if source_cls is None:
            logger.warning("Portal desconhecido, ignorando: %s", source_name)
            continue

        logger.info("=== Coletando em %s ===", source_cls.label)
        with PoliteSession(
            user_agent=settings.user_agent,
            delay_seconds=settings.delay_seconds,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            backoff_factor=settings.backoff_factor,
        ) as session:
            source = None
            try:
                source = source_cls(session, settings)
                jobs = source.fetch(settings.search_terms)
                source_stats = source.stats
            except Exception as exc:  # uma fonte quebrada nao derruba as outras
                jobs = []
                message = f"{source_name}: {type(exc).__name__}: {exc}"
                logger.warning("Fonte interrompida, seguindo com as demais: %s", message)
                source_stats = source.stats if source is not None else SourceStats(source_name)
                source_stats.errors.append(message)

            # A sessao e quem sabe das desistencias: as fontes so param de paginar.
            source_stats.raw_jobs = len(jobs)
            source_stats.requests_made = session.request_count
            source_stats.requests_failed = session.failed_count
            all_jobs.extend(jobs)
            stats.append(source_stats)
            total_requests += session.request_count

        logger.info("%s: %d vagas brutas, %d requisições falhas",
                    source_cls.label, len(jobs), source_stats.requests_failed)

    return all_jobs, stats, total_requests


def preparar_banco(destino: str | Path | None = None) -> Any:
    """Engine pronto para gravar, validado ANTES da coleta.

    Coletar leva minutos; descobrir so no fim que falta DATABASE_URL, que o banco
    nao responde ou que as migrations nao rodaram jogaria esse tempo fora.
    """
    from sqlalchemy import inspect
    from sqlalchemy.exc import SQLAlchemyError

    from api.database import make_engine

    engine = make_engine(destino)  # sem destino nem DATABASE_URL: ConfiguracaoError
    try:
        inspetor = inspect(engine)
        for tabela, coluna in _SCHEMA_EXIGIDO.items():
            if not inspetor.has_table(tabela) or (
                coluna and coluna not in {c["name"] for c in inspetor.get_columns(tabela)}
            ):
                raise ConfiguracaoError(
                    "O banco não está com o schema atual. Rode `alembic upgrade head` "
                    "(veja docs/migrations.md)."
                )
    except SQLAlchemyError as exc:
        engine.dispose()
        # So o tipo do erro: a mensagem do driver pode citar host e usuario.
        raise ConfiguracaoError(
            f"Não foi possível acessar o banco ({type(getattr(exc, 'orig', None) or exc).__name__})."
        ) from exc
    except ConfiguracaoError:
        engine.dispose()
        raise
    return engine


def run(
    settings: Settings,
    strict_seniority: bool = False,
    keep_non_tech: bool = False,
    with_charts: bool = True,
    persistir: bool = True,
    destino_db: str | Path | None = None,
    exportar_csv: bool = False,
    respeitar_intervalo: bool = False,
    intervalo_dias: int | None = None,
    gatilho: str = "local",
) -> PipelineResult:
    """Executa o fluxo completo: grava no banco e, se pedido, exporta arquivos.

    `destino_db` vence DATABASE_URL e aceita caminho SQLite (testes).

    Com `respeitar_intervalo`, consulta a ultima coleta completa registrada e, se
    `intervalo_dias` ainda nao passaram, registra a execucao como pulada sem
    coletar. Sem `intervalo_dias`, le COLLECTION_INTERVAL_DAYS.

    Com banco e X conhecido (sempre na guarda; na execucao forcada, se
    COLLECTION_INTERVAL_DAYS estiver definida), `result.agenda` informa a ultima
    coleta completa e a proxima prevista.
    """
    if respeitar_intervalo and not persistir:
        raise ConfiguracaoError(
            "A guarda de intervalo precisa do banco: é lá que fica a última "
            "coleta registrada."
        )
    if intervalo_dias is None:
        intervalo_dias = (obter_intervalo_dias() if respeitar_intervalo
                          else _intervalo_informativo(persistir))
    elif intervalo_dias < 1:
        raise ConfiguracaoError("COLLECTION_INTERVAL_DAYS precisa ser um inteiro positivo.")

    engine = preparar_banco(destino_db) if persistir else None
    # Um instante por execucao: e o `collected_at` de todos os snapshots dela.
    collected_at = _agora()

    try:
        ultima_anterior = None
        if engine is not None and intervalo_dias is not None:
            from persistence.execucoes import ultima_coleta_completa

            ultima_anterior = ultima_coleta_completa(engine)

        # Vagas brutas das coletas completas anteriores: base da regra de queda brusca.
        historico: dict[str, list[int]] = {}
        if engine is not None:
            from persistence.execucoes import historico_vagas_brutas

            historico = historico_vagas_brutas(engine)

        decisao = None
        if respeitar_intervalo:
            decisao = decidir(ultima_anterior, collected_at, intervalo_dias)
            logger.info("Guarda de intervalo: %s", decisao.motivo)

        if decisao is not None and not decisao.executar:
            result = PipelineResult(
                jobs=[], ranking=[], status=SKIPPED, exit_code=0, decisao=decisao,
                meta={"collected_at": collected_at.isoformat(), "motivo": decisao.motivo,
                      "status": SKIPPED},
            )
        else:
            result = _processar(settings, strict_seniority, keep_non_tech, with_charts,
                                engine, collected_at, exportar_csv)
            result.decisao = decisao
            _aplicar_politica(result, settings, historico, collected_at)
            if engine is not None:
                _encerrar_vagas_ausentes(engine, result, settings, collected_at)

        result.meta["gatilho"] = gatilho
        if engine is not None and intervalo_dias is not None:
            # Esta execucao vira a "ultima coleta" se tiver escopo completo e nao falhar.
            conta = result.status in STATUS_QUE_CONTAM and escopo_completo(settings)
            result.agenda = calcular_agenda(
                collected_at if conta else ultima_anterior, collected_at, intervalo_dias
            )
            logger.info("%s (%s).", result.agenda.frase(), result.agenda.periodicidade)
        if engine is not None:
            _registrar_execucao(engine, result, settings, collected_at, gatilho,
                                intervalo_dias if respeitar_intervalo else None)
        return result
    finally:
        if engine is not None:
            engine.dispose()


def _processar(
    settings: Settings,
    strict_seniority: bool,
    keep_non_tech: bool,
    with_charts: bool,
    engine: Any,
    collected_at: datetime,
    exportar_csv: bool,
) -> PipelineResult:
    raw_jobs, stats, requests_made = collect(settings)
    logger.info("Total bruto: %d vagas", len(raw_jobs))
    # Tudo que os portais ainda listam, antes dos filtros: base do encerramento.
    vistas: dict[str, set[str]] = {}
    for job in raw_jobs:
        vistas.setdefault(job.source, set()).add(job.external_id)

    if settings.only_junior:
        seniority_filter = SeniorityFilter.from_file(strict=strict_seniority)
        jobs = filter_entry_level(raw_jobs, seniority_filter)
        dropped_seniority = len(raw_jobs) - len(jobs)
    else:
        jobs = raw_jobs
        for job in jobs:
            job.seniority = job.seniority or "Não filtrado"
        dropped_seniority = 0
    logger.info("Apos filtro de senioridade: %d vagas (-%d)", len(jobs), dropped_seniority)

    jobs, duplicates = deduplicate(jobs)
    logger.info("Apos deduplicacao: %d vagas (-%d)", len(jobs), duplicates)

    classifier = default_classifier()
    if keep_non_tech:
        dropped_non_tech = 0
    else:
        jobs, non_tech = filter_tech(jobs, classifier)
        dropped_non_tech = len(non_tech)
        logger.info("Apos filtro de tecnologia: %d vagas (-%d nao-tech)",
                    len(jobs), dropped_non_tech)

    jobs = classify_jobs(jobs, classifier)
    # Antes da exportacao: `to_row` trunca a descricao, e as tecnologias precisam
    # do texto completo (a Gupy devolve a descricao inteira).
    jobs = attach_skills(jobs)
    ranking = build_ranking(jobs)

    meta = {
        "sources": [SOURCE_REGISTRY[s].label for s in settings.sources
                    if s in SOURCE_REGISTRY],
        "terms_count": len(settings.search_terms),
        "raw_jobs": len(raw_jobs),
        "dropped_seniority": dropped_seniority,
        "dropped_non_tech": dropped_non_tech,
        "duplicates": duplicates,
        "requests": requests_made,
        "collected_at": collected_at.isoformat(),
    }

    persistencia = None
    if engine is not None:
        from persistence.repositorio import persistir_vagas

        persistencia = persistir_vagas(jobs, engine, collected_at)
        meta["persistencia"] = persistencia.como_dict()

    files: dict[str, Path] = {}
    if exportar_csv:
        files = export_all(jobs, settings.ensure_output_dir(), meta,
                           with_charts=with_charts)
    return PipelineResult(jobs=jobs, ranking=ranking, files=files,
                          stats=stats, meta=meta, persistencia=persistencia,
                          vistas=vistas)


def _encerrar_vagas_ausentes(
    engine: Any, result: PipelineResult, settings: Settings, collected_at: datetime,
) -> None:
    """Encerra vagas que sumiram da listagem em duas coletas seguidas.

    So avalia o que da para confiar: coleta de escopo completo que nao falhou e,
    dentro dela, fontes com status ok que listaram pelo menos uma vaga. Uma fonte
    que volta vazia sem erro pode ser mudanca no HTML do portal, e encerraria tudo.
    """
    if not escopo_completo(settings) or result.status == FAILED:
        return
    confiaveis = {
        fonte: result.vistas[fonte]
        for fonte, status in result.status_fontes.items()
        if status == OK and result.vistas.get(fonte)
    }
    if not confiaveis:
        return

    from persistence.repositorio import encerrar_ausentes

    result.encerramento = encerrar_ausentes(engine, confiaveis, collected_at)
    result.meta["encerramento"] = result.encerramento.como_dict()
    if result.encerramento.erros:
        result.exit_code = 1
        if result.status == SUCCESS:
            result.status = PARTIAL
            result.meta["status"] = PARTIAL
        aviso = "encerramento de vagas desfeito: " + ", ".join(result.encerramento.erros)
        result.meta["motivo"] = "; ".join(filter(None, [result.meta.get("motivo"), aviso]))


def _aplicar_politica(
    result: PipelineResult,
    settings: Settings,
    historico: dict[str, list[int]],
    collected_at: datetime,
) -> None:
    """Status por fonte e da execucao, e o motivo quando nao foi sucesso pleno.

    Roda antes do encerramento: fonte com alerta de qualidade alto vira `partial`
    e, por isso, nao encerra vagas nesta execucao.
    """
    result.alertas = qualidade.verificar(
        result.jobs, result.stats, escopo_completo=escopo_completo(settings),
        historico=historico, hoje=collected_at.date(),
    )
    altos = qualidade.altas(result.alertas)
    result.status_fontes = qualidade.ajustar_status(
        status_por_fonte(result.stats, result.persistencia), result.alertas
    )
    falhas = result.persistencia.falhas if result.persistencia is not None else 0
    result.status, result.exit_code = status_execucao(
        result.status_fontes, len(result.jobs), falhas, len(altos)
    )

    motivos: list[str] = []
    if result.status_fontes and all(s == FAILED for s in result.status_fontes.values()):
        motivos.append("todas as fontes falharam")
    else:
        if not result.jobs:
            motivos.append("nenhuma vaga encontrada")
        com_falha = [f"{fonte} ({status})" for fonte, status in result.status_fontes.items()
                     if status != OK]
        if com_falha:
            motivos.append("fontes com falha: " + ", ".join(com_falha))
    if falhas:
        motivos.append(f"{falhas} vaga(s) não gravada(s)")
    if altos:
        motivos.append("alertas de qualidade: " + ", ".join(
            f"{a.regra} ({a.fonte})" if a.fonte else a.regra for a in altos))

    result.meta["status"] = result.status
    result.meta["qualidade"] = [a.como_dict() for a in result.alertas]
    result.meta["status_fontes"] = dict(result.status_fontes)
    if motivos:
        result.meta["motivo"] = "; ".join(motivos)
    for fonte, status in result.status_fontes.items():
        if status != OK:
            logger.warning("Fonte %s terminou com status %s", fonte, status)
    for alerta in result.alertas:
        nivel = logging.WARNING if alerta.severidade == qualidade.ALTA else logging.INFO
        logger.log(nivel, "Qualidade (%s): %s", alerta.severidade, alerta.mensagem)


def _sumario(result: PipelineResult) -> dict:
    """O que vai para `collection_runs.summary`: so contagens, nunca mensagens de
    erro, que podem citar URL de portal ou dados da conexao."""
    stats = {s.source: s for s in result.stats}
    gravacao = result.persistencia.por_fonte if result.persistencia is not None else {}
    fontes: dict[str, dict] = {}
    for fonte, status in result.status_fontes.items():
        item: dict[str, Any] = {"status": status}
        if fonte in stats:
            s = stats[fonte]
            item.update(requests=s.requests_made, requests_falhos=s.requests_failed,
                        vagas_brutas=s.raw_jobs, erros=len(s.errors))
        if fonte in gravacao:
            item.update(asdict(gravacao[fonte]))
        if result.encerramento is not None and fonte in result.encerramento.por_fonte:
            item.update(asdict(result.encerramento.por_fonte[fonte]))
        fontes[fonte] = item
    # Alertas so levam regra, fonte e contagens; nunca URL nem dado de vaga.
    return {"fontes": fontes, "vagas": len(result.jobs),
            "qualidade": [a.como_dict() for a in result.alertas]}


def _registrar_execucao(
    engine: Any,
    result: PipelineResult,
    settings: Settings,
    started_at: datetime,
    gatilho: str,
    intervalo_dias: int | None,
) -> None:
    """Grava a execucao em `collection_runs`. Falhar aqui nunca desfaz a coleta."""
    from sqlalchemy.exc import SQLAlchemyError

    from persistence.execucoes import registrar_execucao

    decisao = result.decisao
    try:
        registrar_execucao(
            engine,
            started_at=started_at,
            finished_at=_agora(),
            triggered_by=gatilho,
            status=result.status,
            full_scope=escopo_completo(settings),
            interval_days=intervalo_dias,
            reason=result.meta.get("motivo") or (decisao.motivo if decisao else None),
            next_run_on=result.agenda.proxima if result.agenda is not None else None,
            jobs_count=len(result.jobs),
            failures=result.persistencia.falhas if result.persistencia is not None else 0,
            summary=_sumario(result),
        )
    except SQLAlchemyError as exc:
        erro = type(getattr(exc, "orig", None) or exc).__name__
        logger.error("Execução não registrada em collection_runs: %s", erro)
        logger.debug("Detalhe", exc_info=True)
        result.meta["erro_registro"] = f"execução não registrada em collection_runs ({erro})"
        result.exit_code = 1
