"""Daily announcements scheduled in New York local time."""

import datetime
import logging
import os
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from sqlalchemy import update

from models.scores import WeekStatus

logger = logging.getLogger("discord")
NEW_YORK = ZoneInfo("America/New_York")


class Announcements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.daily_announcement.start()
        self.lineup_lock_check.start()

    def cog_unload(self):
        self.daily_announcement.cancel()
        self.lineup_lock_check.cancel()

    @tasks.loop(time=datetime.time(hour=16, tzinfo=NEW_YORK))
    async def daily_announcement(self):
        await self.send_announcement("testing")

    async def send_announcement(self, content):
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
            await channel.send(content)
        except (discord.HTTPException, discord.InvalidData, AttributeError):
            # Keep the loop alive so the next day's announcement is attempted.
            logger.exception("Could not send the daily announcement.")

    @tasks.loop(seconds=60)
    async def lineup_lock_check(self):
        try:
            locked_weeks = await self.lock_due_lineups()
            if locked_weeks:
                await self.send_announcement("testing lock lineups")
        except Exception:
            # Rollback is handled by the transaction; retry on the next check.
            logger.exception("Automatic lineup lock check failed.")

    @lineup_lock_check.before_loop
    async def before_lineup_lock_check(self):
        await self.bot.wait_until_ready()

    async def lock_due_lineups(self, now=None):
        """Atomically lock due active weeks, including deadlines missed offline."""
        if now is None:
            now = datetime.datetime.now(NEW_YORK)
        else:
            now = now.astimezone(NEW_YORK)
        cutoff_date = now.date()
        if now.hour < 16:
            cutoff_date -= datetime.timedelta(days=1)

        async with self.bot.async_session() as session:
            async with session.begin():
                result = await session.execute(
                    update(WeekStatus)
                    .where(
                        WeekStatus.active.is_(True),
                        WeekStatus.lineups_locked.is_(False),
                        WeekStatus.week_start_date.is_not(None),
                        WeekStatus.week_start_date <= cutoff_date,
                    )
                    .values(lineups_locked=True)
                    .returning(WeekStatus.year, WeekStatus.week)
                )
                locked_weeks = result.all()
            return locked_weeks

    @daily_announcement.before_loop
    async def before_daily_announcement(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Announcements(bot))
