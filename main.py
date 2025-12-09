import asyncio
import logging
import os
import threading
import time

import discord
from discord import Embed
from discord.ext import commands
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import cogs.admin as admin
from models.base import Base
from models.scores import FantasyTeam, League, PlayerAuthorized, WeekStatus

load_dotenv()

logger = logging.getLogger("discord")

intents = discord.Intents.default()
intents.message_content = True

# Convert postgres:// to postgresql+asyncpg:// for async driver
conn_str = os.getenv("DATABASE_URL")
if conn_str and conn_str.startswith("postgresql://"):
    conn_str = conn_str.replace("postgresql://", "postgresql+asyncpg://", 1)
elif conn_str and conn_str.startswith("postgres://"):
    conn_str = conn_str.replace("postgres://", "postgresql+asyncpg://", 1)


class FantasyFiMBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="/",
            intents=discord.Intents.all(),
            application_id=os.getenv("DISCORD_APPLICATION_ID"),
        )

        # Async-only engine optimized for Neon
        self.engine = create_async_engine(
            conn_str,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=180,
            connect_args={"ssl": True},
        )
        self.async_session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def setup_db(self):
        """Initialize database tables"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def log_message(
        self, title="Title", message="Message", embed: discord.Embed = None
    ):
        logChannel = await self.fetch_channel(int(os.getenv("LOGGING_CHANNEL_ID")))
        embed = Embed(title=f"{title}", description=f"{message}")
        if not embed is None:
            embed = embed
        return await logChannel.send(embed=embed)

    def run_scheduled_district_update(self):
        while True:
            now = time.localtime()
            if now.tm_hour == 7 and now.tm_min == 0:
                asyncio.run_coroutine_threadsafe(self.district_update_job(), self.loop)
            time.sleep(60)

    async def district_update_job(self):
        adminCog = admin.Admin(self)
        await adminCog.importFullDistrctTask(2026)

    async def verifyTeamMember(
        self, interaction: discord.Interaction, user: discord.User
    ):
        async with self.async_session() as session:
            # Get the fantasy team ID for the interaction user in this channel's league
            stmt = (
                select(FantasyTeam.fantasy_team_id)
                .join(
                    PlayerAuthorized,
                    PlayerAuthorized.fantasy_team_id == FantasyTeam.fantasy_team_id,
                )
                .join(League, FantasyTeam.league_id == League.league_id)
                .where(PlayerAuthorized.player_id == str(interaction.user.id))
                .where(League.discord_channel == str(interaction.channel_id))
            )
            result = await session.execute(stmt)
            row = result.first()

            if row is None:
                return False

            teamid = row.fantasy_team_id
            logger.info(f"teamid {teamid}")

            # Check if the given user is authorized in the same team
            user_stmt = (
                select(PlayerAuthorized)
                .where(PlayerAuthorized.player_id == str(user.id))
                .where(PlayerAuthorized.fantasy_team_id == teamid)
            )
            user_result = await session.execute(user_stmt)
            return user_result.first() is not None

    async def verifyTeamMemberByTeamId(self, fantasyId: int, user: discord.User):
        async with self.async_session() as session:
            stmt = (
                select(PlayerAuthorized)
                .where(PlayerAuthorized.player_id == str(user.id))
                .where(PlayerAuthorized.fantasy_team_id == int(fantasyId))
            )
            result = await session.execute(stmt)
            return result.first() is not None

    async def verifyNotInLeague(
        self, interaction: discord.Interaction, user: discord.User
    ):
        async with self.async_session() as session:
            stmt = (
                select(PlayerAuthorized)
                .join(
                    FantasyTeam,
                    PlayerAuthorized.fantasy_team_id == FantasyTeam.fantasy_team_id,
                )
                .join(League, FantasyTeam.league_id == League.league_id)
                .where(PlayerAuthorized.player_id == str(user.id))
                .where(League.discord_channel == str(interaction.channel_id))
            )
            result = await session.execute(stmt)
            found_teams = result.all()

            # Return True if user is NOT in the league (no teams found)
            return len(found_teams) == 0

    async def getCurrentWeek(self) -> WeekStatus:
        async with self.async_session() as session:
            stmt = (
                select(WeekStatus)
                .where(WeekStatus.active)
                .order_by(WeekStatus.year.asc(), WeekStatus.week.asc())
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def setup_hook(self):
        await self.setup_db()
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.scores")
        await self.load_extension("cogs.admin")
        await self.load_extension("cogs.drafting")
        await self.load_extension("cogs.manageteam")
        await self.tree.sync(guild=discord.Object(id=os.getenv("GUILD_ID")))

    async def on_ready(self):
        logger.info("The bot is alive!")

        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.competing, name=str("Fantasy FiM!")
            )
        )

        threading.Thread(target=self.run_scheduled_district_update, daemon=True).start()

        logger.info("Bot startup complete!")


bot = FantasyFiMBot()

bot.run(os.getenv("DISCORD_BOT_TOKEN"), reconnect=True)
