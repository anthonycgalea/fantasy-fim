import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from cogs.manageteam import ManageTeam
from models.base import Base
from models.scores import FantasyTeam, FRCEvent, League, TeamOwned, TeamScore, TeamStarted
from test_swapdraftpick import AsyncSessionAdapter


class LineupSession(AsyncSessionAdapter):
    def add(self, record):
        self.session.add(record)


class SeasonWeekTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([
                League(league_id=1, league_name='Test', year=2027, is_fim=True, team_starts=1, discord_channel='10', team_size_limit=3),
                FantasyTeam(fantasy_team_id=1, league_id=1, fantasy_team_name='Test'),
                TeamOwned(draft_id=1, league_id=1, fantasy_team_id=1, team_key='123'),
            ])
            for week in (5, 6, 7):
                session.add(FRCEvent(event_key=f'2027w{week}', year=2027,
                                     week=week, is_fim=True, event_name=f'Week {week}'))
            session.add(TeamScore(team_key='123', event_key='2027w6'))
            session.commit()
        self.cog = ManageTeam(SimpleNamespace(
            async_session=lambda: LineupSession(self.engine)))
        self.interaction = SimpleNamespace(original_response=AsyncMock())

    def tearDown(self):
        self.engine.dispose()

    async def start(self, week):
        return await self.cog.startTeamTask(
            self.interaction, '123', week, 1, update_response=False)

    async def test_week_six_event_cannot_start_in_week_five(self):
        self.assertIn('not competing', await self.start(5))
        self.assertIn('starting team 123', await self.start(6))
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(TeamStarted.week)), 6)

    async def test_extra_starter_is_allowed_in_states_week_seven(self):
        with Session(self.engine) as session:
            session.add(TeamScore(team_key='123', event_key='2027w7'))
            session.add(TeamStarted(fantasy_team_id=1, league_id=1,
                                   team_number='456', event_key='2027w7', week=7))
            session.commit()
        self.assertIn('starting team 123', await self.start(7))

    async def test_week_six_has_regular_season_start_limit(self):
        with Session(self.engine) as session:
            session.add(TeamStarted(fantasy_team_id=1, league_id=1,
                                   team_number='456', event_key='2027w6', week=6))
            session.commit()
        self.assertIn('max number', await self.start(6))

    async def test_2026_keeps_combined_week_lineups(self):
        with Session(self.engine) as session:
            session.get(League, 1).year = 2026
            session.add(FRCEvent(event_key='2026w6', year=2026, week=6,
                                 is_fim=True, event_name='2026 Week 6'))
            session.add(TeamScore(team_key='123', event_key='2026w6'))
            session.commit()
        self.assertIn('managed under week 5', await self.start(6))
        self.assertIn('starting team 123', await self.start(5))
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(TeamStarted.week)), 5)
