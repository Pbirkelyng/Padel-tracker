"""leagues seasons league members invites match scope

Revision ID: 002
Revises: 001
Create Date: 2026-05-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

member_role = sa.Enum("member", "admin", name="leaguememberrole", native_enum=False, length=16)
member_status = sa.Enum(
    "active", "pending_request", name="leaguememberstatus", native_enum=False, length=20
)


def upgrade() -> None:
    member_role.create(op.get_bind(), checkfirst=True)
    member_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_leagues_slug"), "leagues", ["slug"], unique=True)

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("final_ratings_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_seasons_league_id"), "seasons", ["league_id"], unique=False)
    op.create_index(op.f("ix_seasons_is_current"), "seasons", ["is_current"], unique=False)

    op.create_table(
        "league_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", member_role, nullable=False, server_default="member"),
        sa.Column("status", member_status, nullable=False, server_default="active"),
        sa.Column("rating", sa.Float(), nullable=False, server_default="1000"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("league_id", "user_id", name="uq_league_user"),
    )
    op.create_index(op.f("ix_league_members_league_id"), "league_members", ["league_id"], unique=False)
    op.create_index(op.f("ix_league_members_user_id"), "league_members", ["user_id"], unique=False)
    op.create_index(op.f("ix_league_members_status"), "league_members", ["status"], unique=False)

    op.create_table(
        "league_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("accepted_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["accepted_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_league_invites_league_id"), "league_invites", ["league_id"], unique=False)
    op.create_index(op.f("ix_league_invites_token"), "league_invites", ["token"], unique=True)

    with op.batch_alter_table("matches") as batch_op:
        batch_op.add_column(sa.Column("league_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("season_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    first_uid = bind.execute(sa.text("SELECT id FROM users ORDER BY id ASC LIMIT 1")).scalar()
    if first_uid is None:
        first_uid = 1

    league_id = bind.execute(
        sa.text(
            "INSERT INTO leagues (name, slug, description, is_public, created_by_id) "
            "VALUES ('Default League', 'default', '', TRUE, :uid) RETURNING id"
        ),
        {"uid": first_uid},
    ).scalar()

    season_id = bind.execute(
        sa.text(
            "INSERT INTO seasons (league_id, name, is_current) "
            "VALUES (:lid, 'Season 1', TRUE) RETURNING id"
        ),
        {"lid": league_id},
    ).scalar()

    bind.execute(
        sa.text("UPDATE matches SET league_id = :lid, season_id = :sid WHERE league_id IS NULL"),
        {"lid": league_id, "sid": season_id},
    )

    users_rows = bind.execute(
        sa.text("SELECT id, rating, is_admin FROM users WHERE status = 'approved'")
    ).fetchall()
    for uid, rating, is_admin in users_rows:
        role = "admin" if is_admin else "member"
        bind.execute(
            sa.text(
                "INSERT INTO league_members (league_id, user_id, role, status, rating, is_pinned) "
                "VALUES (:lid, :uid, :role, 'active', :rating, FALSE)"
            ),
            {"lid": league_id, "uid": uid, "role": role, "rating": rating or 1000.0},
        )

    with op.batch_alter_table("matches") as batch_op:
        batch_op.alter_column("league_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("season_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_matches_league_id", "leagues", ["league_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_foreign_key(
            "fk_matches_season_id", "seasons", ["season_id"], ["id"], ondelete="CASCADE"
        )
    op.create_index(op.f("ix_matches_league_id"), "matches", ["league_id"], unique=False)
    op.create_index(op.f("ix_matches_season_id"), "matches", ["season_id"], unique=False)

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("rating")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("rating", sa.Float(), nullable=False, server_default="1000"))

    bind = op.get_bind()
    for row in bind.execute(sa.text("SELECT user_id, rating FROM league_members WHERE league_id = 1")).fetchall():
        uid, r = row
        bind.execute(sa.text("UPDATE users SET rating = :r WHERE id = :uid"), {"r": r, "uid": uid})

    op.drop_index(op.f("ix_matches_season_id"), table_name="matches")
    op.drop_index(op.f("ix_matches_league_id"), table_name="matches")
    with op.batch_alter_table("matches") as batch_op:
        batch_op.drop_constraint("fk_matches_season_id", type_="foreignkey")
        batch_op.drop_constraint("fk_matches_league_id", type_="foreignkey")
        batch_op.drop_column("season_id")
        batch_op.drop_column("league_id")

    op.drop_index(op.f("ix_league_invites_token"), table_name="league_invites")
    op.drop_index(op.f("ix_league_invites_league_id"), table_name="league_invites")
    op.drop_table("league_invites")

    op.drop_index(op.f("ix_league_members_status"), table_name="league_members")
    op.drop_index(op.f("ix_league_members_user_id"), table_name="league_members")
    op.drop_index(op.f("ix_league_members_league_id"), table_name="league_members")
    op.drop_table("league_members")

    op.drop_index(op.f("ix_seasons_is_current"), table_name="seasons")
    op.drop_index(op.f("ix_seasons_league_id"), table_name="seasons")
    op.drop_table("seasons")

    op.drop_index(op.f("ix_leagues_slug"), table_name="leagues")
    op.drop_table("leagues")

    member_role.drop(op.get_bind(), checkfirst=True)
    member_status.drop(op.get_bind(), checkfirst=True)
