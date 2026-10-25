import datetime
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.admin import Admin
from cogs.announcements import Announcements, NEW_YORK
from cogs.manageteam import ManageTeam
from models.base import Base
from models.draft import Draft
from models.scores import (
    FRCEvent, FantasyTeam, League, Team, TeamOwned, TeamScore, WeekStatus,
)
from models.transactions import TeamOnWaivers, WaiverClaim


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

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()


class WeekFinishAndWaiverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            for week, date, active, finalized in (
                (1, datetime.date(2026, 7, 10), True, True),
                (2, datetime.date(2026, 7, 11), True, True),
                (3, datetime.date(2026, 7, 9), False, True),
                (4, None, True, True),
                (5, datetime.date(2026, 7, 10), True, False),
            ):
                session.add(WeekStatus(
                    year=2026, week=week, week_end_date=date,
                    week_start_date=datetime.date(2026, 7, 10) if week == 1 else None,
                    active=active, lineups_locked=False, scores_finalized=finalized,
                ))
            session.add(League(
                league_id=1, league_name="FiM", year=2026, is_fim=True,
                active=True, discord_channel="123", team_size_limit=3,
            ))
            session.add(FantasyTeam(
                fantasy_team_id=1, fantasy_team_name="Test", league_id=1,
            ))
            session.add(Draft(draft_id=1, league_id=1, event_key="2026test", discord_channel="123"))
            session.add(FRCEvent(
                event_key="2026test", event_name="Test", year=2026, week=1, is_fim=True,
            ))
            for number in ("27", "33", "44"):
                session.add(Team(team_number=number, name=number, is_fim=True))
                session.add(TeamScore(team_key=number, event_key="2026test"))
            session.add(TeamOwned(
                team_key="33", fantasy_team_id=1, league_id=1, draft_id=1,
            ))
            session.add(TeamOnWaivers(league_id=1, team_number="44"))
            session.commit()
        self.bot = SimpleNamespace(
            async_session=lambda: AsyncSessionAdapter(self.engine),
            getCurrentWeek=AsyncMock(return_value=SimpleNamespace(year=2026, week=1)),
        )
        self.admin = Admin(self.bot)
        self.admin.verifyAdmin = AsyncMock(return_value=True)
        self.bot.get_cog = lambda name: self.admin
        self.cog = Announcements(self.bot)
        self.cog.send_announcement = AsyncMock()
        self.message = SimpleNamespace(edit=AsyncMock())
        self.interaction = SimpleNamespace(
            response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
            original_response=AsyncMock(return_value=self.message),
        )

    def tearDown(self):
        self.engine.dispose()

    def status(self, week=1):
        with Session(self.engine) as session:
            return session.get(WeekStatus, (2026, week))

    def waiver_teams(self):
        with Session(self.engine) as session:
            return {row.team_number for row in session.query(TeamOnWaivers).all()}

    async def test_automatic_lock_populates_waivers_and_excludes_owned_teams(self):
        await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 10, 16, tzinfo=NEW_YORK)
        )
        self.assertEqual(self.waiver_teams(), {"27", "44"})
        self.assertTrue(self.status().lineups_locked)
        await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 10, 16, 1, tzinfo=NEW_YORK)
        )
        self.assertEqual(self.waiver_teams(), {"27", "44"})

    async def test_manual_lock_also_populates_waivers(self):
        await Admin.lockLineups.callback(self.admin, self.interaction)
        self.assertEqual(self.waiver_teams(), {"27", "44"})
        self.assertTrue(self.status().lineups_locked)

    async def test_finish_waits_until_midnight_after_end_date(self):
        await self.cog.run_due_week_finishes(
            datetime.datetime(2026, 7, 10, 23, 59, 59, tzinfo=NEW_YORK)
        )
        self.assertTrue(self.status().active)
        await self.cog.run_due_week_finishes(
            datetime.datetime(2026, 7, 11, 0, tzinfo=NEW_YORK)
        )
        self.assertFalse(self.status().active)
        self.assertTrue(self.status().lineups_locked)
        for week in (2, 4, 5):
            self.assertTrue(self.status(week).active)
        self.cog.send_announcement.assert_awaited_once_with("Deactivated week 1 in 2026")

    async def test_restart_after_midnight_finishes_once(self):
        now = datetime.datetime(2026, 7, 11, 0, 1, tzinfo=NEW_YORK)
        await self.cog.run_due_week_finishes(now)
        await self.cog.run_due_week_finishes(now)
        self.cog.send_announcement.assert_awaited_once()

    async def test_finishing_no_longer_places_teams_on_waivers(self):
        await self.admin.finishWeekTask(2026, 1)
        self.assertEqual(self.waiver_teams(), {"44"})
        self.assertFalse(self.status().active)

    async def test_claim_is_allowed_while_lineups_are_locked(self):
        await self.cog.lock_due_lineups(
            datetime.datetime(2026, 7, 10, 16, tzinfo=NEW_YORK)
        )
        manager = ManageTeam(self.bot)
        manager.getWaiverClaimPriority = AsyncMock(return_value=1)
        await manager.makeWaiverClaimTask(self.interaction, 1, "27", "33")
        with Session(self.engine) as session:
            claim = session.query(WaiverClaim).one()
            self.assertEqual(claim.team_claimed, "27")
            self.assertEqual(claim.team_to_drop, "33")
        self.assertTrue(self.status().lineups_locked)

    async def test_finish_rechecks_finalization_before_deactivating(self):
        self.assertFalse(await self.admin.finishWeekTask(2026, 5, require_finalized=True))
        self.assertTrue(self.status(5).active)


if __name__ == "__main__":
    unittest.main()
