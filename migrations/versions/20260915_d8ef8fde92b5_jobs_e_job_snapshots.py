"""jobs e job snapshots

Separa a identidade de uma vaga (`jobs`, unica por source + external_id) dos
estados observados a cada coleta (`job_snapshots`, no maximo um por vaga por
coleta). As FKs para `jobs` e `tecnologias` usam RESTRICT: apagar uma vaga ou
uma tecnologia nao pode apagar historico em silencio. Veja docs/data-model.md.

O downgrade remove apenas estas tres tabelas; a baseline fica intacta.

Revision ID: d8ef8fde92b5
Revises: 8426f7230fd1
Create Date: 2026-09-15 13:59:57.155178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8ef8fde92b5'
down_revision: Union[str, Sequence[str], None] = '8426f7230fd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('external_id', sa.String(length=40), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'external_id', name='uq_jobs_source_external_id'),
    )
    op.create_index('ix_jobs_is_active', 'jobs', ['is_active'], unique=False)
    op.create_index('ix_jobs_last_seen_at', 'jobs', ['last_seen_at'], unique=False)

    op.create_table(
        'job_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('company', sa.String(length=200), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('workplace_type', sa.String(length=20), nullable=True),
        sa.Column('published_date', sa.Date(), nullable=True),
        sa.Column('seniority', sa.String(length=20), nullable=True),
        sa.Column('area', sa.String(length=40), nullable=True),
        sa.Column('area_score', sa.Float(), nullable=True),
        sa.Column('area_matches', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'collected_at', name='uq_job_snapshots_job_collected'),
    )
    op.create_index('ix_job_snapshots_area', 'job_snapshots', ['area'], unique=False)
    op.create_index(
        'ix_job_snapshots_collected_at', 'job_snapshots', ['collected_at'], unique=False
    )

    op.create_table(
        'job_snapshot_tecnologias',
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('tecnologia_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['snapshot_id'], ['job_snapshots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tecnologia_id'], ['tecnologias.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('snapshot_id', 'tecnologia_id'),
    )


def downgrade() -> None:
    op.drop_table('job_snapshot_tecnologias')
    op.drop_index('ix_job_snapshots_collected_at', table_name='job_snapshots')
    op.drop_index('ix_job_snapshots_area', table_name='job_snapshots')
    op.drop_table('job_snapshots')
    op.drop_index('ix_jobs_last_seen_at', table_name='jobs')
    op.drop_index('ix_jobs_is_active', table_name='jobs')
    op.drop_table('jobs')
