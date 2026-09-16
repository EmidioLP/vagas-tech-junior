"""remove tabelas legadas

Apaga `vagas` e `vaga_tecnologia`, o espelho do CSV que a API lia antes de passar
a ler o historico (etapa 09). Nada mais le nem escreve nessas tabelas. `tecnologias`
fica: `job_snapshot_tecnologias` a referencia.

**O downgrade nao devolve dados.** Ele recria as duas tabelas vazias, com o schema
de antes (inclusive `external_id` com 100 caracteres). Para recuperar o conteudo
de um banco real, use a branch Neon de backup criada antes do upgrade
(docs/neon-setup.md).

Revision ID: 85084f63871c
Revises: b7d2e4f19a63
Create Date: 2026-09-16 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85084f63871c'
down_revision: Union[str, Sequence[str], None] = 'b7d2e4f19a63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('vaga_tecnologia')
    op.drop_index('ix_vagas_workplace_type', table_name='vagas')
    op.drop_index('ix_vagas_source', table_name='vagas')
    op.drop_index('ix_vagas_area', table_name='vagas')
    op.drop_table('vagas')


def downgrade() -> None:
    op.create_table(
        'vagas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('external_id', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('company', sa.String(length=200), nullable=True),
        sa.Column('area', sa.String(length=40), nullable=False),
        sa.Column('seniority', sa.String(length=20), nullable=True),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('workplace_type', sa.String(length=20), nullable=True),
        sa.Column('published_date', sa.Date(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('area_score', sa.Float(), nullable=True),
        sa.Column('area_matches', sa.Text(), nullable=True),
        sa.Column('search_term', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'external_id', name='uq_vaga_source_external_id'),
    )
    op.create_index('ix_vagas_area', 'vagas', ['area'], unique=False)
    op.create_index('ix_vagas_source', 'vagas', ['source'], unique=False)
    op.create_index('ix_vagas_workplace_type', 'vagas', ['workplace_type'], unique=False)

    op.create_table(
        'vaga_tecnologia',
        sa.Column('vaga_id', sa.Integer(), nullable=False),
        sa.Column('tecnologia_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['tecnologia_id'], ['tecnologias.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vaga_id'], ['vagas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('vaga_id', 'tecnologia_id'),
    )
