import unittest
from unittest.mock import AsyncMock, patch

from match13 import fetch_norm_xp


class Response:
    def __init__(self, payload, status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.payload


class HTTP:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.pages = []

    def get(self, endpoint, **kwargs):
        self.pages.append(kwargs["params"]["page"])
        return next(self.responses)


def page(number, next_page, rows):
    return {"year": 2025, "page": number, "nextPage": next_page, "teams": rows}


def team(number, norm_xp):
    return {"year": 2025, "teamNumber": number, "normXp": norm_xp, "xp": 99.9}


class Match13Tests(unittest.IsolatedAsyncioTestCase):
    async def test_follows_next_page_and_uses_normalized_xp(self):
        http = HTTP([
            Response(page(1, 3, [team(2056, 2128.5535)])),
            Response(page(3, None, [team(1323, 0), team(1690, None)])),
        ])
        values = await fetch_norm_xp(http, "https://example.test", {}, 2025)
        self.assertEqual(values, {"2056": 2128, "1323": 0})
        self.assertEqual(http.pages, [1, 3])

    async def test_later_page_failure_does_not_return_partial_values(self):
        http = HTTP([
            Response(page(1, 2, [team(2056, 2128.5535)])),
            Response({}, status=500),
        ])
        with self.assertRaisesRegex(RuntimeError, "HTTP 500 on page 2"):
            await fetch_norm_xp(http, "https://example.test", {}, 2025)

    async def test_rejects_missing_or_looping_pagination(self):
        for next_page in (1, 0, True, "2", 10001):
            with self.subTest(next_page=next_page):
                http = HTTP([Response(page(1, next_page, []))])
                with self.assertRaisesRegex(ValueError, "nextPage"):
                    await fetch_norm_xp(http, "https://example.test", {}, 2025)
        http = HTTP([Response({"year": 2025, "page": 1, "teams": []})])
        with self.assertRaisesRegex(ValueError, "nextPage"):
            await fetch_norm_xp(http, "https://example.test", {}, 2025)

    async def test_retries_rate_limit_on_same_page(self):
        http = HTTP([
            Response({}, status=429, headers={"Retry-After": "2"}),
            Response(page(1, None, [team(2056, 2128.5535)])),
        ])
        with patch("match13.asyncio.sleep", new_callable=AsyncMock) as sleep:
            values = await fetch_norm_xp(http, "https://example.test", {}, 2025)
        sleep.assert_awaited_once_with(2.0)
        self.assertEqual(http.pages, [1, 1])
        self.assertEqual(values, {"2056": 2128})

    async def test_rejects_invalid_values_and_wrong_season(self):
        for value in (True, "2128", float("nan"), float("inf"), 2**31):
            with self.subTest(value=value):
                http = HTTP([Response(page(1, None, [team(2056, value)]))])
                with self.assertRaises(ValueError):
                    await fetch_norm_xp(http, "https://example.test", {}, 2025)
        payload = page(1, None, [])
        payload["year"] = 2024
        with self.assertRaisesRegex(ValueError, "season"):
            await fetch_norm_xp(HTTP([Response(payload)]), "https://example.test", {}, 2025)


if __name__ == "__main__":
    unittest.main()
