import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
from models.scores import *
from models.transactions import TeamOnWaivers

logger = logging.getLogger('discord')

class Scores(commands.Cog):
  def __init__(self, bot):
    self.bot = bot

  async def getFRCTeamReport(self, interaction: discord.Interaction, frcTeam: str):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    leagueToGrabReport: League = session.query(League).filter(League.discord_channel==str(interaction.channel_id)).first()
    frcTeamToReport: Team = session.query(Team).filter(Team.team_number==frcTeam).filter(Team.is_fim==True).first()
    if not leagueToGrabReport:
      await message.edit(content="No league associated with this channel.")
    elif not frcTeamToReport:
      await message.edit(content="No league associated with this channel.")
    else:
      # Variables to fill in before the snippet

      team_number = frcTeamToReport.team_number
      team_name = frcTeamToReport.name
      team_status = "Free Agent"  # Change to "On Waivers" or "Free Agent" as needed
      ownedBy: TeamOwned = session.query(TeamOwned).filter(TeamOwned.league_id==leagueToGrabReport.league_id)\
        .filter(TeamOwned.team_key==frcTeam).first()
      if ownedBy:
        team_status = f"Owned by {ownedBy.fantasyTeam.fantasy_team_name}"
      else:
        onWaivers: TeamOnWaivers = session.query(TeamOnWaivers).filter(TeamOnWaivers.league_id==leagueToGrabReport.league_id)\
                                                                .filter(TeamOnWaivers.team_number==frcTeam).first()
        if onWaivers:
          team_status = "On Waivers"
      team_starts = session.query(TeamStarted).filter(TeamStarted.team_number==frcTeam).filter(TeamStarted.league_id==leagueToGrabReport.league_id).count()
      events_attending = (
          session.query(TeamScore)
          .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key)  # Join with FRCEvent
          .filter(TeamScore.team_key == frcTeam)  # Filter by the team key
          .filter(FRCEvent.year == leagueToGrabReport.year)
          .order_by(FRCEvent.week)  # Order by the week attribute
          .all()
      )

      # Create the embed
      embed = discord.Embed(title=f"**Team {team_number} Report**", color=discord.Color.blue())

      # Add fields
      embed.add_field(name="Team Name", value=team_name, inline=False)
      embed.add_field(name="Team Status", value=team_status, inline=False)
      embed.add_field(name="Team Starts", value=str(team_starts), inline=False)

      # Format events attending using TeamScore objects
      events_info = "\n".join([f"{score.event.event_name} - {score.score_team()} points" if score.score_team() > 0 else f"{score.event.event_name} - Week {score.event.week}" for score in events_attending if score.event.is_fim==True])
      embed.add_field(name="Events Attending", value=events_info if events_info else "None", inline=False)

      # Send the embed (example)
      await message.edit(embed=embed)

  @app_commands.command(name="getrankings", description="Retrieves rankings for the channel's league")
  async def getRankings(self, interaction: discord.Interaction):
    await interaction.response.send_message("Retrieving rankings")
  
  @app_commands.command(name="teamreport", description="Retrieves a report of a specific FRC team in the channel's league")
  async def getTeamReport(self, interaction: discord.Interaction, frcteam: str):
    await interaction.response.send_message(f"Retrieving team report for team {frcteam}", ephemeral=True)
    await self.getFRCTeamReport(interaction, frcteam)

  @app_commands.command(name="weeklyreport", description="Retrieves a report of scores and rankings up to date for the current week in the channel's league")
  async def getWeekReport(self, interaction: discord.Interaction):
    await interaction.response.send_message(f"Retrieving report up to the most recent week")

async def setup(bot: commands.Bot) -> None:
  cog = Scores(bot)
  guild = await bot.fetch_guild(int(os.getenv("GUILD_ID")))
  assert guild is not None

  await bot.add_cog(
      cog,
    guilds=[guild]
  )