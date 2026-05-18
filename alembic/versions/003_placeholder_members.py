"""placeholder member users

Revision ID: 003
Revises: 002
Create Date: 2026-05-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_placeholder",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("placeholder_email_hint", sa.String(length=255), nullable=True)
        )
    op.create_index(
        op.f("ix_users_is_placeholder"), "users", ["is_placeholder"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_is_placeholder"), table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("placeholder_email_hint")
        batch_op.drop_column("is_placeholder")
