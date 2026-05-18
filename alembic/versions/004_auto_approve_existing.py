"""auto-approve existing pending users

Revision ID: 004
Revises: 003
Create Date: 2026-05-18

Anyone can register and use the site now; per-league approval is the
gatekeeping mechanism. Any users who registered while the old "pending until
site-admin approves" flow was active get auto-approved so they're not stuck.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET status = 'approved' WHERE status = 'pending'")


def downgrade() -> None:
    # Not reversible — we can't tell which users were originally pending.
    pass
