#!/usr/bin/env python3
"""Replay completed matches to recalculate ELO ratings.

Use after fixing the finalize stale-collection bug, or whenever ratings need
to be rebuilt from match history.

Examples:
    python scripts/recompute_elo.py
    python scripts/recompute_elo.py --league-id 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as: python scripts/recompute_elo.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.services.elo import recompute_all_leagues_elo, recompute_league_elo


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay completed matches to rebuild ELO ratings.")
    parser.add_argument(
        "--league-id",
        type=int,
        default=None,
        help="Recompute a single league (default: all leagues)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.league_id is not None:
            recompute_league_elo(db, args.league_id)
            scope = f"league {args.league_id}"
        else:
            recompute_all_leagues_elo(db)
            scope = "all leagues"
        db.commit()
        print(f"ELO recompute complete for {scope}.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ELO recompute failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
