"""Daily announcements scheduled in New York local time."""

import datetime
import logging
import os
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

logger = logging.getLogger("discord")
NEW_YORK = ZoneInfo("America/New_York")


class Announcements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.daily_announcement.start()

    def cog_unload(self):
        self.daily_announcement.cancel()

    @tasks.loop(time=datetime.time(hour=16, tzinfo=NEW_YORK))
    async def daily_announcement(self):
        raw_channel_id = os.getenv("ANNOUNCEMENTS_CHANNEL_ID")
        if not raw_channel_id:
            logger.warning("Daily announcement skipped: ANNOUNCEMENTS_CHANNEL_ID is not set.")
            return
        try:
            channel_id = int(raw_channel_id)
            if channel_id <= 0:
                raise ValueError
        except ValueError:
            logger.error("Daily announcement skipped: ANNOUNCEMENTS_CHANNEL_ID must be a positive integer.")
            return

        try:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            await channel.send("testing")
        except (discord.HTTPException, discord.InvalidData, AttributeError):
            # Keep the loop alive so the next day's announcement is attempted.
            logger.exception("Could not send the daily announcement.")

    @daily_announcement.before_loop
    async def before_daily_announcement(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Announcements(bot))
