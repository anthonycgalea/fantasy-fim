import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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

    async def test_waits_until_seven_am_and_passes_day_marker(self):
        await self.cog.run_scheduled_waiver_processing(
            datetime.datetime(2026, 10, 20, 6, 59, tzinfo=NEW_YORK)
        )
        self.admin.processWaiversTask.assert_not_awaited()
        await self.cog.run_scheduled_waiver_processing(
            datetime.datetime(2026, 10, 20, 7, tzinfo=NEW_YORK)
        )
        self.admin.processWaiversTask.assert_awaited_once_with(processed_field="tuesday_processed")

    async def test_seven_am_follows_est_edt(self):
        for month, day, utc_hour in ((1, 20, 12), (7, 21, 11)):
            self.admin.processWaiversTask.reset_mock()
            await self.cog.run_scheduled_waiver_processing(
                datetime.datetime(2026, month, day, utc_hour - 1, 59, tzinfo=datetime.timezone.utc)
            )
            self.admin.processWaiversTask.assert_not_awaited()
            await self.cog.run_scheduled_waiver_processing(
                datetime.datetime(2026, month, day, utc_hour, tzinfo=datetime.timezone.utc)
            )
            self.admin.processWaiversTask.assert_awaited_once()


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

    def seed_week_and_league(self, week=1):
        self.bot.getCurrentWeek.return_value = SimpleNamespace(year=2026, week=week)
        with Session(self.engine) as session:
            session.add(WeekStatus(
                year=2026, week=week, active=True, lineups_locked=True, scores_finalized=False,
            ))
            session.add(League(
                league_id=1, league_name="Test", year=2026, active=True,
                is_fim=True, discord_channel="123", team_size_limit=3,
            ))
            session.commit()

    async def test_new_week_has_all_processing_flags_false(self):
        self.seed_week_and_league()
        with Session(self.engine) as session:
            row = session.get(WeekStatus, (2026, 1))
            self.assertFalse(row.tuesday_processed)
            self.assertFalse(row.wednesday_processed)
            self.assertFalse(row.thursday_processed)

    async def test_successful_run_sets_only_its_flag_and_skips_repeat(self):
        self.seed_week_and_league()
        self.assertTrue(await self.admin.processWaiversTask(processed_field="tuesday_processed"))
        self.assertFalse(await self.admin.processWaiversTask(processed_field="tuesday_processed"))
        with Session(self.engine) as session:
            row = session.get(WeekStatus, (2026, 1))
            self.assertTrue(row.tuesday_processed)
            self.assertFalse(row.wednesday_processed)
            self.assertFalse(row.thursday_processed)
        self.channel.send.assert_not_awaited()
        self.bot.fetch_channel.assert_not_awaited()

    async def test_failed_processing_does_not_set_flag(self):
        self.seed_week_and_league()
        with patch.object(
            AsyncSessionAdapter, "commit",
            new=AsyncMock(side_effect=RuntimeError("Commit failed")),
        ):
            with self.assertRaises(RuntimeError):
                await self.admin.processWaiversTask(processed_field="wednesday_processed")
        with Session(self.engine) as session:
            self.assertFalse(session.get(WeekStatus, (2026, 1)).wednesday_processed)

    async def test_states_week_skips_thursday_but_allows_wednesday(self):
        self.seed_week_and_league(week=7)
        self.assertFalse(await self.admin.processWaiversTask(processed_field="thursday_processed"))
        self.channel.send.assert_not_awaited()
        self.assertTrue(await self.admin.processWaiversTask(processed_field="wednesday_processed"))
        with Session(self.engine) as session:
            row = session.get(WeekStatus, (2026, 7))
            self.assertFalse(row.thursday_processed)
            self.assertTrue(row.wednesday_processed)

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
            session.add(League(
                league_id=2, league_name="No claims", year=2026, active=True,
                is_fim=True, discord_channel="456", team_size_limit=3,
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
        self.bot.fetch_channel.assert_awaited_once_with(123)


if __name__ == "__main__":
    unittest.main()
