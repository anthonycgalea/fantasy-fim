import importlib
import os
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.draft import Draft, DraftPick, StatboticsData
from models.scores import FRCEvent, League, Team, TeamScore

with patch.dict(os.environ, {"DATABASE_URL": "sqlite://"}):
    api = importlib.import_module("app")


class TeamXPResponseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as session:
            for number in ("27", "33", "99"):
                session.add(Team(team_number=number, name=f"Team {number}", is_fim=True))
            session.add(FRCEvent(
                event_key="2027test", event_name="Test Event",
                year=2027, week=1, is_fim=True,
            ))
            for number in ("27", "33", "99"):
                session.add(TeamScore(team_key=number, event_key="2027test"))
            for league_id, is_fim in ((1, True), (2, False)):
                session.add(League(
                    league_id=league_id, league_name=f"League {league_id}",
                    year=2027, is_fim=is_fim, discord_channel="10", team_size_limit=3,
                ))
                session.add(Draft(
                    draft_id=league_id, league_id=league_id,
                    event_key="2027test", discord_channel="10",
                ))
            session.add(DraftPick(
                fantasy_team_id=1, draft_id=1, pick_number=1, team_number="33"
            ))
            session.add_all([
                StatboticsData(team_number="27", year=2026, year_end_epa=None, match13_xp=2129),
                StatboticsData(team_number="33", year=2026, year_end_epa=2000, match13_xp=0),
                StatboticsData(team_number="27", year=2027, year_end_epa=1800, match13_xp=1900),
            ])
            session.commit()
        self.session_patch = patch.object(api, "Session", self.sessions)
        self.schema_patch = patch.object(api.app, "_schema_initialized", True, create=True)
        self.session_patch.start()
        self.schema_patch.start()
        self.http_patch = patch.object(api.requests, "get")
        self.http = self.http_patch.start()
        self.http.return_value = Mock(status_code=404)
        self.client = api.app.test_client()

    def tearDown(self):
        self.http_patch.stop()
        self.schema_patch.stop()
        self.session_patch.stop()
        self.engine.dispose()

    def test_epa_returns_xp_including_zero_and_missing_values(self):
        response = self.client.get("/api/epa?teams=27,33,99&year=2026")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "27": {"year_end_epa": None, "match13_xp": 2129},
            "33": {"year_end_epa": 2000, "match13_xp": 0},
            "99": {"year_end_epa": None, "match13_xp": None},
        })
        self.assertEqual(self.http.call_count, 2)

    def test_epa_lookup_fills_xp_only_record_without_erasing_xp(self):
        self.http.return_value = Mock(
            status_code=200, json=Mock(return_value={"unitless_epa_end": 1987.9})
        )
        response = self.client.get("/api/epa?teams=27&year=2026")
        self.assertEqual(response.get_json(), {
            "27": {"year_end_epa": 1987, "match13_xp": 2129}
        })
        with self.sessions() as session:
            row = session.get(StatboticsData, ("27", 2026))
            self.assertEqual(row.year_end_epa, 1987)
            self.assertEqual(row.match13_xp, 2129)

    def test_epa_lookup_caches_new_record_with_null_xp(self):
        self.http.return_value = Mock(
            status_code=200, json=Mock(return_value={"unitless_epa_end": 1700})
        )
        response = self.client.get("/api/epa?teams=99&year=2026")
        self.assertEqual(response.get_json(), {
            "99": {"year_end_epa": 1700, "match13_xp": None}
        })
        with self.sessions() as session:
            self.assertEqual(session.get(StatboticsData, ("99", 2026)).year_end_epa, 1700)

    def test_draft_xp_uses_same_season_as_epa_and_excludes_picked_teams(self):
        for draft_id, expected_epa, expected_xp in ((1, 0, 2129), (2, 1800, 1900)):
            with self.subTest(draft_id=draft_id):
                response = self.client.get(f"/api/drafts/{draft_id}/availableTeams")
                self.assertEqual(response.status_code, 200)
                teams = {row["team_number"]: row for row in response.get_json()}
                self.assertEqual(teams["27"]["match13_xp"], expected_xp)
                self.assertEqual(teams["27"]["year_end_epa"], expected_epa)
                self.assertIsNone(teams["99"]["match13_xp"])
                self.assertEqual(teams["27"]["events"], [{"event_key": "2027test", "week": 1}])
                if draft_id == 1:
                    self.assertNotIn("33", teams)

    def test_epa_requires_parameters(self):
        for url in ("/api/epa?teams=27", "/api/epa?year=2026"):
            self.assertEqual(self.client.get(url).status_code, 400)


if __name__ == "__main__":
    unittest.main()
