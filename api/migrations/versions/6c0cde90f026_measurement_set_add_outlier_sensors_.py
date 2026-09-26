"""measurement_set: add outlier_sensors column

Revision ID: 6c0cde90f026
Revises: 0553fd37cd2d
Create Date: 2026-07-20 22:55:41.371110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6c0cde90f026'
down_revision: Union[str, Sequence[str], None] = '0553fd37cd2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'measurementset',
        sa.Column(
            'outlier_sensors',
            postgresql.ARRAY(sa.Integer()),
            server_default='{}',
            nullable=False,
        ),
    )
    # The app sets outlier_sensors in Python on insert (default_factory=list), not via
    # a DB-level default — drop the server_default once existing rows are backfilled.
    op.alter_column('measurementset', 'outlier_sensors', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('measurementset', 'outlier_sensors')
