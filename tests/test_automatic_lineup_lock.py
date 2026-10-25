import datetime
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.announcements import Announcements, NEW_YORK
from models.base import Base
from models.draft import Draft  # Register draft tables referenced by scores.
from models.transactions import WaiverPriority  # Register score relationships.
from models.scores import WeekStatus
from models.users import Player  # Register the players table referenced by metadata.


class AsyncSessionAdapter:
    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    @asynccontextmanager
    async def begin(self):
        with self.session.begin():
            yield

    async def execute(self, stmt):
        return self.session.execute(stmt)


class AutomaticLineupLockTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.cog = Announcements(SimpleNamespace(
            async_session=lambda: AsyncSessionAdapter(self.engine)
        ))
        with Session(self.engine) as session:
            for week, start_date, active, locked in (
                (1, datetime.date(2026, 7, 10), True, False),
                (2, datetime.date(2026, 7, 11), True, False),
                (3, None, True, False),
                (4, datetime.date(2026, 7, 9), False, False),
                (5, datetime.date(2026, 7, 9), True, True),
            ):
                session.add(WeekStatus(
                    year=2026, week=week, week_start_date=start_date,
                    active=active, lineups_locked=locked, scores_finalized=False,
                ))
            session.commit()

    def tearDown(self):
        self.engine.dispose()

    def locked(self, week):
        with Session(self.engine) as session:
            return session.get(WeekStatus, (2026, week)).lineups_locked

    async def test_does_not_lock_before_four_pm(self):
        rows = await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 10, 15, 59, 59, tzinfo=NEW_YORK)
        )
        self.assertEqual(rows, [])
        self.assertFalse(self.locked(1))

    async def test_locks_at_four_pm_and_skips_future_inactive_undated_locked(self):
        rows = await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 10, 16, tzinfo=NEW_YORK)
        )
        self.assertEqual([tuple(row) for row in rows], [(2026, 1)])
        self.assertTrue(self.locked(1))
        for week in (2, 3, 4):
            self.assertFalse(self.locked(week))

    async def test_restart_after_deadline_catches_up_only_once(self):
        now = datetime.datetime(2026, 7, 10, 16, 1, tzinfo=NEW_YORK)
        self.assertEqual(len(await self.cog.lock_due_lineups(now)), 1)
        # A new cog represents a restart; the saved flag prevents duplicate work.
        restarted = Announcements(self.cog.bot)
        self.assertEqual(await restarted.lock_due_lineups(now), [])

    async def test_previous_day_catches_up_before_today_four_pm(self):
        rows = await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 11, 9, tzinfo=NEW_YORK)
        )
        self.assertEqual([tuple(row) for row in rows], [(2026, 1)])
        self.assertFalse(self.locked(2))

    async def test_summer_utc_deadline_is_twenty_utc(self):
        utc = datetime.timezone.utc
        self.assertEqual(await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 10, 19, 59, tzinfo=utc)
        ), [])
        self.assertEqual(len(await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 10, 20, tzinfo=utc)
        )), 1)

    async def test_winter_utc_deadline_is_twenty_one_utc(self):
        with Session(self.engine) as session:
            session.get(WeekStatus, (2026, 1)).week_start_date = datetime.date(2026, 1, 10)
            session.commit()
        utc = datetime.timezone.utc
        self.assertEqual(await self.cog.lock_due_lineups(
            datetime.datetime(2026, 1, 10, 20, 59, tzinfo=utc)
        ), [])
        self.assertEqual(len(await self.cog.lock_due_lineups(
            datetime.datetime(2026, 1, 10, 21, tzinfo=utc)
        )), 1)

    async def test_announces_exact_message_only_when_lock_changes(self):
        original = self.cog.lock_due_lineups

        async def fixed_time_lock():
            return await original(datetime.datetime(2026, 7, 10, 16, 1, tzinfo=NEW_YORK))

        self.cog.lock_due_lineups = fixed_time_lock
        self.cog.send_announcement = AsyncMock()
        await Announcements.lineup_lock_check.coro(self.cog)
        await Announcements.lineup_lock_check.coro(self.cog)
        self.cog.send_announcement.assert_awaited_once_with("testing lock lineups")


if __name__ == "__main__":
    unittest.main()
