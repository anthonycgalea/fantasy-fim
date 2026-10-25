import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.admin import Admin
from cogs.announcements import Announcements, NEW_YORK
from models.base import Base
from models.scores import (
    FantasyScores, FantasyTeam, FRCEvent, League, Team, TeamScore, TeamStarted, WeekStatus,
)


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

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()


class WeekendScoreUpdateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            for week, active, locked, finalized in (
                (1, True, True, False), (2, True, False, False),
                (3, False, True, False), (4, True, True, True),
            ):
                session.add(WeekStatus(
                    year=2026, week=week, active=active,
                    lineups_locked=locked, scores_finalized=finalized,
                ))
            session.commit()
        self.admin = SimpleNamespace(runScoreUpdate=AsyncMock())
        self.channel = SimpleNamespace(send=AsyncMock())
        self.bot = SimpleNamespace(
            async_session=lambda: AsyncSessionAdapter(self.engine),
            get_cog=Mock(return_value=self.admin),
            get_channel=Mock(return_value=self.channel),
        )
        self.cog = Announcements(self.bot)

    def tearDown(self):
        self.engine.dispose()

    async def test_friday_and_saturday_select_only_active_locked_nonfinal_weeks(self):
        for day in (23, 24):
            self.admin.runScoreUpdate.reset_mock()
            await self.cog.run_scheduled_score_updates(
                datetime.datetime(2026, 10, day, 22, tzinfo=NEW_YORK)
            )
            self.admin.runScoreUpdate.assert_awaited_once_with(
                None, 2026, 1, final=False, states=False
            )

    async def test_other_nights_are_skipped(self):
        for day in (19, 20, 21, 22, 25):
            await self.cog.run_scheduled_score_updates(
                datetime.datetime(2026, 10, day, 22, tzinfo=NEW_YORK)
            )
        self.admin.runScoreUpdate.assert_not_awaited()

    async def test_uses_new_york_day_even_when_utc_is_next_day(self):
        await self.cog.run_scheduled_score_updates(
            datetime.datetime(2026, 10, 24, 2, tzinfo=datetime.timezone.utc)
        )
        self.admin.runScoreUpdate.assert_awaited_once()

    async def test_one_failed_week_does_not_stop_another(self):
        with Session(self.engine) as session:
            session.add(WeekStatus(
                year=2026, week=5, active=True,
                lineups_locked=True, scores_finalized=False,
            ))
            session.commit()
        self.admin.runScoreUpdate.side_effect = [RuntimeError("failed"), True]
        await self.cog.run_scheduled_score_updates(
            datetime.datetime(2026, 10, 23, 22, tzinfo=NEW_YORK)
        )
        self.assertEqual(self.admin.runScoreUpdate.await_count, 2)

    def test_schedule_is_ten_pm_and_tracks_dst(self):
        scheduled = self.cog.weekend_score_update.time[0]
        self.assertEqual((scheduled.hour, scheduled.minute), (22, 0))
        for month, offset in ((1, -5), (7, -4)):
            local = datetime.datetime.combine(datetime.date(2026, month, 15), scheduled)
            self.assertEqual(local.utcoffset(), datetime.timedelta(hours=offset))

    async def test_shared_pipeline_updates_and_posts_unofficial_scores_without_interaction(self):
        with Session(self.engine) as session:
            session.add(League(
                league_id=1, league_name="Test League", year=2026,
                is_fim=True, active=True, discord_channel="123", team_size_limit=3,
            ))
            session.add(FantasyTeam(
                fantasy_team_id=1, fantasy_team_name="Test Team", league_id=1,
            ))
            session.add(Team(team_number="27", name="Team 27", rookie_year=2020))
            session.add(FRCEvent(
                event_key="2026test", event_name="Test Event",
                year=2026, week=1, is_fim=True,
            ))
            session.add(TeamScore(team_key="27", event_key="2026test"))
            session.add(TeamStarted(
                fantasy_team_id=1, team_number="27", league_id=1,
                event_key="2026test", week=1,
            ))
            session.commit()
        response = Mock()
        response.json.return_value = {"points": {"frc27": {
            "qual_points": 10, "alliance_points": 2, "elim_points": 0, "award_points": 0,
        }}}
        admin = Admin(self.bot)
        with patch("cogs.admin.get_tba_headers", return_value={}), patch(
            "cogs.admin.requests.get", return_value=response
        ):
            success = await admin.runScoreUpdate(None, 2026, 1, final=False)
        self.assertTrue(success)
        with Session(self.engine) as session:
            self.assertFalse(session.get(WeekStatus, (2026, 1)).scores_finalized)
            score = session.query(FantasyScores).one()
            self.assertEqual(score.weekly_score, 12)
        self.assertEqual(self.channel.send.await_count, 2)
        title = self.channel.send.await_args_list[0].kwargs["embed"].title
        self.assertIn("Unofficial", title)

    async def test_finalized_week_stops_shared_pipeline_before_notifications(self):
        self.assertFalse(await Admin(self.bot).runScoreUpdate(None, 2026, 4))
        self.channel.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
