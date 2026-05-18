"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", name="userstatus"), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("best_of", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("scheduled", "completed", "cancelled", name="matchstatus"), nullable=False),
        sa.Column("winner_team", sa.String(length=1), nullable=True),
        sa.Column("elo_delta", sa.Float(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_matches_scheduled_at"), "matches", ["scheduled_at"], unique=False)
    op.create_index(op.f("ix_matches_status"), "matches", ["status"], unique=False)

    op.create_table(
        "match_players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("team", sa.String(length=1), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "user_id", name="uq_match_user"),
    )
    op.create_index(op.f("ix_match_players_match_id"), "match_players", ["match_id"], unique=False)
    op.create_index(op.f("ix_match_players_user_id"), "match_players", ["user_id"], unique=False)

    op.create_table(
        "set_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("team_a_games", sa.Integer(), nullable=False),
        sa.Column("team_b_games", sa.Integer(), nullable=False),
        sa.Column("team_a_tb", sa.Integer(), nullable=True),
        sa.Column("team_b_tb", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "set_number", name="uq_match_set"),
    )
    op.create_index(op.f("ix_set_scores_match_id"), "set_scores", ["match_id"], unique=False)


def downgrade() -> None:
    op.drop_table("set_scores")
    op.drop_table("match_players")
    op.drop_table("matches")
    op.drop_table("users")
