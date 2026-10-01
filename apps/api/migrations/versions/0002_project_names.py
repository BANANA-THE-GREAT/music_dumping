"""Add project and score naming metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("uploads", sa.Column("project_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("uploads", "project_name")
