"""add fts_doc column and pg_trgm extension for full-text search

Revision ID: 540d6b34a445
Revises: 540d6b34a444
Create Date: 2026-07-08 05:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '540d6b34a445'
down_revision: Union[str, None] = '540d6b34a444'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add FTS tsvector column to authorities
    op.add_column('authorities', sa.Column('fts_doc', postgresql.TSVECTOR(), nullable=True))
    op.create_index('idx_authorities_fts', 'authorities', ['fts_doc'], postgresql_using='gin')

    # Install pg_trgm extension (IF NOT EXISTS avoids errors if already present)
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # Create trigram indexes for citation search
    op.create_index('idx_authorities_neutral_trgm', 'authorities', ['neutral_cite'],
                    postgresql_using='gin', postgresql_ops={'neutral_cite': 'gin_trgm_ops'})
    op.create_index('idx_authorities_reporter_trgm', 'authorities', ['reporter_cite'],
                    postgresql_using='gin', postgresql_ops={'reporter_cite': 'gin_trgm_ops'})


def downgrade() -> None:
    op.drop_index('idx_authorities_reporter_trgm', table_name='authorities')
    op.drop_index('idx_authorities_neutral_trgm', table_name='authorities')
    op.execute('DROP EXTENSION IF EXISTS pg_trgm')
    op.drop_index('idx_authorities_fts', table_name='authorities')
    op.drop_column('authorities', 'fts_doc')
