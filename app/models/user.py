import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), default=UserStatus.pending, index=True
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    placeholder_email_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    match_players: Mapped[list["MatchPlayer"]] = relationship(back_populates="user")
    league_memberships: Mapped[list["LeagueMember"]] = relationship(
        "LeagueMember", back_populates="user"
    )
