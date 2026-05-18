from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class LeagueMemberRole(str, enum.Enum):
    member = "member"
    admin = "admin"


class LeagueMemberStatus(str, enum.Enum):
    active = "active"
    pending_request = "pending_request"


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    memberships: Mapped[list["LeagueMember"]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )
    invites: Mapped[list["LeagueInvite"]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )
    matches: Mapped[list["Match"]] = relationship(back_populates="league")


class LeagueMember(Base):
    __tablename__ = "league_members"
    __table_args__ = (UniqueConstraint("league_id", "user_id", name="uq_league_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[LeagueMemberRole] = mapped_column(
        Enum(LeagueMemberRole), default=LeagueMemberRole.member
    )
    status: Mapped[LeagueMemberStatus] = mapped_column(
        Enum(LeagueMemberStatus), default=LeagueMemberStatus.active, index=True
    )
    rating: Mapped[float] = mapped_column(Float, default=1000.0)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    league: Mapped["League"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="league_memberships")


class LeagueInvite(Base):
    __tablename__ = "league_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    league: Mapped["League"] = relationship(back_populates="invites")
