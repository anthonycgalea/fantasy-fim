import importlib
import os
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.scores import League

# Import the API without using any configured database or connecting to a server.
with patch.dict(os.environ, {'DATABASE_URL': 'sqlite://'}):
    api = importlib.import_module('app')


class LeagueFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.year = date.today().year
        with self.session_factory() as session:
            for league_id, year, offseason, active in (
                (1, self.year, False, True),
                (2, self.year, True, True),
                (3, self.year - 1, False, True),
                (4, self.year - 1, True, True),
                (5, self.year - 1, False, False),
                (6, self.year, False, False),
            ):
                session.add(League(league_id=league_id, league_name=str(league_id),
                                   year=year, offseason=offseason, active=active,
                                   discord_channel='10', team_size_limit=3))
            session.commit()
        self.session_patch = patch.object(api, 'Session', self.session_factory)
        self.session_patch.start()
        # Schema is already initialized in this test's isolated database.
        self.schema_patch = patch.object(api.app, '_schema_initialized', True, create=True)
        self.schema_patch.start()
        self.client = api.app.test_client()

    def tearDown(self):
        self.schema_patch.stop()
        self.session_patch.stop()
        self.engine.dispose()

    def ids(self, query=''):
        response = self.client.get('/api/leagues' + query)
        self.assertEqual(response.status_code, 200)
        return {league['league_id'] for league in response.get_json()}

    def test_defaults_to_current_year_and_both_offseason_types(self):
        self.assertEqual(self.ids(), {1, 2})

    def test_explicit_prior_year_includes_inactive_and_both_offseason_types(self):
        self.assertEqual(self.ids(f'?year={self.year - 1}'), {3, 4, 5})

    def test_offseason_true_and_false_for_prior_year(self):
        self.assertEqual(self.ids(f'?year={self.year - 1}&offseason=true'), {4})
        self.assertEqual(self.ids(f'?year={self.year - 1}&offseason=false'), {3, 5})

    def test_offseason_filter_without_year_uses_current_year(self):
        self.assertEqual(self.ids('?offseason=false'), {1})
        self.assertEqual(self.ids('?offseason=true'), {2})

    def test_invalid_filters_return_bad_request(self):
        for query in ('?year=abc', '?year=', '?offseason=maybe', '?offseason='):
            with self.subTest(query=query):
                self.assertEqual(self.client.get('/api/leagues' + query).status_code, 400)

    def test_year_with_no_leagues_returns_empty_list(self):
        self.assertEqual(self.ids('?year=1900'), set())

    def test_explicit_current_year_also_includes_inactive(self):
        self.assertEqual(self.ids(f'?year={self.year}'), {1, 2, 6})

    def test_retrieve_active_and_inactive_leagues_by_id(self):
        for league_id in (1, 5, 6):
            with self.subTest(league_id=league_id):
                response = self.client.get(f'/api/leagues/{league_id}')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()['league_id'], league_id)

    def test_retrieve_missing_league_returns_not_found(self):
        response = self.client.get('/api/leagues/999')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {'error': 'League not found'})
