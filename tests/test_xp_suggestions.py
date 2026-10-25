import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cogs.drafting import Drafting
from models.base import Base
from models.draft import DraftPick, StatboticsData
from models.scores import FRCEvent, Team, TeamScore


class AsyncSessionAdapter:
    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    async def execute(self, statement):
        return self.session.execute(statement)


class XPSuggestionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add(FRCEvent(
                event_key="2027test", event_name="Test", year=2027,
                week=1, is_fim=True,
            ))
            for number, xp, epa in (
                ("27", 2000, 100), ("33", 2500, 50),
                ("44", 0, 500), ("55", None, 600), ("66", 9000, 1000),
            ):
                session.add(Team(team_number=number, name=number, is_fim=True))
                session.add(TeamScore(team_key=number, event_key="2027test"))
                session.add(StatboticsData(
                    team_number=number, year=2026,
                    match13_xp=xp, year_end_epa=epa,
                ))
                session.add(StatboticsData(
                    team_number=number, year=2027,
                    match13_xp=3000 if number == "27" else xp, year_end_epa=epa,
                ))
            session.add(DraftPick(
                fantasy_team_id=1, draft_id=1, pick_number=1, team_number="66"
            ))
            session.commit()
        self.cog = Drafting(SimpleNamespace(
            async_session=lambda: AsyncSessionAdapter(self.engine)
        ))

    def tearDown(self):
        self.engine.dispose()

    async def suggestions(self, is_fim=False, offseason=False):
        return await self.cog.getSuggestedTeamsList(
            "2027test", 2027, is_fim, 1, offseason
        )

    async def test_regular_and_fim_rank_by_previous_year_xp_not_epa(self):
        for is_fim in (False, True):
            with self.subTest(is_fim=is_fim):
                rows = await self.suggestions(is_fim=is_fim)
                self.assertEqual(
                    [tuple(row) for row in rows],
                    [("33", 2500), ("27", 2000), ("44", 0), ("55", None)],
                )

    async def test_offseason_uses_current_year_xp(self):
        rows = await self.suggestions(offseason=True)
        self.assertEqual(rows[0][0], "27")
        self.assertEqual(rows[0][1], 3000)
        self.assertNotIn("66", [row[0] for row in rows])

    async def test_embed_labels_xp_and_displays_zero_and_missing_values(self):
        self.cog.getDraftFromChannel = AsyncMock(
            return_value=SimpleNamespace(draft_id=1, event_key="2027test")
        )
        self.cog.getLeague = AsyncMock(
            return_value=SimpleNamespace(year=2027, is_fim=True, offseason=False)
        )
        message = SimpleNamespace(edit=AsyncMock())
        interaction = SimpleNamespace(original_response=AsyncMock(return_value=message))
        await self.cog.postSuggestedTeams(interaction)
        text = message.edit.call_args.kwargs["embed"].description
        self.assertIn("2026 XP", text)
        self.assertNotIn("EPA", text)
        self.assertIn("0", next(line for line in text.splitlines() if line.strip().startswith("44")))
        self.assertIn("—", next(line for line in text.splitlines() if line.strip().startswith("55")))

    async def test_autodraft_picks_highest_xp_team(self):
        self.cog.getDraftFromChannel = AsyncMock(
            return_value=SimpleNamespace(draft_id=1, event_key="2027test")
        )
        self.cog.getLeague = AsyncMock(
            return_value=SimpleNamespace(year=2027, is_fim=True, offseason=False)
        )
        self.cog.makeDraftPickHandler = AsyncMock()
        message = SimpleNamespace(edit=AsyncMock())
        interaction = SimpleNamespace(
            response=SimpleNamespace(send_message=AsyncMock()),
            original_response=AsyncMock(return_value=message),
        )
        await Drafting.auto_draft.callback(self.cog, interaction)
        self.cog.makeDraftPickHandler.assert_awaited_once_with(
            interaction=interaction, team_number="33", force=False
        )


if __name__ == "__main__":
    unittest.main()
