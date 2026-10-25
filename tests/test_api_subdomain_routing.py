import importlib
import os
import unittest
from unittest.mock import patch

# Register related metadata while keeping all checks independent of a database.
from models.users import Player

with patch.dict(os.environ, {"DATABASE_URL": "sqlite://"}):
    api = importlib.import_module("app")


class APISubdomainRoutingTests(unittest.TestCase):
    def setUp(self):
        self.schema_patch = patch.object(api.app, "_schema_initialized", True, create=True)
        self.schema_patch.start()
        self.client = api.app.test_client()

    def tearDown(self):
        self.schema_patch.stop()

    def test_all_api_routes_are_registered_without_prefix(self):
        routes = {rule.rule for rule in api.app.url_map.iter_rules()}
        self.assertIn("/currentWeek", routes)
        self.assertIn("/leagues", routes)
        self.assertIn("/epa", routes)
        self.assertIn("/xp", routes)
        self.assertIn("/drafts/<int:draftId>/availableTeams", routes)
        self.assertIn("/leagues/<int:leagueId>/availableTeams", routes)
        self.assertFalse(any(path.startswith("/api/") for path in routes))

    def test_old_prefixed_urls_are_not_registered(self):
        for path in ("/api/leagues", "/api/xp", "/api/apidocs/"):
            with self.subTest(path=path):
                response = self.client.get(path, base_url="https://api.fantasyfim.com")
                self.assertEqual(response.status_code, 404)

    def test_swagger_targets_new_host_and_unprefixed_paths(self):
        response = self.client.get(
            "/apidocs/swagger.json", base_url="https://api.fantasyfim.com"
        )
        self.assertEqual(response.status_code, 200)
        spec = response.get_json()
        self.assertEqual(spec["host"], "api.fantasyfim.com")
        self.assertEqual(spec["basePath"], "/")
        self.assertEqual(spec["schemes"], ["https"])
        self.assertIn("/leagues", spec["paths"])
        self.assertIn("/epa", spec["paths"])
        self.assertIn("/xp", spec["paths"])
        self.assertFalse(any(path.startswith("/api/") for path in spec["paths"]))

    def test_swagger_ui_uses_new_spec_route(self):
        response = self.client.get("/apidocs/", base_url="https://api.fantasyfim.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/apidocs/swagger.json", response.data)


if __name__ == "__main__":
    unittest.main()
