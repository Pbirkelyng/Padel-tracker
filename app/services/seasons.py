"""Season lifecycle: end season with soft ELO reset."""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import League, LeagueMember, Season


def end_current_season(db: Session, league: League) -> Season:
    current = db.scalar(
        select(Season).where(Season.league_id == league.id, Season.is_current.is_(True))
    )
    if not current:
        raise ValueError("No current season")

    members = db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    snapshot = {str(m.user_id): m.rating for m in members}
    current.final_ratings_json = json.dumps(snapshot)
    current.ended_at = datetime.utcnow()
    current.is_current = False

    settings = get_settings()
    default = settings.default_rating
    for m in members:
        m.rating = (m.rating + default) / 2

    prev_count = db.scalar(
        select(func.count()).select_from(Season).where(Season.league_id == league.id)
    )
    next_num = int(prev_count or 0) + 1
    new_season = Season(league_id=league.id, name=f"Season {next_num}", is_current=True)
    db.add(new_season)
    db.flush()
    return new_season
