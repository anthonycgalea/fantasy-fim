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

    def test_xp_returns_scalar_map_including_zero_and_missing_values(self):
        response = self.client.get("/xp?teams=27,33,99&year=2026")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"27": 2129, "33": 0, "99": None})
        self.http.assert_not_called()

    def test_xp_uses_requested_year_and_trims_team_numbers(self):
        response = self.client.get("/xp?teams=27,%2033&year=2027")
        self.assertEqual(response.get_json(), {"27": 1900, "33": None})

    def test_epa_keeps_existing_scalar_response(self):
        response = self.client.get("/epa?teams=27,33,99&year=2026")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"27": None, "33": 2000, "99": None})

    def test_draft_xp_uses_same_season_as_epa_and_excludes_picked_teams(self):
        for draft_id, expected_epa, expected_xp in ((1, 0, 2129), (2, 1800, 1900)):
            with self.subTest(draft_id=draft_id):
                response = self.client.get(f"/drafts/{draft_id}/availableTeams")
                self.assertEqual(response.status_code, 200)
                teams = {row["team_number"]: row for row in response.get_json()}
                self.assertEqual(teams["27"]["match13_xp"], expected_xp)
                self.assertEqual(teams["27"]["year_end_epa"], expected_epa)
                self.assertIsNone(teams["99"]["match13_xp"])
                self.assertEqual(teams["27"]["events"], [{"event_key": "2027test", "week": 1}])
                if draft_id == 1:
                    self.assertNotIn("33", teams)

    def test_xp_requires_parameters(self):
        for url in ("/xp?teams=27", "/xp?year=2026", "/xp?teams=27&year=abc"):
            self.assertEqual(self.client.get(url).status_code, 400)


if __name__ == "__main__":
    unittest.main()
