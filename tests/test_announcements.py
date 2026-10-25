import datetime
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from cogs.announcements import Announcements


class DailyAnnouncementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.channel = SimpleNamespace(send=AsyncMock())
        self.bot = SimpleNamespace(
            get_channel=Mock(return_value=self.channel),
            fetch_channel=AsyncMock(return_value=self.channel),
            wait_until_ready=AsyncMock(),
        )
        self.cog = Announcements(self.bot)

    async def run_announcement(self, channel_id="123"):
        with patch.dict(os.environ, {"ANNOUNCEMENTS_CHANNEL_ID": channel_id}):
            await Announcements.daily_announcement.coro(self.cog)

    async def test_sends_exact_message_to_configured_channel(self):
        await self.run_announcement()
        self.bot.get_channel.assert_called_once_with(123)
        self.channel.send.assert_awaited_once_with("testing")
        self.bot.fetch_channel.assert_not_awaited()

    async def test_fetches_channel_when_not_cached(self):
        self.bot.get_channel.return_value = None
        await self.run_announcement()
        self.bot.fetch_channel.assert_awaited_once_with(123)
        self.channel.send.assert_awaited_once_with("testing")

    async def test_missing_or_invalid_channel_skips_send(self):
        for value in ("", "invalid", "0", "-1"):
            with self.subTest(value=value):
                await self.run_announcement(value)
        self.channel.send.assert_not_awaited()
        self.bot.fetch_channel.assert_not_awaited()

    async def test_send_failure_does_not_prevent_next_invocation(self):
        response = SimpleNamespace(status=403, reason="Forbidden")
        self.channel.send.side_effect = [
            discord.Forbidden(response, "Missing permissions"), None
        ]
        await self.run_announcement()
        await self.run_announcement()
        self.assertEqual(self.channel.send.await_count, 2)

    async def test_waits_for_bot_readiness(self):
        await Announcements.before_daily_announcement(self.cog)
        self.bot.wait_until_ready.assert_awaited_once()

    def test_schedule_tracks_daylight_saving_at_four_pm(self):
        scheduled = self.cog.daily_announcement.time[0]
        self.assertEqual((scheduled.hour, scheduled.minute), (16, 0))
        for month, expected_offset, name in ((1, -5, "EST"), (7, -4, "EDT")):
            local = datetime.datetime.combine(
                datetime.date(2026, month, 15), scheduled
            )
            self.assertEqual(local.utcoffset(), datetime.timedelta(hours=expected_offset))
            self.assertEqual(local.tzname(), name)


if __name__ == "__main__":
    unittest.main()
