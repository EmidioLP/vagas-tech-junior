"""content hash em job snapshots

Adiciona `job_snapshots.content_hash`, a assinatura SHA-256 do estado gravado no
snapshot (`persistence/assinatura.py`). A persistencia compara o hash com o do
snapshot anterior para decidir se a coleta gera um snapshot novo.

A coluna entra com default '' so para aceitar linhas que ja existam; o default e
removido em seguida, para o schema bater com o modelo. Uma linha antiga com hash
vazio nunca casa com um hash real, entao a proxima coleta grava um snapshot novo
em vez de pular a vaga.

Revision ID: a61c3e2f9b04
Revises: d8ef8fde92b5
Create Date: 2026-09-15 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a61c3e2f9b04'
down_revision: Union[str, Sequence[str], None] = 'd8ef8fde92b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('job_snapshots') as batch_op:
        batch_op.add_column(
            sa.Column('content_hash', sa.String(length=64), server_default='', nullable=False)
        )
    with op.batch_alter_table('job_snapshots') as batch_op:
        batch_op.alter_column(
            'content_hash', existing_type=sa.String(length=64), server_default=None
        )


def downgrade() -> None:
    with op.batch_alter_table('job_snapshots') as batch_op:
        batch_op.drop_column('content_hash')
