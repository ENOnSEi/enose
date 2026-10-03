"""sample: add outlier_detection column

Revision ID: a3f1c9e2b7d4
Revises: 6c0cde90f026
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3f1c9e2b7d4'
down_revision: Union[str, Sequence[str], None] = '6c0cde90f026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable y sin default: las filas existentes quedan a NULL (= nunca etiquetado)
    op.add_column(
        'sample',
        sa.Column('outlier_detection', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sample', 'outlier_detection')
