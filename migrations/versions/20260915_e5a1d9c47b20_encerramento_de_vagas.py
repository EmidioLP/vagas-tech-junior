"""encerramento de vagas em jobs

Adiciona `jobs.missing_since` e `jobs.closed_at`, usados para encerrar vagas que
sumiram da listagem em duas coletas completas seguidas (`is_active = false`).
As duas colunas sao nulas: vagas existentes continuam ativas e sem ausencia. O
historico (`job_snapshots`) nao muda. Veja docs/data-model.md.

O downgrade remove apenas as duas colunas.

Revision ID: e5a1d9c47b20
Revises: c3b8f2d71e46
Create Date: 2026-09-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1d9c47b20'
down_revision: Union[str, Sequence[str], None] = 'c3b8f2d71e46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('missing_since', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.drop_column('closed_at')
        batch_op.drop_column('missing_since')
