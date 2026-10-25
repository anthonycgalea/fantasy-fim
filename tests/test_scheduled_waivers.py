import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.admin import Admin
from cogs.announcements import Announcements, NEW_YORK
from models.base import Base
from models.draft import Draft
from models.scores import FantasyTeam, League, Team, TeamOwned, WeekStatus
from models.transactions import TeamOnWaivers, WaiverClaim, WaiverPriority


class AsyncSessionAdapter:
    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    async def execute(self, stmt):
        return self.session.execute(stmt)

    def add(self, row):
        self.session.add(row)

    def add_all(self, rows):
        self.session.add_all(rows)

    async def delete(self, row):
        self.session.delete(row)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()


class ScheduledWaiverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.admin = SimpleNamespace(processWaiversTask=AsyncMock())
        self.cog = Announcements(SimpleNamespace(
            get_cog=Mock(return_value=self.admin)
        ))

    async def test_runs_tuesday_wednesday_thursday_only(self):
        for day in range(19, 26):
            self.admin.processWaiversTask.reset_mock()
            await self.cog.run_scheduled_waiver_processing(
                datetime.datetime(2026, 10, day, 7, tzinfo=NEW_YORK)
            )
            self.assertEqual(self.admin.processWaiversTask.await_count,
                             1 if day in (20, 21, 22) else 0)

    async def test_uses_new_york_weekday(self):
        # Tuesday UTC is still Monday night in New York.
        await self.cog.run_scheduled_waiver_processing(
            datetime.datetime(2026, 10, 20, 1, tzinfo=datetime.timezone.utc)
        )
        self.admin.processWaiversTask.assert_not_awaited()

    def test_seven_am_schedule_follows_est_edt(self):
        scheduled = self.cog.waiver_processing.time[0]
        self.assertEqual((scheduled.hour, scheduled.minute), (7, 0))
        for month, expected_offset in ((1, -5), (7, -4)):
            local = datetime.datetime.combine(datetime.date(2026, month, 15), scheduled)
            self.assertEqual(local.utcoffset(), datetime.timedelta(hours=expected_offset))


class WaiverProcessingFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.channel = SimpleNamespace(send=AsyncMock())
        self.bot = SimpleNamespace(
            async_session=lambda: AsyncSessionAdapter(self.engine),
            getCurrentWeek=AsyncMock(return_value=SimpleNamespace(year=2026, week=1)),
            fetch_channel=AsyncMock(return_value=self.channel),
        )
        self.admin = Admin(self.bot)

    def tearDown(self):
        self.engine.dispose()

    async def test_no_active_week_does_not_process(self):
        self.bot.getCurrentWeek.return_value = None
        self.assertFalse(await self.admin.processWaiversTask())
        self.channel.send.assert_not_awaited()

    async def test_successful_claim_is_processed_while_lineups_locked(self):
        with Session(self.engine) as session:
            session.add(WeekStatus(
                year=2026, week=1, active=True, lineups_locked=True, scores_finalized=False,
            ))
            session.add(League(
                league_id=1, league_name="Test", year=2026, active=True,
                is_fim=True, discord_channel="123", team_size_limit=3,
            ))
            session.add(FantasyTeam(fantasy_team_id=1, fantasy_team_name="Test", league_id=1))
            session.add(Draft(draft_id=1, league_id=1, event_key="2026fim", discord_channel="123"))
            for number in ("27", "33"):
                session.add(Team(team_number=number, name=number, is_fim=True))
            session.add(TeamOwned(
                team_key="33", fantasy_team_id=1, league_id=1, draft_id=1,
            ))
            session.add(TeamOnWaivers(league_id=1, team_number="27"))
            session.add(WaiverPriority(league_id=1, fantasy_team_id=1, priority=1))
            session.add(WaiverClaim(
                fantasy_team_id=1, league_id=1, priority=1,
                team_claimed="27", team_to_drop="33",
            ))
            session.commit()
        self.assertTrue(await self.admin.processWaiversTask())
        with Session(self.engine) as session:
            self.assertEqual(session.query(TeamOwned).one().team_key, "27")
            self.assertEqual(session.query(TeamOnWaivers).one().team_number, "33")
            self.assertEqual(session.query(WaiverClaim).count(), 0)
            self.assertTrue(session.get(WeekStatus, (2026, 1)).lineups_locked)
        self.channel.send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
