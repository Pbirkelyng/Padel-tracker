import json

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import ApprovedUser
from app.league_helpers import get_active_membership, is_league_admin, nav_pending_for_league
from app.models import (
    LeagueMember,
    LeagueMemberStatus,
    Match,
    MatchPlayer,
    MatchStatus,
    SetScore,
    UserStatus,
)
from app.services.elo import apply_elo_for_match, compute_elo_delta, reverse_elo_for_match
from app.services.scoring import (
    VALID_SET_SCORES,
    SetInput,
    sets_needed_to_win,
    validate_match_scores,
)
from app.templating import templates

router = APIRouter(tags=["matches"])


def _load_match(db: Session, match_id: int) -> Match | None:
    return db.scalars(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.players).selectinload(MatchPlayer.user),
            selectinload(Match.set_scores),
            selectinload(Match.created_by),
            selectinload(Match.league),
            selectinload(Match.season),
        )
    ).first()


def _team_counts(players: list[MatchPlayer]) -> tuple[int, int]:
    a = sum(1 for p in players if p.team == "A")
    b = sum(1 for p in players if p.team == "B")
    return a, b


def _league_membership_for_user(db: Session, league_id: int, user_id: int) -> LeagueMember | None:
    return get_active_membership(db, league_id, user_id)


@router.get("/matches/{match_id}", response_class=HTMLResponse)
def match_detail(
    request: Request,
    match_id: int,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    error: str | None = Query(None),
    success: str | None = Query(None),
):
    match = _load_match(db, match_id)
    if not match:
        return RedirectResponse("/", status_code=303)

    mem = _league_membership_for_user(db, match.league_id, user.id)
    if not mem:
        return RedirectResponse("/", status_code=303)

    team_a = [p for p in match.players if p.team == "A"]
    team_b = [p for p in match.players if p.team == "B"]
    unassigned = [p for p in match.players if p.team is None]

    league_slug = match.league.slug if match.league else "default"
    league_admin = is_league_admin(mem)
    sets_needed = sets_needed_to_win(match.best_of)
    valid_set_pairs_json = json.dumps(sorted(VALID_SET_SCORES))
    can_manage = (
        match.status == MatchStatus.scheduled and (user.is_admin or match.created_by_id == user.id or league_admin)
    )
    can_finalize = can_manage
    can_reopen_completed = user.is_admin or league_admin

    player_ratings: dict[int, float] = {}
    for mp in match.players:
        lm = db.scalar(
            select(LeagueMember).where(
                LeagueMember.league_id == match.league_id,
                LeagueMember.user_id == mp.user_id,
            )
        )
        player_ratings[mp.user_id] = lm.rating if lm else 1000.0

    # League members not already on the match — admins/creators can add them
    # while the match is still scheduled.
    addable_members: list[LeagueMember] = []
    if can_manage and len(match.players) < 4:
        existing_ids = {p.user_id for p in match.players}
        addable_members = list(
            db.scalars(
                select(LeagueMember)
                .where(
                    LeagueMember.league_id == match.league_id,
                    LeagueMember.status == LeagueMemberStatus.active,
                )
                .options(selectinload(LeagueMember.user))
                .order_by(LeagueMember.joined_at)
            ).all()
        )
        addable_members = [
            m
            for m in addable_members
            if m.user_id not in existing_ids and m.user.status == UserStatus.approved
        ]

    # Any active member who isn't already on a scheduled match with open
    # slots can sign themselves up.
    user_on_match = any(p.user_id == user.id for p in match.players)
    can_self_join = (
        match.status == MatchStatus.scheduled
        and not user_on_match
        and len(match.players) < 4
    )

    return templates.TemplateResponse(
        request,
        "matches/detail.html",
        {
            "user": user,
            "match": match,
            "team_a": team_a,
            "team_b": team_b,
            "unassigned": unassigned,
            "error": error,
            "success": success,
            "league_slug": league_slug,
            "can_edit": can_manage,
            "can_reopen_completed": can_reopen_completed,
            "can_manage_teams": match.status == MatchStatus.scheduled,
            "can_manage_scores": match.status == MatchStatus.scheduled and can_manage,
            "can_manage_roster": can_manage,
            "can_self_join": can_self_join,
            "player_ratings": player_ratings,
            "addable_members": addable_members,
            "sets_needed": sets_needed,
            "valid_set_pairs_json": valid_set_pairs_json,
            "nav_members_pending": nav_pending_for_league(db, match.league, user.id),
        },
    )


@router.post("/matches/{match_id}/players")
def add_player_to_match(
    match_id: int,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    player_id: int = Form(...),
):
    match = _load_match(db, match_id)
    if not match:
        return RedirectResponse("/", status_code=303)
    mem = _league_membership_for_user(db, match.league_id, user.id)
    if not mem or match.status != MatchStatus.scheduled:
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    is_creator_or_admin = (
        user.is_admin or match.created_by_id == user.id or is_league_admin(mem)
    )
    is_self_add = player_id == user.id
    # Non-admin members can add themselves (sign up for a match). Admins,
    # match creators, and site admins can add anyone.
    if not is_creator_or_admin and not is_self_add:
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    if len(match.players) >= 4:
        return RedirectResponse(
            f"/matches/{match_id}?error=Maximum+4+players+per+match",
            status_code=303,
        )

    # Validate the candidate is an active member of this league.
    target_membership = get_active_membership(db, match.league_id, player_id)
    if not target_membership:
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    if any(p.user_id == player_id for p in match.players):
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    db.add(MatchPlayer(match_id=match.id, user_id=player_id, team=None))
    db.commit()
    return RedirectResponse(f"/matches/{match_id}", status_code=303)


@router.post("/matches/{match_id}/players/{player_id}/remove")
def remove_player_from_match(
    match_id: int,
    player_id: int,
    user: ApprovedUser,
    db: Session = Depends(get_db),
):
    match = _load_match(db, match_id)
    if not match:
        return RedirectResponse("/", status_code=303)
    mem = _league_membership_for_user(db, match.league_id, user.id)
    if not mem or match.status != MatchStatus.scheduled:
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    is_creator_or_admin = (
        user.is_admin or match.created_by_id == user.id or is_league_admin(mem)
    )
    if not is_creator_or_admin:
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    # Never let the match end up with zero players (re-create one instead).
    if len(match.players) <= 1:
        return RedirectResponse(
            f"/matches/{match_id}?error=A+match+needs+at+least+one+player",
            status_code=303,
        )

    mp = next((p for p in match.players if p.user_id == player_id), None)
    if mp:
        db.delete(mp)
        db.commit()
    return RedirectResponse(f"/matches/{match_id}", status_code=303)
@router.post("/matches/{match_id}/teams/{player_id}")
def assign_single_team(
    match_id: int,
    player_id: int,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    team: str = Form(...),
):
    match = _load_match(db, match_id)
    if not match:
        return RedirectResponse("/", status_code=303)
    mem = _league_membership_for_user(db, match.league_id, user.id)
    if not mem or match.status != MatchStatus.scheduled:
        return RedirectResponse("/", status_code=303)

    team = team.upper()
    if team not in ("A", "B", "NONE"):
        team = "NONE"

    mp = next((p for p in match.players if p.user_id == player_id), None)
    if mp:
        mp.team = None if team == "NONE" else team

    a_count, b_count = _team_counts(match.players)
    if a_count > 2 or b_count > 2:
        db.rollback()
        return RedirectResponse(
            f"/matches/{match_id}?error=Each+team+can+have+at+most+2+players",
            status_code=303,
        )

    db.commit()
    return RedirectResponse(f"/matches/{match_id}", status_code=303)


@router.post("/matches/{match_id}/scores")
def save_scores(
    request: Request,
    match_id: int,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    set_numbers: list[int] = Form(default=[]),
    team_a_games: list[int] = Form(default=[]),
    team_b_games: list[int] = Form(default=[]),
    team_a_tb: list[str] = Form(default=[]),
    team_b_tb: list[str] = Form(default=[]),
    action: str = Form("save"),
):
    match = _load_match(db, match_id)
    if not match:
        return RedirectResponse("/", status_code=303)

    mem = _league_membership_for_user(db, match.league_id, user.id)
    if not mem:
        return RedirectResponse("/", status_code=303)

    if match.status == MatchStatus.scheduled:
        if not (user.is_admin or match.created_by_id == user.id or is_league_admin(mem)):
            return RedirectResponse(f"/matches/{match_id}", status_code=303)

    if match.status == MatchStatus.completed and action != "reopen":
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    sets: list[SetInput] = []
    for i, sn in enumerate(set_numbers):
        a_g = team_a_games[i] if i < len(team_a_games) else 0
        b_g = team_b_games[i] if i < len(team_b_games) else 0
        a_tb_raw = team_a_tb[i] if i < len(team_a_tb) else ""
        b_tb_raw = team_b_tb[i] if i < len(team_b_tb) else ""
        try:
            a_tb = int(a_tb_raw) if str(a_tb_raw).strip() else None
            b_tb = int(b_tb_raw) if str(b_tb_raw).strip() else None
        except ValueError:
            a_tb, b_tb = None, None
        sets.append(
            SetInput(
                set_number=sn,
                team_a_games=int(a_g),
                team_b_games=int(b_g),
                team_a_tb=a_tb,
                team_b_tb=b_tb,
            )
        )

    if action == "save":
        if match.status != MatchStatus.scheduled:
            return RedirectResponse(f"/matches/{match_id}", status_code=303)
        for existing in list(match.set_scores):
            db.delete(existing)
        for s in sets:
            db.add(
                SetScore(
                    match_id=match.id,
                    set_number=s.set_number,
                    team_a_games=s.team_a_games,
                    team_b_games=s.team_b_games,
                    team_a_tb=s.team_a_tb,
                    team_b_tb=s.team_b_tb,
                )
            )
        db.commit()
        return RedirectResponse(f"/matches/{match_id}?success=Scores+saved", status_code=303)

    if action == "finalize":
        if match.status != MatchStatus.scheduled:
            return RedirectResponse(f"/matches/{match_id}", status_code=303)
        a_count, b_count = _team_counts(match.players)
        if a_count != 2 or b_count != 2:
            return RedirectResponse(
                f"/matches/{match_id}?error=Assign+2+players+to+each+team+before+finalizing",
                status_code=303,
            )

        result, err = validate_match_scores(sets, match.best_of)
        if err or result is None:
            return RedirectResponse(
                f"/matches/{match_id}?error={(err or 'Invalid+scores').replace(' ', '+')}",
                status_code=303,
            )

        for existing in list(match.set_scores):
            db.delete(existing)
        for s in sets:
            db.add(
                SetScore(
                    match_id=match.id,
                    set_number=s.set_number,
                    team_a_games=s.team_a_games,
                    team_b_games=s.team_b_games,
                    team_a_tb=s.team_a_tb,
                    team_b_tb=s.team_b_tb,
                )
            )

        match.status = MatchStatus.completed
        match.winner_team = result.winner
        match.elo_delta = compute_elo_delta(db, match, result.winner)
        apply_elo_for_match(db, match, result.winner)
        db.commit()
        return RedirectResponse(
            f"/matches/{match_id}?success=Match+finalized+Team+{result.winner}+wins",
            status_code=303,
        )

    return RedirectResponse(f"/matches/{match_id}", status_code=303)


@router.post("/matches/{match_id}/best_of")
def update_best_of(
    match_id: int,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    best_of: int = Form(...),
):
    match = _load_match(db, match_id)
    if not match or match.status != MatchStatus.scheduled:
        return RedirectResponse("/", status_code=303)

    mem = _league_membership_for_user(db, match.league_id, user.id)
    if not mem:
        return RedirectResponse("/", status_code=303)
    if not (user.is_admin or match.created_by_id == user.id or is_league_admin(mem)):
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    if best_of not in (3, 5, 7):
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    mx = max((s.set_number for s in match.set_scores), default=0)
    if mx > best_of:
        return RedirectResponse(
            f"/matches/{match_id}?error=Too+many+saved+sets+for+that+format+(max+set+{mx})",
            status_code=303,
        )

    match.best_of = best_of
    db.commit()
    return RedirectResponse(f"/matches/{match_id}", status_code=303)


@router.post("/matches/{match_id}/reopen")
def reopen_match(
    match_id: int,
    user: ApprovedUser,
    db: Session = Depends(get_db),
):
    match = _load_match(db, match_id)
    if not match or match.status != MatchStatus.completed:
        return RedirectResponse("/", status_code=303)

    mem = _league_membership_for_user(db, match.league_id, user.id)
    if not mem:
        return RedirectResponse("/", status_code=303)
    if not (user.is_admin or is_league_admin(mem)):
        return RedirectResponse(f"/matches/{match_id}", status_code=303)

    reverse_elo_for_match(db, match)
    match.status = MatchStatus.scheduled
    db.commit()
    return RedirectResponse(f"/matches/{match_id}?success=Match+reopened+for+editing", status_code=303)
