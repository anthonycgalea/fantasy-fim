"""Lineup locking, score updates, and announcements in New York local time."""

import datetime
import logging
import os
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from sqlalchemy import delete, select, update

from models.scores import WeekStatus
from models.transactions import TradeProposal, TradeTeams

logger = logging.getLogger("discord")
NEW_YORK = ZoneInfo("America/New_York")


class Announcements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.lineup_lock_check.start()
        self.weekend_score_update.start()
        self.final_score_check.start()

    def cog_unload(self):
        self.lineup_lock_check.cancel()
        self.weekend_score_update.cancel()
        self.final_score_check.cancel()

    async def send_announcement(self, content):
        raw_channel_id = os.getenv("ANNOUNCEMENTS_CHANNEL_ID")
        if not raw_channel_id:
            logger.warning("Announcement skipped: ANNOUNCEMENTS_CHANNEL_ID is not set.")
            return
        try:
            channel_id = int(raw_channel_id)
            if channel_id <= 0:
                raise ValueError
        except ValueError:
            logger.error("Announcement skipped: ANNOUNCEMENTS_CHANNEL_ID must be a positive integer.")
            return

        try:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            await channel.send(content)
        except (discord.HTTPException, discord.InvalidData, AttributeError):
            # Keep scheduled jobs alive after a Discord delivery failure.
            logger.exception("Could not send the announcement.")

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
                if locked_weeks:
                    # Same cleanup as manually running /locklineups.
                    await session.execute(delete(TradeTeams))
                    await session.flush()
                    await session.execute(delete(TradeProposal))
            return locked_weeks

    @tasks.loop(time=datetime.time(hour=22, tzinfo=NEW_YORK))
    async def weekend_score_update(self):
        try:
            await self.run_scheduled_score_updates()
        except Exception:
            logger.exception("Scheduled non-final score update failed.")

    @weekend_score_update.before_loop
    async def before_weekend_score_update(self):
        await self.bot.wait_until_ready()

    async def run_scheduled_score_updates(self, now=None):
        now = datetime.datetime.now(NEW_YORK) if now is None else now.astimezone(NEW_YORK)
        if now.weekday() not in (4, 5):
            return
        async with self.bot.async_session() as session:
            result = await session.execute(
                select(WeekStatus.year, WeekStatus.week)
                .where(
                    WeekStatus.active.is_(True),
                    WeekStatus.lineups_locked.is_(True),
                    WeekStatus.scores_finalized.is_(False),
                )
                .order_by(WeekStatus.year, WeekStatus.week)
            )
            weeks = result.all()
        if not weeks:
            return
        admin = self.bot.get_cog("Admin")
        if admin is None:
            logger.error("Scheduled scoring skipped: Admin cog is not loaded.")
            return
        for year, week in weeks:
            try:
                await admin.runScoreUpdate(None, year, week, final=False, states=False)
            except Exception:
                logger.exception("Scheduled scoring failed for %s week %s", year, week)


    @tasks.loop(seconds=60)
    async def final_score_check(self):
        try:
            await self.run_due_final_score_updates()
        except Exception:
            logger.exception("Automatic final score check failed.")

    @final_score_check.before_loop
    async def before_final_score_check(self):
        await self.bot.wait_until_ready()

    async def run_due_final_score_updates(self, now=None):
        now = datetime.datetime.now(NEW_YORK) if now is None else now.astimezone(NEW_YORK)
        cutoff_date = now.date()
        if now.hour < 21:
            cutoff_date -= datetime.timedelta(days=1)
        async with self.bot.async_session() as session:
            result = await session.execute(
                select(WeekStatus.year, WeekStatus.week)
                .where(
                    WeekStatus.active.is_(True),
                    WeekStatus.scores_finalized.is_(False),
                    WeekStatus.week_end_date.is_not(None),
                    WeekStatus.week_end_date <= cutoff_date,
                )
                .order_by(WeekStatus.year, WeekStatus.week)
            )
            weeks = result.all()
        if not weeks:
            return
        admin = self.bot.get_cog("Admin")
        if admin is None:
            logger.error("Automatic final scoring skipped: Admin cog is not loaded.")
            return
        for year, week in weeks:
            try:
                await admin.runScoreUpdate(None, year, week, final=True, states=False)
            except Exception:
                # Failed scoring remains unfinalized and is retried next minute.
                logger.exception("Automatic final scoring failed for %s week %s", year, week)


async def setup(bot):
    await bot.add_cog(Announcements(bot))
