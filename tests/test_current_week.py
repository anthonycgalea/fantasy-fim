import importlib
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.scores import WeekStatus

with patch.dict(os.environ, {"DATABASE_URL": "sqlite://"}):
    api = importlib.import_module("app")


class CurrentWeekTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as session:
            for year, week, active in (
                (2025, 3, True),
                (2026, 1, False),
                (2026, 2, True),
                (2026, 4, True),
                (2027, 1, False),
            ):
                session.add(WeekStatus(
                    year=year, week=week, active=active,
                    lineups_locked=True, scores_finalized=False,
                ))
            session.commit()
        self.session_patch = patch.object(api, "Session", self.session_factory)
        self.session_patch.start()
        self.schema_patch = patch.object(
            api.app, "_schema_initialized", True, create=True
        )
        self.schema_patch.start()
        self.client = api.app.test_client()

    def tearDown(self):
        self.schema_patch.stop()
        self.session_patch.stop()
        self.engine.dispose()

    def test_omitted_year_preserves_cross_year_ordering(self):
        response = self.client.get("/currentWeek")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "year": 2025, "week": 3, "active": True,
            "lineups_locked": True, "scores_finalized": False,
        })

    def test_explicit_year_returns_earliest_active_week_in_that_year(self):
        response = self.client.get("/currentWeek?year=2026")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["year"], 2026)
        self.assertEqual(response.get_json()["week"], 2)

    def test_no_matching_active_week_returns_not_found(self):
        for year in (2027, 1900):
            with self.subTest(year=year):
                response = self.client.get(f"/currentWeek?year={year}")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.get_json(), {
                    "error": "No active week found"
                })

    def test_invalid_year_returns_bad_request_before_querying(self):
        with patch.object(api, "Session") as session:
            for year in ("abc", "", "2026.5"):
                with self.subTest(year=year):
                    response = self.client.get("/currentWeek?year=" + year)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json(), {
                        "error": "year must be an integer"
                    })
            session.assert_not_called()
