"""Phase 11d: network_invite.revoked_at / revoked_by (spec/data-model.md §network_invite).

Both nullable, no backfill; downgrade drops them. Does not import app code.

Revision ID: 0009
Revises: 0008
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("network_invite") as batch:
        batch.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("revoked_by", sa.String(length=254), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("network_invite") as batch:
        batch.drop_column("revoked_by")
        batch.drop_column("revoked_at")
