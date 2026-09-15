"""baseline vagas tecnologias

Schema que a API ja criava com `Base.metadata.create_all`: vagas, tecnologias e
a associacao vaga_tecnologia. Nao redesenha nada. Bancos criados antes do
Alembic adotam esta revisao com `alembic stamp head` (docs/migrations.md).

Revision ID: 8426f7230fd1
Revises:
Create Date: 2026-09-15 13:47:20.579347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8426f7230fd1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tecnologias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=80), nullable=False),
        sa.Column('grupo', sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nome'),
    )
    op.create_table(
        'vagas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('external_id', sa.String(length=40), nullable=False),
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


def downgrade() -> None:
    op.drop_table('vaga_tecnologia')
    op.drop_index('ix_vagas_workplace_type', table_name='vagas')
    op.drop_index('ix_vagas_source', table_name='vagas')
    op.drop_index('ix_vagas_area', table_name='vagas')
    op.drop_table('vagas')
    op.drop_table('tecnologias')
