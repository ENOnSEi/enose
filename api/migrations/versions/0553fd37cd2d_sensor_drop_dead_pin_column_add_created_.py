"""sensor: drop dead pin column, add created_at and retired_at

Revision ID: 0553fd37cd2d
Revises: 
Create Date: 2026-07-16 18:28:59.678831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0553fd37cd2d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sensor',
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.add_column('sensor', sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True))
    # The app sets created_at in Python on insert (default_factory), not via a
    # DB-level default — drop the server_default once existing rows are backfilled.
    op.alter_column('sensor', 'created_at', server_default=None)
    op.drop_column('sensor', 'pin')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'sensor',
        sa.Column(
            'pin',
            sa.VARCHAR(length=10),
            autoincrement=False,
            nullable=False,
            server_default='',
        ),
    )
    op.alter_column('sensor', 'pin', server_default=None)
    op.drop_column('sensor', 'retired_at')
    op.drop_column('sensor', 'created_at')
