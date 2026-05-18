from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SetScore(Base):
    __tablename__ = "set_scores"
    __table_args__ = (UniqueConstraint("match_id", "set_number", name="uq_match_set"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    set_number: Mapped[int] = mapped_column(Integer)
    team_a_games: Mapped[int] = mapped_column(Integer)
    team_b_games: Mapped[int] = mapped_column(Integer)
    team_a_tb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team_b_tb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match: Mapped["Match"] = relationship(back_populates="set_scores")


from app.models.match import Match  # noqa: E402

