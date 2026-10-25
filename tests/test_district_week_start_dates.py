import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.admin import Admin, get_district_week_start_dates
from models.base import Base
from models.scores import WeekStatus


def event(key, week, start_date, event_type=1):
    return {
        "key": key, "name": key, "week": week,
        "start_date": start_date, "event_type": event_type,
    }


class WeekStartDateSelectionTests(unittest.TestCase):
    def test_earliest_event_for_each_one_based_week(self):
        events = [
            event("2026late", 0, "2026-03-07"),
            event("2026early", 0, "2026-03-05"),
            event("2026last", 6, "2026-04-16"),
        ]
        self.assertEqual(get_district_week_start_dates(events, 2026), {
            1: datetime.date(2026, 3, 5), 7: datetime.date(2026, 4, 16),
        })

    def test_excludes_unsupported_weeks_types_years_and_invalid_dates(self):
        events = [
            event("2026negative", -1, "2026-03-01"),
            event("2026eighth", 7, "2026-04-23"),
            event("2026null", None, "2026-03-01"),
            event("2026string", "0", "2026-03-01"),
            event("2026bool", True, "2026-03-01"),
            event("2026invalid", 0, "invalid"),
            event("2026missing", 0, None),
            event("2026otherdate", 0, "2025-03-01"),
            event("2025otheryear", 0, "2026-03-01"),
            event("2026unsupported", 0, "2026-03-01", event_type=0),
        ]
        self.assertEqual(get_district_week_start_dates(events, 2026), {})


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

    async def delete(self, row):
        self.session.delete(row)

    async def commit(self):
        self.session.commit()


class DistrictWeekStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.message = SimpleNamespace(edit=AsyncMock())
        self.cog = Admin(SimpleNamespace(
            async_session=lambda: AsyncSessionAdapter(self.engine),
            log_message=AsyncMock(return_value=self.message),
        ))

    def tearDown(self):
        self.engine.dispose()

    async def import_events(self, events):
        def get(url, **kwargs):
            response = Mock()
            response.json.return_value = events if "/district/" in url else []
            return response

        http = Mock()
        http.get.side_effect = get
        http.__enter__ = Mock(return_value=http)
        http.__exit__ = Mock(return_value=False)
        with patch("cogs.admin.get_tba_headers", return_value={}), patch(
            "cogs.admin.requests.Session", return_value=http
        ):
            await self.cog.importFullDistrctTask(2026)

    async def test_creates_missing_week_active_with_other_flags_false(self):
        await self.import_events([event("2026week7", 6, "2026-04-16")])
        with Session(self.engine) as session:
            row = session.get(WeekStatus, (2026, 7))
            self.assertIsNotNone(row)
            self.assertEqual(row.week_start_date, datetime.date(2026, 4, 16))
            self.assertTrue(row.active)
            self.assertFalse(row.lineups_locked)
            self.assertFalse(row.scores_finalized)

    async def test_preserves_existing_flags_and_updates_rescheduled_date(self):
        with Session(self.engine) as session:
            session.add(WeekStatus(
                year=2026, week=1, week_start_date=datetime.date(2026, 3, 1),
                active=True, lineups_locked=True, scores_finalized=True,
            ))
            session.commit()
        await self.import_events([
            event("2026later", 0, "2026-03-07"),
            event("2026earlier", 0, "2026-03-05"),
        ])
        with Session(self.engine) as session:
            row = session.get(WeekStatus, (2026, 1))
            self.assertEqual(row.week_start_date, datetime.date(2026, 3, 5))
            self.assertTrue(row.active)
            self.assertTrue(row.lineups_locked)
            self.assertTrue(row.scores_finalized)

    async def test_week_eight_and_missing_dates_do_not_create_weekstatus(self):
        await self.import_events([
            event("2026week8", 7, "2026-04-23"),
            event("2026undated", 0, None),
        ])
        with Session(self.engine) as session:
            self.assertEqual(session.query(WeekStatus).count(), 0)


if __name__ == "__main__":
    unittest.main()
