"""external id com 100 caracteres

Alarga `jobs.external_id` e `vagas.external_id` de VARCHAR(40) para VARCHAR(100).
A GeekHunter passou a publicar o `identifier` do JobPosting como hash de 64
caracteres: na coleta real de 15/09/2026, as 36 vagas dela falharam com
"external_id com mais de 40 caracteres", e o seed (35 linhas da GeekHunter) nao
entraria num PostgreSQL. O id nunca e cortado: um id truncado viraria outra vaga.

No PostgreSQL, alargar VARCHAR so muda metadado. O downgrade volta para 40 e
falha se ja houver ids maiores gravados, de proposito: cortar identidade em
silencio seria pior.

Revision ID: b7d2e4f19a63
Revises: e5a1d9c47b20
Create Date: 2026-09-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2e4f19a63'
down_revision: Union[str, Sequence[str], None] = 'e5a1d9c47b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELAS = ('jobs', 'vagas')


def upgrade() -> None:
    for tabela in TABELAS:
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.alter_column(
                'external_id',
                existing_type=sa.String(length=40),
                type_=sa.String(length=100),
                existing_nullable=False,
            )


def downgrade() -> None:
    for tabela in TABELAS:
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.alter_column(
                'external_id',
                existing_type=sa.String(length=100),
                type_=sa.String(length=40),
                existing_nullable=False,
            )
