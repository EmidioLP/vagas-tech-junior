"""Tabelas do banco (SQLAlchemy 2.0).

Uma vaga guarda os mesmos campos que o CSV do scraper produz, com duas
diferencas:

  - `id` inteiro, gerado pelo banco, porque o CSV nao tem chave propria e a API
    precisa de uma URL estavel (`/vagas/{id}`). A identidade real da vaga
    continua sendo o par (source, external_id), que e UNIQUE.
  - as tecnologias saem da string "Excel, Python, SQL" e viram uma relacao
    muitos-para-muitos, que e o que permite filtrar e contar de verdade.

As tabelas historicas (`jobs`, `job_snapshots`) separam a identidade de uma vaga
dos estados observados a cada coleta. Veja docs/data-model.md.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

vaga_tecnologia = Table(
    "vaga_tecnologia",
    Base.metadata,
    Column("vaga_id", ForeignKey("vagas.id", ondelete="CASCADE"), primary_key=True),
    Column("tecnologia_id", ForeignKey("tecnologias.id", ondelete="CASCADE"),
           primary_key=True),
)


class Tecnologia(Base):
    __tablename__ = "tecnologias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    grupo: Mapped[str] = mapped_column(String(40), nullable=False)

    vagas: Mapped[list["Vaga"]] = relationship(
        secondary=vaga_tecnologia, back_populates="tecnologias"
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniencia no shell
        return f"<Tecnologia {self.nome}>"


class Vaga(Base):
    __tablename__ = "vagas"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_vaga_source_external_id"),
        Index("ix_vagas_area", "area"),
        Index("ix_vagas_workplace_type", "workplace_type"),
        Index("ix_vagas_source", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # 100: a GeekHunter publica o id como hash de 64 caracteres, e identidade nunca e cortada.
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(40), nullable=False)
    seniority: Mapped[str | None] = mapped_column(String(20))
    location: Mapped[str | None] = mapped_column(String(200))
    workplace_type: Mapped[str | None] = mapped_column(String(20))
    published_date: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    area_score: Mapped[float | None] = mapped_column(Float)
    area_matches: Mapped[str | None] = mapped_column(Text)
    search_term: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tecnologias: Mapped[list[Tecnologia]] = relationship(
        secondary=vaga_tecnologia, back_populates="vagas", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniencia no shell
        return f"<Vaga {self.id} {self.title[:40]!r}>"


# ---------------------------------------------------------------------------
# Historico: identidade da vaga separada dos estados observados em cada coleta.
# ---------------------------------------------------------------------------

job_snapshot_tecnologias = Table(
    "job_snapshot_tecnologias",
    Base.metadata,
    Column("snapshot_id", ForeignKey("job_snapshots.id", ondelete="CASCADE"),
           primary_key=True),
    # RESTRICT: remover uma tecnologia nao pode apagar historico em silencio.
    Column("tecnologia_id", ForeignKey("tecnologias.id", ondelete="RESTRICT"),
           primary_key=True),
)


class JobRecord(Base):
    """Identidade e ciclo de vida de uma vaga.

    Nada que possa mudar entre coletas fica aqui: titulo, descricao, area e
    modalidade pertencem ao snapshot. O nome evita colidir com a dataclass
    `scraper.models.Job`.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
        Index("ix_jobs_is_active", "is_active"),
        Index("ix_jobs_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # 100: a GeekHunter publica o id como hash de 64 caracteres, e identidade nunca e cortada.
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)
    # Primeira coleta completa (com a fonte ok) em que a vaga nao apareceu na
    # listagem; volta a nulo quando ela reaparece. Ausente de novo em outro dia, a
    # vaga e encerrada: `is_active = false` e `closed_at` com a data da coleta.
    # Veja persistence/repositorio.encerrar_ausentes.
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # passive_deletes="all": o ORM nao tenta anular job_id dos snapshots ao
    # apagar a vaga; quem decide e o RESTRICT do banco.
    snapshots: Mapped[list["JobSnapshot"]] = relationship(
        back_populates="job",
        order_by="JobSnapshot.collected_at",
        passive_deletes="all",
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniencia no shell
        return f"<JobRecord {self.source}:{self.external_id}>"


class JobSnapshot(Base):
    """Estado de uma vaga observado numa coleta."""

    __tablename__ = "job_snapshots"
    __table_args__ = (
        # No maximo um snapshot por vaga em cada coleta.
        UniqueConstraint("job_id", "collected_at", name="uq_job_snapshots_job_collected"),
        Index("ix_job_snapshots_collected_at", "collected_at"),
        Index("ix_job_snapshots_area", "area"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    workplace_type: Mapped[str | None] = mapped_column(String(20))
    published_date: Mapped[date | None] = mapped_column(Date)
    seniority: Mapped[str | None] = mapped_column(String(20))
    area: Mapped[str | None] = mapped_column(String(40))
    area_score: Mapped[float | None] = mapped_column(Float)
    area_matches: Mapped[str | None] = mapped_column(Text)
    # SHA-256 dos campos acima + tecnologias. Ver persistence/assinatura.py.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[JobRecord] = relationship(back_populates="snapshots")
    tecnologias: Mapped[list[Tecnologia]] = relationship(
        secondary=job_snapshot_tecnologias, lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniencia no shell
        return f"<JobSnapshot job={self.job_id} {self.collected_at:%Y-%m-%d}>"


# ---------------------------------------------------------------------------
# Controle: uma linha por execucao do pipeline com banco.
# ---------------------------------------------------------------------------


class CollectionRun(Base):
    """Uma execucao da coleta, feita ou pulada pela guarda de intervalo.

    E o que a guarda consulta (`persistence/execucoes.py`) e o registro auditavel
    de cada disparo, agendado, manual ou local. Veja docs/data-model.md.
    """

    __tablename__ = "collection_runs"
    __table_args__ = (
        Index("ix_collection_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # schedule / manual / local
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    # success / partial / failed / skipped
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    full_scope: Mapped[bool] = mapped_column(Boolean, nullable=False)
    interval_days: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    next_run_on: Mapped[date | None] = mapped_column(Date)
    jobs_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, nullable=False)
    # So contagens por fonte; nunca mensagens de erro.
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - conveniencia no shell
        return f"<CollectionRun {self.id} {self.status} {self.started_at:%Y-%m-%d}>"
