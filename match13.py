"""Read normalized season XP from the match13 API."""

import asyncio
import math


async def fetch_norm_xp(http, endpoint, headers, year):
    """Fetch all pages before returning integer XP keyed by team number."""
    values = {}
    page = 1
    while True:
        for attempt in range(4):
            async with http.get(
                endpoint,
                headers=headers,
                params={"page": page, "limit": 1000, "scope": "season"},
                allow_redirects=False,
            ) as response:
                if response.status == 429 and attempt < 3:
                    try:
                        delay = float(response.headers.get("Retry-After", "5"))
                    except ValueError:
                        delay = 5
                    if not math.isfinite(delay):
                        delay = 5
                    await asyncio.sleep(min(max(delay, 1), 60))
                    continue
                if response.status != 200:
                    raise RuntimeError(
                        f"match13 returned HTTP {response.status} on page {page}."
                    )
                payload = await response.json()
                break

        if not isinstance(payload, dict) or payload.get("year") != year:
            raise ValueError("Unexpected season in match13 response.")
        teams = payload.get("teams")
        if not isinstance(teams, list) or payload.get("page") != page:
            raise ValueError("Invalid match13 page response.")
        if "nextPage" not in payload:
            raise ValueError("match13 response is missing nextPage.")
        for row in teams:
            if not isinstance(row, dict):
                raise ValueError("Invalid match13 team row.")
            team = row.get("teamNumber")
            if type(team) is not int or team <= 0 or row.get("year") != year:
                raise ValueError("Invalid match13 team number or year.")
            xp = row.get("normXp")
            if xp is None:
                continue
            if type(xp) not in (int, float) or not math.isfinite(xp):
                raise ValueError(f"Invalid normXp for team {team}.")
            # Round to the nearest integer before database storage.
            xp = round(xp)
            if not -(2**31) <= xp < 2**31:
                raise ValueError(f"normXp for team {team} exceeds integer storage.")
            values[str(team)] = xp

        next_page = payload["nextPage"]
        if next_page is None:
            return values
        if type(next_page) is not int or not page < next_page <= 10000:
            raise ValueError("Invalid match13 nextPage.")
        page = next_page
