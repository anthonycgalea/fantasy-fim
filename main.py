import discord
from discord.ext import commands
from discord import Embed
import os
import logging
import logging.handlers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models.base import Base
from models.scores import PlayerAuthorized, League, FantasyTeam, WeekStatus
import cogs.admin as admin
import time
import threading


load_dotenv()

logger = logging.getLogger('discord')

intents = discord.Intents.default()
intents.message_content = True

conn_str = os.getenv("DATABASE_URL")

class FantasyFiMBot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix="/",
                         intents=discord.Intents.all(),
                         applpication_id=os.getenv("DISCORD_APPLICATION_ID"))

        self.engine = create_engine(url=conn_str, pool_size=20, max_overflow=40, pool_pre_ping=True, pool_recycle=60)
        self.session = self.engine.connect()
        Base.metadata.create_all(self.engine)

    async def log_message(self, title="Title", message="Message", embed: discord.Embed=None):
        logChannel = await self.fetch_channel(int(os.getenv("LOGGING_CHANNEL_ID")))
        embed = Embed(title=f"{title}", description=f"{message}")
        if not embed == None:
            embed=embed
        return await logChannel.send(embed = embed)

    def run_scheduled_district_update(self):
        while True:
            now = time.localtime()
            if now.tm_hour == 7 and now.tm_min == 0:
                self.loop.create_task(self.district_update_job())
            time.sleep(60)

    async def district_update_job(self):
        adminCog = admin.Admin(self)
        await adminCog.importFullDistrctTask(2025)

    async def get_session(self):
        Session = sessionmaker(bind=self.engine)
        return Session()
    
    async def verifyTeamMember(self, interaction: discord.Interaction, user: discord.User):
        session = await self.get_session()

        # Perform the query with correct joins and conditions
        largeQuery = session.query(PlayerAuthorized, FantasyTeam, League)\
            .join(FantasyTeam, PlayerAuthorized.fantasy_team_id == FantasyTeam.fantasy_team_id)\
            .join(League, FantasyTeam.league_id == League.league_id)\
            .filter(PlayerAuthorized.player_id == str(interaction.user.id))\
            .filter(League.discord_channel == str(interaction.channel_id))

        # Check if the query returns any results
        if largeQuery.count() == 0:
            session.close()
            return False

        # Get the fantasy team ID from the first result row
        teamid = largeQuery.first().FantasyTeam.fantasy_team_id
        logger.info(f"teamid {teamid}")

        # Now check if the given user is authorized in the same team
        users = session.query(PlayerAuthorized)\
            .filter(PlayerAuthorized.player_id == str(user.id))\
            .filter(PlayerAuthorized.fantasy_team_id == int(teamid))

        session.close()
        return users.count() > 0
    
    async def verifyTeamMemberByTeamId(self, fantasyId: int, user: discord.User):
        session = await self.get_session()

        # Now check if the given user is authorized in the same team
        users = session.query(PlayerAuthorized)\
            .filter(PlayerAuthorized.player_id == str(user.id))\
            .filter(PlayerAuthorized.fantasy_team_id == int(fantasyId))

        session.close()
        return users.count() > 0

    async def verifyNotInLeague(self, interaction: discord.Interaction, user: discord.User):
        session = await self.get_session()

        # Query to find any fantasy team in the league where the user is already a member
        existingTeamQuery = session.query(PlayerAuthorized)\
            .join(FantasyTeam, PlayerAuthorized.fantasy_team_id == FantasyTeam.fantasy_team_id)\
            .join(League, FantasyTeam.league_id == League.league_id)\
            .filter(PlayerAuthorized.player_id == str(user.id))\
            .filter(League.discord_channel == str(interaction.channel_id))

        # Debugging: Print or log the results to see if the query is returning anything
        found_teams = existingTeamQuery.all()

        if len(found_teams) > 0:
            session.close()
            return False  # The user is already part of the league

        session.close()
        return True  # The user is not part of the league

    async def getCurrentWeek(self) -> WeekStatus:
        session = await self.get_session()
        week = session.query(WeekStatus).filter(WeekStatus.active==True).order_by(WeekStatus.year.asc()).order_by(WeekStatus.week.asc()).first()
        session.close() 
        return week

    async def setup_hook(self):
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.scores")
        await self.load_extension("cogs.admin")
        await self.load_extension("cogs.drafting")
        await self.load_extension("cogs.manageteam")
        await self.tree.sync(guild=discord.Object(id=os.getenv("GUILD_ID")))

    async def on_ready(self):
        logger.info("The bot is alive!")

        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.competing, name=str("Fantasy FiM!")))
        
        threading.Thread(target=self.run_scheduled_district_update, daemon=True).start()

        logger.info("Bot startup complete!")


bot = FantasyFiMBot()

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
