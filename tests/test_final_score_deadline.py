import asyncio
import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.admin import Admin
from cogs.announcements import Announcements, NEW_YORK
from models.base import Base
from models.scores import WeekStatus


class AsyncSessionAdapter:
    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    async def execute(self, stmt):
        return self.session.execute(stmt)

    async def commit(self):
        self.session.commit()

    async def flush(self):
        self.session.flush()

    def add(self, row):
        self.session.add(row)


class FinalScoreDeadlineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            for week, date, active, finalized in (
                (1, datetime.date(2026, 10, 25), True, False),
                (2, datetime.date(2026, 10, 26), True, False),
                (3, None, True, False),
                (4, datetime.date(2026, 10, 24), False, False),
                (5, datetime.date(2026, 10, 24), True, True),
            ):
                session.add(WeekStatus(
                    year=2026, week=week, week_end_date=date,
                    active=active, lineups_locked=False, scores_finalized=finalized,
                ))
            session.commit()
        self.bot = SimpleNamespace(
            async_session=lambda: AsyncSessionAdapter(self.engine),
        )
        self.admin = Admin(self.bot)
        self.bot.get_cog = lambda name: self.admin
        self.cog = Announcements(self.bot)

    def tearDown(self):
        self.engine.dispose()

    def status(self, week=1):
        with Session(self.engine) as session:
            return session.get(WeekStatus, (2026, week))

    async def check(self, hour=21, minute=0, day=25):
        await self.cog.run_due_final_score_updates(
            datetime.datetime(2026, 10, day, hour, minute, tzinfo=NEW_YORK)
        )

    async def test_no_finalization_before_nine_pm(self):
        await self.check(hour=20, minute=59)
        self.assertFalse(self.status().scores_finalized)

    async def test_finalizes_only_due_active_week_at_nine_pm(self):
        await self.check()
        self.assertTrue(self.status().scores_finalized)
        self.assertTrue(self.status().active)
        for week in (2, 3, 4):
            self.assertFalse(self.status(week).scores_finalized)

    async def test_restart_at_nine_oh_one_catches_up_and_skips_finalized_week(self):
        self.admin.notifyWeeklyScoresTask = AsyncMock()
        self.admin.getLeagueStandingsTask = AsyncMock()
        await self.check(minute=1)
        restarted = Announcements(self.bot)
        await restarted.run_due_final_score_updates(
            datetime.datetime(2026, 10, 25, 21, 2, tzinfo=NEW_YORK)
        )
        self.admin.notifyWeeklyScoresTask.assert_awaited_once_with(None, 2026, 1)
        self.admin.getLeagueStandingsTask.assert_awaited_once_with(None, 2026, 1)

    async def test_next_day_before_nine_catches_up(self):
        await self.check(hour=9, day=26)
        self.assertTrue(self.status().scores_finalized)
        self.assertFalse(self.status(2).scores_finalized)

    async def test_deadline_follows_est_and_edt(self):
        for month, utc_hour in ((1, 2), (7, 1)):
            with self.subTest(month=month):
                with Session(self.engine) as session:
                    row = session.get(WeekStatus, (2026, 1))
                    row.week_end_date = datetime.date(2026, month, 15)
                    row.scores_finalized = False
                    session.commit()
                utc = datetime.timezone.utc
                await self.cog.run_due_final_score_updates(
                    datetime.datetime(2026, month, 16, utc_hour - 1, 59, tzinfo=utc)
                )
                self.assertFalse(self.status().scores_finalized)
                await self.cog.run_due_final_score_updates(
                    datetime.datetime(2026, month, 16, utc_hour, tzinfo=utc)
                )
                self.assertTrue(self.status().scores_finalized)

    async def test_scoring_failure_stays_unfinalized_and_can_retry(self):
        original = self.admin.scoreAllLeaguesTask
        self.admin.scoreAllLeaguesTask = AsyncMock(side_effect=RuntimeError("failed"))
        await self.check()
        self.assertFalse(self.status().scores_finalized)
        self.admin.scoreAllLeaguesTask = original
        await self.check(minute=1)
        self.assertTrue(self.status().scores_finalized)

    async def test_concurrent_final_updates_only_finalize_and_notify_once(self):
        original = self.admin.scoreWeekTask

        async def delayed_score(*args):
            await asyncio.sleep(0)
            return await original(*args)

        self.admin.scoreWeekTask = delayed_score
        self.admin.notifyWeeklyScoresTask = AsyncMock()
        self.admin.getLeagueStandingsTask = AsyncMock()
        results = await asyncio.gather(
            self.admin.runScoreUpdate(None, 2026, 1, final=True),
            self.admin.runScoreUpdate(None, 2026, 1, final=True),
        )
        self.assertEqual(results, [True, False])
        self.admin.notifyWeeklyScoresTask.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
