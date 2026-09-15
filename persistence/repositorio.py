"""Gravacao idempotente das vagas processadas em `jobs` e `job_snapshots`.

Regras (detalhes em docs/data-model.md, secao "Persistência"):

- **Identidade.** Uma vaga e o par (source, external_id). A constraint
  `uq_jobs_source_external_id` decide no fim: a insercao usa ON CONFLICT, entao
  duas execucoes concorrentes nao duplicam a vaga. A deduplicacao em memoria do
  pipeline reduz ruido, mas nao e o que garante a integridade.
- **Ciclo de vida.** Vaga vista: `last_seen_at` avanca (nunca retrocede),
  `first_seen_at` so recua e `is_active` volta a true. Nenhuma vaga e desativada
  aqui: uma coleta parcial (`--sources gupy`, termo que falhou) desativaria vagas
  abertas.
- **Snapshot.** So e gravado se a assinatura (`persistence/assinatura.py`) difere
  da do snapshot anterior. Se ja existe snapshot desta vaga nesta coleta, nada e
  gravado: no maximo um por coleta, mesmo que a vaga venha repetida na entrada.
- **Transacoes.** Uma por fonte, com SAVEPOINT por vaga. Erro de dado numa vaga
  desfaz so ela (vaga, snapshot e tecnologias juntos); erro de banco na fonte
  desfaz a fonte inteira. Fontes ja confirmadas nunca sao afetadas.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from api import vocabulary
from api.dates import parse_published_date
from api.models import JobRecord, JobSnapshot, Tecnologia
from scraper.models import Job

from .assinatura import assinatura_snapshot

logger = logging.getLogger(__name__)

# Insert com ON CONFLICT existe por dialeto; o projeto usa estes dois.
_INSERTS = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}

# Erros que dizem respeito a uma vaga so. Qualquer outro SQLAlchemyError (conexao
# caiu, commit falhou) desfaz a fonte inteira.
_ERROS_DA_VAGA = (IntegrityError, DataError, ValueError)

CAMPOS_TEXTO = (
    "title", "company", "description", "location", "workplace_type",
    "seniority", "area", "area_matches",
)


def _limite(tabela, coluna: str) -> int | None:
    return getattr(tabela.c[coluna].type, "length", None)


@dataclass
class ResumoFonte:
    jobs_criados: int = 0
    jobs_atualizados: int = 0
    snapshots_criados: int = 0
    snapshots_ignorados: int = 0
    falhas: int = 0


@dataclass
class ResumoPersistencia:
    """Contagens de uma execucao, por fonte e no total."""

    por_fonte: dict[str, ResumoFonte] = field(default_factory=dict)
    # "fonte:id: TipoDoErro". Nunca inclui a URL do banco.
    erros: list[str] = field(default_factory=list)

    def _somar(self, campo: str) -> int:
        return sum(getattr(r, campo) for r in self.por_fonte.values())

    @property
    def jobs_criados(self) -> int:
        return self._somar("jobs_criados")

    @property
    def jobs_atualizados(self) -> int:
        return self._somar("jobs_atualizados")

    @property
    def snapshots_criados(self) -> int:
        return self._somar("snapshots_criados")

    @property
    def snapshots_ignorados(self) -> int:
        return self._somar("snapshots_ignorados")

    @property
    def falhas(self) -> int:
        return self._somar("falhas")

    def como_dict(self) -> dict:
        return {
            "jobs_criados": self.jobs_criados,
            "jobs_atualizados": self.jobs_atualizados,
            "snapshots_criados": self.snapshots_criados,
            "snapshots_ignorados": self.snapshots_ignorados,
            "falhas": self.falhas,
            "por_fonte": {f: asdict(r) for f, r in self.por_fonte.items()},
            "erros": list(self.erros),
        }


def semear_tecnologias(db: Session) -> dict[str, Tecnologia]:
    """Garante uma linha para cada tecnologia de skills.yml."""
    existentes = {t.nome: t for t in db.scalars(select(Tecnologia))}
    for nome, grupo in vocabulary.technologies().items():
        atual = existentes.get(nome)
        if atual is None:
            atual = Tecnologia(nome=nome, grupo=grupo)
            db.add(atual)
            existentes[nome] = atual
        elif atual.grupo != grupo:
            atual.grupo = grupo
    db.flush()
    return existentes


def _utc(momento: datetime) -> datetime:
    """O SQLite devolve datetime sem fuso; o valor gravado ja esta em UTC."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _texto(valor: str | None, coluna: str) -> str | None:
    """Apara e corta no tamanho da coluna. Vazio vira None."""
    valor = (valor or "").strip()
    if not valor:
        return None
    limite = _limite(JobSnapshot.__table__, coluna)
    return valor[:limite] if limite else valor


def campos_snapshot(job: Job, collected_at: datetime) -> dict:
    """Os campos do snapshot, exatamente como serao gravados (e assinados)."""
    campos = {coluna: _texto(getattr(job, coluna), coluna) for coluna in CAMPOS_TEXTO}
    if campos["title"] is None:
        raise ValueError("vaga sem título")
    # Datas relativas ("Há 3 dias") so fazem sentido contra o dia da coleta.
    campos["published_date"] = parse_published_date(
        job.published_date, collected_at.astimezone().date()
    )
    campos["area_score"] = float(job.area_score) if job.area_score is not None else None
    return campos


def _validar_identidade(job: Job) -> None:
    """Identidade nunca e cortada: um id truncado viraria outra vaga."""
    for coluna in ("source", "external_id"):
        valor = getattr(job, coluna) or ""
        if not valor.strip():
            raise ValueError(f"{coluna} vazio")
        limite = _limite(JobRecord.__table__, coluna)
        if limite and len(valor) > limite:
            raise ValueError(f"{coluna} com mais de {limite} caracteres")


def _upsert_job(db: Session, insert, job: Job, collected_at: datetime) -> tuple[JobRecord, bool]:
    """Devolve (vaga, criada). A constraint do banco e a palavra final."""
    filtro = (JobRecord.source == job.source, JobRecord.external_id == job.external_id)
    url = (job.url or "").strip() or None

    registro = db.scalar(select(JobRecord).where(*filtro))
    if registro is None:
        novo_id = db.scalar(
            insert(JobRecord)
            .values(
                source=job.source, external_id=job.external_id, url=url,
                first_seen_at=collected_at, last_seen_at=collected_at, is_active=True,
            )
            .on_conflict_do_nothing(index_elements=["source", "external_id"])
            .returning(JobRecord.id)
        )
        if novo_id is not None:
            return db.get(JobRecord, novo_id), True
        # Outra execucao inseriu a mesma vaga entre o SELECT e o INSERT.
        registro = db.scalar(select(JobRecord).where(*filtro))
        if registro is None:  # pragma: no cover - so com a constraint violada
            raise IntegrityError("upsert de jobs sem linha", None, Exception())

    if url and registro.url != url:
        registro.url = url
    if collected_at > _utc(registro.last_seen_at):
        registro.last_seen_at = collected_at
    if collected_at < _utc(registro.first_seen_at):
        registro.first_seen_at = collected_at
    if not registro.is_active:
        registro.is_active = True
    return registro, False


def _gravar_snapshot(
    db: Session,
    registro: JobRecord,
    campos: dict,
    tecnologias: list[Tecnologia],
    collected_at: datetime,
) -> bool:
    """Grava o snapshot se o estado mudou. Devolve True se gravou."""
    assinatura = assinatura_snapshot({**campos, "tecnologias": [t.nome for t in tecnologias]})
    anterior = db.execute(
        select(JobSnapshot.collected_at, JobSnapshot.content_hash)
        .where(JobSnapshot.job_id == registro.id, JobSnapshot.collected_at <= collected_at)
        .order_by(JobSnapshot.collected_at.desc())
        .limit(1)
    ).first()
    if anterior is not None and (
        _utc(anterior.collected_at) == collected_at or anterior.content_hash == assinatura
    ):
        return False

    db.add(JobSnapshot(
        job_id=registro.id, collected_at=collected_at, content_hash=assinatura,
        tecnologias=tecnologias, **campos,
    ))
    db.flush()
    return True


def _gravar_vaga(
    db: Session,
    insert,
    job: Job,
    conhecidas: dict[str, Tecnologia],
    collected_at: datetime,
) -> tuple[bool, bool]:
    """Vaga + snapshot. Devolve (vaga criada, snapshot criado)."""
    _validar_identidade(job)
    campos = campos_snapshot(job, collected_at)
    tecnologias = [conhecidas[n] for n in dict.fromkeys(job.skills) if n in conhecidas]

    registro, criada = _upsert_job(db, insert, job, collected_at)
    db.flush()
    return criada, _gravar_snapshot(db, registro, campos, tecnologias, collected_at)


def _nome_erro(exc: BaseException) -> str:
    """So o tipo: a mensagem de erro de banco pode carregar dados da conexao."""
    if isinstance(exc, ValueError):
        return f"ValueError: {exc}"
    original = getattr(exc, "orig", None)
    return type(original or exc).__name__


def _persistir_fonte(
    engine: Engine, insert, fonte: str, vagas: list[Job], collected_at: datetime,
) -> tuple[ResumoFonte, list[str]]:
    resumo = ResumoFonte()
    erros: list[str] = []

    with Session(engine) as db, db.begin():
        conhecidas = {t.nome: t for t in db.scalars(select(Tecnologia))}
        for job in vagas:
            try:
                with db.begin_nested():
                    criada, snapshot = _gravar_vaga(db, insert, job, conhecidas, collected_at)
            except _ERROS_DA_VAGA as exc:
                resumo.falhas += 1
                erros.append(f"{job.source}:{job.external_id}: {_nome_erro(exc)}")
                logger.warning("Vaga não gravada (%s): %s", job.source_key, _nome_erro(exc))
                logger.debug("Detalhe", exc_info=True)
                continue

            if criada:
                resumo.jobs_criados += 1
            else:
                resumo.jobs_atualizados += 1
            if snapshot:
                resumo.snapshots_criados += 1
            else:
                resumo.snapshots_ignorados += 1

    return resumo, erros


def persistir_vagas(
    jobs: Iterable[Job], engine: Engine, collected_at: datetime,
) -> ResumoPersistencia:
    """Grava as vagas processadas de uma coleta. Reexecutar e seguro.

    `collected_at` precisa ter fuso: e o mesmo instante para todas as vagas da
    execucao, e e ele que torna a mesma coleta reconhecivel ao rodar de novo.
    """
    if collected_at.tzinfo is None:
        raise ValueError("collected_at precisa ter fuso horário")
    collected_at = collected_at.astimezone(timezone.utc)

    insert = _INSERTS.get(engine.dialect.name)
    if insert is None:
        raise ValueError(f"Banco não suportado pela persistência: {engine.dialect.name}")

    por_fonte: dict[str, list[Job]] = {}
    for job in jobs:
        por_fonte.setdefault(job.source, []).append(job)

    resumo = ResumoPersistencia()
    if not por_fonte:
        return resumo

    with Session(engine) as db, db.begin():
        semear_tecnologias(db)

    for fonte, vagas in por_fonte.items():
        try:
            parcial, erros = _persistir_fonte(engine, insert, fonte, vagas, collected_at)
        except SQLAlchemyError as exc:
            # Nada desta fonte foi confirmado; as anteriores continuam gravadas.
            parcial = ResumoFonte(falhas=len(vagas))
            erros = [f"{fonte}: transação desfeita ({_nome_erro(exc)})"]
            logger.error("Fonte %s não gravada, transação desfeita: %s", fonte, _nome_erro(exc))
            logger.debug("Detalhe", exc_info=True)

        resumo.por_fonte[fonte] = parcial
        resumo.erros.extend(erros)
        logger.info(
            "%s: %d vagas criadas, %d atualizadas, %d snapshots novos, %d sem mudança, %d falhas",
            fonte, parcial.jobs_criados, parcial.jobs_atualizados,
            parcial.snapshots_criados, parcial.snapshots_ignorados, parcial.falhas,
        )

    return resumo
