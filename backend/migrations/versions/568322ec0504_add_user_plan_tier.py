"""add user plan tier

Adds ``users.plan`` with a CHECK constraint and a server default so existing rows
are backfilled in the same statement. Safe to run on a live table: one nullable-then-
defaulted VARCHAR, no rewrite of user data.

The limits themselves are not stored here - they live in ``app/safety/plans.py`` so
changing a tier's allowance never needs a migration.

Revision ID: 568322ec0504
Revises: 0e3a0c7ed6c4
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "568322ec0504"
down_revision: Union[str, Sequence[str], None] = "0e3a0c7ed6c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan", sa.String(length=16), nullable=False, server_default="regular"),
    )
    op.create_check_constraint(
        "ck_users_plan_valid",
        "users",
        "plan IN ('regular', 'pro', 'pro_plus')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_plan_valid", "users", type_="check")
    op.drop_column("users", "plan")