import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from cogs.admin import Admin
from models.base import Base
from models.draft import Draft, DraftPick
from models.scores import League, TeamOwned, TeamScore
from models.users import Player


class AsyncSessionAdapter:
    """Run the command's SQL against an isolated SQLite database."""

    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()


class SwapDraftPickTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([
                Player(user_id='99', is_admin=True),
                League(league_id=1, league_name='Offseason', offseason=True,
                       year=2026, discord_channel='10', team_size_limit=3),
                Draft(draft_id=1, league_id=1, event_key='2026test', discord_channel='10'),
                Draft(draft_id=2, league_id=1, event_key='2026other', discord_channel='20'),
                DraftPick(draft_id=1, fantasy_team_id=5, pick_number=1, team_number='123'),
                DraftPick(draft_id=1, fantasy_team_id=6, pick_number=2, team_number='789'),
                DraftPick(draft_id=2, fantasy_team_id=7, pick_number=1, team_number='123'),
                TeamScore(team_key='456', event_key='2026test'),
                TeamOwned(draft_id=1, league_id=1, fantasy_team_id=5, team_key='123'),
            ])
            session.commit()
        self.bot = SimpleNamespace(async_session=lambda: AsyncSessionAdapter(self.engine))
        self.cog = Admin(self.bot)
        self.message = SimpleNamespace(edit=AsyncMock())
        self.interaction = SimpleNamespace(
            user=SimpleNamespace(id=99), channel_id=10,
            response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
            original_response=AsyncMock(return_value=self.message),
        )

    def tearDown(self):
        self.engine.dispose()

    async def invoke(self, original='123', replacement='456'):
        await Admin.swapDraftPick.callback(self.cog, self.interaction, original, replacement)

    def pick(self, draft_id=1):
        with Session(self.engine) as session:
            return session.scalar(select(DraftPick.team_number).where(
                DraftPick.draft_id == draft_id, DraftPick.pick_number == 1))

    async def test_swaps_any_teams_pick_and_roster_only_in_current_draft(self):
        await self.invoke()
        self.assertEqual(self.pick(), '456')
        self.assertEqual(self.pick(2), '123')
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(TeamOwned.team_key)), '456')
        self.assertIn('fantasy team 5', self.message.edit.call_args.kwargs['content'])

    async def test_regular_season_rejected(self):
        with Session(self.engine) as session:
            session.get(League, 1).offseason = False
            session.commit()
        await self.invoke()
        self.assertEqual(self.pick(), '123')
        self.assertIn('offseason', self.message.edit.call_args.kwargs['content'])

    async def test_non_admin_rejected(self):
        self.interaction.user.id = 100
        await self.invoke()
        self.assertEqual(self.pick(), '123')
        self.interaction.response.defer.assert_not_awaited()
        self.interaction.response.send_message.assert_awaited_once()

    async def test_invalid_swaps_leave_pick_unchanged(self):
        for original, replacement in [('123', '789'), ('123', '999'),
                                      ('999', '456'), ('123', '123'),
                                      ('-1', '456'), ('123', 'abc')]:
            with self.subTest(original=original, replacement=replacement):
                await self.invoke(original, replacement)
                self.assertEqual(self.pick(), '123')

    async def test_wrong_channel_rejected(self):
        self.interaction.channel_id = 999
        await self.invoke()
        self.assertEqual(self.pick(), '123')
        self.assertIn('No draft', self.message.edit.call_args.kwargs['content'])

    async def test_active_draft_without_roster(self):
        with Session(self.engine) as session:
            session.delete(session.scalar(select(TeamOwned)))
            session.commit()
        await self.invoke()
        self.assertEqual(self.pick(), '456')
