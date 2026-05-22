import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MatchStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    best_of: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus), default=MatchStatus.scheduled, index=True
    )
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    winner_team: Mapped[str | None] = mapped_column(String(1), nullable=True)
    elo_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    ended_early: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    league: Mapped["League"] = relationship("League", back_populates="matches")
    season: Mapped["Season"] = relationship("Season", back_populates="matches")
    players: Mapped[list["MatchPlayer"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    set_scores: Mapped[list["SetScore"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="SetScore.set_number"
    )


class MatchPlayer(Base):
    __tablename__ = "match_players"
    __table_args__ = (UniqueConstraint("match_id", "user_id", name="uq_match_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    team: Mapped[str | None] = mapped_column(String(1), nullable=True)  # 'A' or 'B'

    match: Mapped["Match"] = relationship(back_populates="players")
    user: Mapped["User"] = relationship(back_populates="match_players")


