"""Database operations shared by manual and automatic week lifecycle actions."""

from sqlalchemy import select

from models.scores import FRCEvent, League, Team, TeamOwned, TeamScore
from models.transactions import TeamOnWaivers


async def add_week_teams_to_waivers(session, year, week):
    """Place unowned competing FiM teams on waivers without committing."""
    event_weeks = [week]
    if year == 2026 and week == 5:
        event_weeks.append(6)
    result = await session.execute(
        select(TeamScore.team_key)
        .join(Team, Team.team_number == TeamScore.team_key)
        .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key)
        .where(Team.is_fim.is_(True), FRCEvent.year == year, FRCEvent.week.in_(event_weeks))
        .distinct()
    )
    competing = set(result.scalars().all())
    result = await session.execute(
        select(League.league_id).where(
            League.is_fim.is_(True), League.active.is_(True), League.year == year
        )
    )
    league_ids = result.scalars().all()
    for league_id in league_ids:
        result = await session.execute(
            select(TeamOwned.team_key).where(TeamOwned.league_id == league_id)
        )
        owned = set(result.scalars().all())
        result = await session.execute(
            select(TeamOnWaivers.team_number).where(TeamOnWaivers.league_id == league_id)
        )
        existing = set(result.scalars().all())
        for team_number in sorted(competing - owned - existing):
            session.add(TeamOnWaivers(league_id=league_id, team_number=team_number))
    await session.flush()
