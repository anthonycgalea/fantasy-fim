import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
import random
from sqlalchemy import select, func
from models.scores import League, FantasyTeam, WeekStatus, FantasyScores, PlayerAuthorized
from models.transactions import WaiverPriority
from models.draft import Draft
from models.users import Player
from discord import Embed

logger = logging.getLogger('discord')
websiteURL = os.getenv("WEBSITE_URL")

class General(commands.Cog):
  def __init__(self, bot):
    self.bot = bot

  @app_commands.command(name="ping", description="Shows the bot is active")
  async def ping(self, interaction: discord.Interaction):
    latency = round(self.bot.latency * 1000, 2)
    await interaction.response.send_message(f"Testing Pong! Latency: {latency}ms")

  @app_commands.command(name="leagues", description="Reports on active leagues and their league ids.")
  async def getLeagues(self, interaction: discord.Interaction):
    async with self.bot.async_session() as session:
      stmt = select(League).where(League.active == True)
      result = await session.execute(stmt)
      leagues = result.scalars().all()
      embed = Embed(title="**League Listing**", description="")
      if len(leagues) == 0:
        embed.description+="No active leagues```"
        await interaction.response.send_message(embed=embed)
        return
      for league in leagues:
        embed.description += f'{league.league_name:>15s}   <#{league.discord_channel}>\n'
      await interaction.response.send_message(embed=embed)

  @app_commands.command(name="teams", description="Reports on teams in the channel's league and their team IDs.")
  async def getTeamsInLeague(self, interaction: discord.Interaction):
    async with self.bot.async_session() as session:
      stmt = select(League).where(League.discord_channel==str(interaction.channel_id))
      result = await session.execute(stmt)
      league = result.scalars().first()
      if league is None:
        await interaction.response.send_message("No league associated with this channel")
        return
      leagueid = league.league_id
      draftOrderEmbed = Embed(title=f"**Teams in {league.league_name}**", description=f"```{'Team ID':7s}{'':5s}{'Team Name (id)':30s}{'Waiver':^6s}\n")
      stmt = select(FantasyTeam).where(FantasyTeam.league_id==leagueid).order_by(FantasyTeam.fantasy_team_id.asc())
      result = await session.execute(stmt)
      fantasyTeams = result.scalars().all()
      for team in fantasyTeams:
        if team.waiver_priority==None:
          draftOrderEmbed.description+=f"{team.fantasy_team_id:>7d}{'':5s}{team.fantasy_team_name:30s}\n"  
        else:
          waiverprio = team.waiver_priority.priority
          draftOrderEmbed.description+=f"{team.fantasy_team_id:>7d}{'':5s}{team.fantasy_team_name:30s}{waiverprio:^6d}\n"  
      draftOrderEmbed.description+="```"
      await interaction.response.send_message(embed=draftOrderEmbed)

  @app_commands.command(name="waiverpriority", description="Reports on teams in the channel's league and their team IDs.")
  async def waiverPriorityReport(self, interaction: discord.Interaction):
    async with self.bot.async_session() as session:
      stmt = select(League).where(League.discord_channel==str(interaction.channel_id))
      result = await session.execute(stmt)
      league = result.scalars().first()
      if league is None:
        await interaction.response.send_message("No league associated with this channel")
        return
      leagueid = league.league_id
      draftOrderEmbed = Embed(title=f"**Teams in {league.league_name}**", description=f"```{'Team ID':7s}{'':5s}{'Team Name (id)':30s}{'Waiver':^6s}\n")
      stmt = select(WaiverPriority).where(WaiverPriority.league_id==leagueid).order_by(WaiverPriority.priority.asc())
      result = await session.execute(stmt)
      fantasyTeams = result.scalars().all()
      if not fantasyTeams:
        await interaction.response.send_message("No waiver priorities yet!")
        return
      for team in fantasyTeams:
        waiverprio = team.priority
        fantasyTeam = team.fantasy_team
        draftOrderEmbed.description+=f"{fantasyTeam.fantasy_team_id:>7d}{'':5s}{fantasyTeam.fantasy_team_name:30s}{waiverprio:^6d}\n"    
      draftOrderEmbed.description+="```"
      await interaction.response.send_message(embed=draftOrderEmbed)

  @app_commands.command(name="leaguesite", description="Retrieve a link to your league's webpage")
  async def getLeagueWebpage(self, interaction: discord.Interaction):
    async with self.bot.async_session() as session:
      stmt = select(League).where(League.discord_channel==str(interaction.channel_id))
      result = await session.execute(stmt)
      league = result.scalars().first()
      if league is None:
        await interaction.response.send_message("No league associated with this channel")
        return
      leagueid = league.league_id
      await interaction.response.send_message(f"{websiteURL}/leagues/{leagueid}")

  @app_commands.command(name="draftsite", description="Retrieve a link to your draft's webpage")
  async def getDraftWebpage(self, interaction: discord.Interaction):
    async with self.bot.async_session() as session:
      stmt = select(Draft).where(Draft.discord_channel==str(interaction.channel_id))
      result = await session.execute(stmt)
      draft = result.scalars().first()
      if draft is None:
        await interaction.response.send_message("No draft associated with this channel")
        return
      draftid = draft.draft_id
      await interaction.response.send_message(f"{websiteURL}/drafts/{draftid}")

  @app_commands.command(name="website", description="Retrieve a link to the fantasy FiM website")
  async def getWebsite(self, interaction: discord.Interaction):    
    await interaction.response.send_message(f"{websiteURL}")

  @app_commands.command(name="api", description="sends a link to the swagger page for the API")
  async def getAPI(self, interaction: discord.Interaction):
    await interaction.response.send_message(f"{websiteURL}/api/apidocs")

  @app_commands.command(name="weekstatus", description="Reports on the status of the current fantasy FiM week")
  async def getWeekStatus(self, interaction: discord.Interaction):
    currentWeek: WeekStatus = await self.bot.getCurrentWeek()
    embed = Embed(title=f"**Current Week: Week {currentWeek.week} of {currentWeek.year}**", description="")
    embed.description += "Lineup Setting: "
    if currentWeek.lineups_locked:
      embed.description += "LOCKED\nScores Finalized: "
      if currentWeek.scores_finalized:
        embed.description += "FINALIZED"
      else:
        embed.description += "IN PROCESS"
    else:
      embed.description += "ACTIVE"
    embed.description += "\n"
    await interaction.response.send_message(embed=embed)

  @app_commands.command(name="standings", description="Reports on the rankings for the league in this channel")
  async def getLeagueStandingsTask(self, interaction: discord.Interaction, week: int):
    await interaction.response.send_message(f"Retrieving standings as of week {week}")
    async with self.bot.async_session() as session:
      stmt = select(League).where(League.is_fim == True, League.active == True, League.discord_channel==str(interaction.channel_id))
      result = await session.execute(stmt)
      league = result.scalars().first()
      if league:
          year = league.year
          stmt = select(WeekStatus).where(WeekStatus.year == year, WeekStatus.week == week)
          result = await session.execute(stmt)
          week_status = result.scalars().first()
          if not week_status:
              await interaction.followup.send(f"No status found for week {week} in year {year}.")
              return
          stmt = select(FantasyTeam).where(FantasyTeam.league_id == league.league_id)
          result = await session.execute(stmt)
          fantasy_teams = result.scalars().all()
          standings = []
          for fantasy_team in fantasy_teams:
              # Get scores up to the specified week
              stmt = select(FantasyScores).where(
                  FantasyScores.fantasy_team_id == fantasy_team.fantasy_team_id,
                  FantasyScores.week <= week
              )
              result = await session.execute(stmt)
              scores = result.scalars().all()
              # Calculate total score and tiebreaker
              total_score = sum(score.rank_points for score in scores)  # Total score based on rank points
              tiebreaker = sum(score.weekly_score for score in scores)  # Tiebreaker based on weekly score

              standings.append({
                  'team_name': fantasy_team.fantasy_team_name,
                  'total_score': total_score,
                  'tiebreaker': tiebreaker,
              })

          # Sort standings first by total score, then by tiebreaker
          standings.sort(key=lambda x: (-x['total_score'], -x['tiebreaker']))

          # Prepare embed
          if week_status.scores_finalized:
              title = f"League Standings up to Week {week} for {league.league_name} ({year})"
          else:
              title = f"Unofficial League Standings up to Week {week} for {league.league_name} ({year})"

          embed = Embed(title=title, description="Here are the current standings:")

          for idx, standing in enumerate(standings):
              embed.add_field(name=f"{idx + 1}. {standing['team_name']}", 
                              value=f"Total Score (Rank Points): {standing['total_score']} | Tiebreaker (Weekly Score): {standing['tiebreaker']}", 
                              inline=False)

          # Send the standings embed to the Discord channel
          channel = self.bot.get_channel(int(league.discord_channel))
          await channel.send(embed=embed)
      else:
        await interaction.channel.send(content="No league associated with this channel!")

  @app_commands.command(name="randomize", description="Randomly pick a team from a comma-separated list")
  @app_commands.describe(teams="Comma-separated list of team names")
  async def randomize(self, interaction: discord.Interaction, teams: str):
    team_list = [team.strip() for team in teams.split(",") if team.strip()]

    if not team_list:
      await interaction.response.send_message("No valid teams were provided.")
      return

    await interaction.response.send_message(
      f"Picking a team randomly from list: {', '.join(team_list)}"
    )

    selected_team = random.choice(team_list)
    await interaction.followup.send(f"Team Selected: **{selected_team}**")

  @app_commands.command(name="joindraft", description="Join an offseason draft! Can specify a team name")
  async def joinOffseasonDraft(self, interaction: discord.Interaction, teamname: str = None):
    async with self.bot.async_session() as session:
      # Step 1: Find the league associated with the Discord channel
      stmt = select(League).where(League.discord_channel==str(interaction.channel_id))
      result = await session.execute(stmt)
      league = result.scalars().first()
      if not league:
          await interaction.response.send_message("No league associated with this channel.")
          return
      
      # Step 2: Check if the league is in the offseason
      if not league.offseason:
          await interaction.response.send_message("This league is not an offseason league.")
          return
      
      # Step 3: Check if the player is already on a FantasyTeam in this league
      stmt = select(PlayerAuthorized).join(FantasyTeam).where(
          PlayerAuthorized.player_id == str(interaction.user.id),
          FantasyTeam.league_id == league.league_id
      )
      result = await session.execute(stmt)
      player_authorization = result.scalars().first()
      
      if player_authorization:
          await interaction.response.send_message("You are already part of a fantasy team in this league.")
          return

      # Step 4: Check if the draft has already started
      stmt = select(Draft).where(Draft.league_id==league.league_id)
      result = await session.execute(stmt)
      draft_started = result.scalars().first()
      if draft_started:
          await interaction.response.send_message("The draft for this league has already started.")
          return
      
      # Step 5: Check if the player has a Player object, if not, create one
      stmt = select(Player).where(Player.user_id==str(interaction.user.id))
      result = await session.execute(stmt)
      player = result.scalars().first()
      if not player:
          new_player = Player(
              user_id=str(interaction.user.id),
              is_admin=False  # Default setting for new players
          )
          session.add(new_player)
          await session.flush()
      
      # Step 6: Create a new FantasyTeam for the user
      stmt = select(func.max(FantasyTeam.fantasy_team_id))
      result = await session.execute(stmt)
      max_team_id = result.scalar()
      new_team_id = max_team_id + 1 if max_team_id else 1
      
      # Step 7: Check if the team name is unique in the league
      if teamname:
          stmt = select(FantasyTeam).where(FantasyTeam.league_id==league.league_id, FantasyTeam.fantasy_team_name==teamname)
          result = await session.execute(stmt)
          existing_team = result.scalars().first()
          if existing_team:
              teamname = None  # Reset team name to None if it's already taken

      # Use the provided team name or the player's Discord nickname if no valid team name is provided
      new_team_name = teamname if teamname else interaction.user.display_name
      
      new_fantasy_team = FantasyTeam(
          fantasy_team_id=new_team_id,
          league_id=league.league_id,
          fantasy_team_name=new_team_name
      )
      
      session.add(new_fantasy_team)
      await session.flush()
      # Step 8: Link the player to the new FantasyTeam
      player_authorized = PlayerAuthorized(
          player_id=str(interaction.user.id),
          fantasy_team_id=new_team_id
      )
      
      session.add(player_authorized)
      
      # Step 8: Commit changes and send a success message
      await session.commit()
      await interaction.response.send_message(f"Successfully joined the offseason draft with team '{new_team_name}' and team ID {new_fantasy_team.fantasy_team_id}!")

async def setup(bot: commands.Bot) -> None:
  cog = General(bot)
  guild = await bot.fetch_guild(int(os.getenv("GUILD_ID")))
  assert guild is not None

  await bot.add_cog(
      cog,
    guilds=[guild]
  )