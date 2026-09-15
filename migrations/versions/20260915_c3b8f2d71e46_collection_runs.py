"""collection runs

Adiciona `collection_runs`, a tabela de controle da coleta: uma linha por
execucao do pipeline com banco, inclusive as puladas pela guarda de intervalo.
A guarda consulta a ultima coleta completa bem-sucedida aqui. Nao tem FK para as
outras tabelas. Veja docs/data-model.md e docs/automation.md.

O downgrade remove apenas esta tabela.

Revision ID: c3b8f2d71e46
Revises: a61c3e2f9b04
Create Date: 2026-09-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3b8f2d71e46'
down_revision: Union[str, Sequence[str], None] = 'a61c3e2f9b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'collection_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('triggered_by', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('full_scope', sa.Boolean(), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('next_run_on', sa.Date(), nullable=True),
        sa.Column('jobs_count', sa.Integer(), nullable=False),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_collection_runs_status_started_at', 'collection_runs',
        ['status', 'started_at'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_collection_runs_status_started_at', table_name='collection_runs')
    op.drop_table('collection_runs')
