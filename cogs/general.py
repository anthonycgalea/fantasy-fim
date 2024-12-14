import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
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
    await interaction.response.send_message(f"Pong! Latency: {latency}ms")

  @app_commands.command(name="leagues", description="Reports on active leagues and their league ids.")
  async def getLeagues(self, interaction: discord.Interaction):
    session = await self.bot.get_session()
    leagues = session.query(League).where(League.active == True)
    embed = Embed(title="**League Listing**", description="")
    if (leagues.count() == 0):
      embed.description+="No active leagues```"
      await interaction.response.send_message(embed=embed)
      return
    for league in leagues.all():
      embed.description += f'{league.league_name:>15s}   <#{league.discord_channel}>\n'
    await interaction.response.send_message(embed=embed)
    session.close()

  @app_commands.command(name="teams", description="Reports on teams in the channel's league and their team IDs.")
  async def getTeamsInLeague(self, interaction: discord.Interaction):
    session = await self.bot.get_session()
    league = session.query(League).where(League.discord_channel==str(interaction.channel_id))
    if (league.count() == 0):
      await interaction.response.send_message("No league associated with this channel")
    leagueid = league.first().league_id
    draftOrderEmbed = Embed(title=f"**Teams in {league.first().league_name}**", description=f"```{'Team ID':7s}{'':5s}{'Team Name (id)':30s}{'Waiver':^6s}\n")
    fantasyTeams = session.query(FantasyTeam).where(FantasyTeam.league_id==leagueid).order_by(FantasyTeam.fantasy_team_id.asc()).all()
    for team in fantasyTeams:
      if team.waiver_priority==None:
        draftOrderEmbed.description+=f"{team.fantasy_team_id:>7d}{'':5s}{team.fantasy_team_name:30s}\n"  
      else:
        waiverprio = team.waiver_priority.priority
        draftOrderEmbed.description+=f"{team.fantasy_team_id:>7d}{'':5s}{team.fantasy_team_name:30s}{waiverprio:^6d}\n"  
    draftOrderEmbed.description+="```"
    await interaction.response.send_message(embed=draftOrderEmbed)
    session.close()

  @app_commands.command(name="waiverpriority", description="Reports on teams in the channel's league and their team IDs.")
  async def waiverPriorityReport(self, interaction: discord.Interaction):
    session = await self.bot.get_session()
    league = session.query(League).where(League.discord_channel==str(interaction.channel_id))
    if (league.count() == 0):
      await interaction.response.send_message("No league associated with this channel")
    leagueid = league.first().league_id
    draftOrderEmbed = Embed(title=f"**Teams in {league.first().league_name}**", description=f"```{'Team ID':7s}{'':5s}{'Team Name (id)':30s}{'Waiver':^6s}\n")
    fantasyTeams = session.query(WaiverPriority).where(WaiverPriority.league_id==leagueid).order_by(WaiverPriority.priority.asc()).all()
    if not fantasyTeams:
      await interaction.response.send_message("No waiver priorities yet!")
      session.close()
      return
    for team in fantasyTeams:
      waiverprio = team.priority
      fantasyTeam = team.fantasy_team
      draftOrderEmbed.description+=f"{fantasyTeam.fantasy_team_id:>7d}{'':5s}{fantasyTeam.fantasy_team_name:30s}{waiverprio:^6d}\n"    
    draftOrderEmbed.description+="```"
    await interaction.response.send_message(embed=draftOrderEmbed)
    session.close()

  @app_commands.command(name="leaguesite", description="Retrieve a link to your league's webpage")
  async def getLeagueWebpage(self, interaction: discord.Interaction):
    session = await self.bot.get_session()
    league = session.query(League).where(League.discord_channel==str(interaction.channel_id))
    if (league.count() == 0):
      await interaction.response.send_message("No league associated with this channel")
    leagueid = league.first().league_id
    await interaction.response.send_message(f"{websiteURL}/leagues/{leagueid}")
    session.close()

  @app_commands.command(name="draftsite", description="Retrieve a link to your draft's webpage")
  async def getDraftWebpage(self, interaction: discord.Interaction):
    session = await self.bot.get_session()
    draft = session.query(Draft).where(Draft.discord_channel==str(interaction.channel_id))
    if (draft.count() == 0):
      await interaction.response.send_message("No draft associated with this channel")
    draftid = draft.first().draft_id
    await interaction.response.send_message(f"{websiteURL}/drafts/{draftid}")
    session.close()

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
    session = await self.bot.get_session()
    league = session.query(League).filter(League.is_fim == True, League.active == True, League.discord_channel==str(interaction.channel_id)).first()
    if league:
        year = league.year
        week_status = session.query(WeekStatus).filter(WeekStatus.year == year, WeekStatus.week == week).first()
        if not week_status:
            await interaction.followup.send(f"No status found for week {week} in year {year}.")
            session.close()
            return
        fantasy_teams = session.query(FantasyTeam).filter(FantasyTeam.league_id == league.league_id).all()
        standings = []
        for fantasy_team in fantasy_teams:
            # Get scores up to the specified week
            scores = session.query(FantasyScores).filter(
                FantasyScores.fantasy_team_id == fantasy_team.fantasy_team_id,
                FantasyScores.week <= week
            ).all()
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
    session.close()

  @app_commands.command(name="joindraft", description="Join an offseason draft! Can specify a team name")
  async def joinOffseasonDraft(self, interaction: discord.Interaction, teamname: str = None):
    session = await self.bot.get_session()
    
    # Step 1: Find the league associated with the Discord channel
    league = session.query(League).filter_by(discord_channel=str(interaction.channel_id)).first()
    if not league:
        await interaction.response.send_message("No league associated with this channel.")
        return
    
    # Step 2: Check if the league is in the offseason
    if not league.offseason:
        await interaction.response.send_message("This league is not an offseason league.")
        return
    
    # Step 3: Check if the player is already on a FantasyTeam in this league
    player_authorization = session.query(PlayerAuthorized).join(FantasyTeam).filter(
        PlayerAuthorized.player_id == str(interaction.user.id),
        FantasyTeam.league_id == league.league_id
    ).first()
    
    if player_authorization:
        await interaction.response.send_message("You are already part of a fantasy team in this league.")
        return

    # Step 4: Check if the draft has already started
    draft_started = session.query(Draft).filter_by(league_id=league.league_id, discord_channel=str(interaction.channel_id)).first()
    if draft_started:
        await interaction.response.send_message("The draft for this league has already started.")
        return
    
    # Step 5: Check if the player has a Player object, if not, create one
    player = session.query(Player).filter_by(user_id=str(interaction.user.id)).first()
    if not player:
        new_player = Player(
            user_id=str(interaction.user.id),
            is_admin=False  # Default setting for new players
        )
        session.add(new_player)
        session.flush()
    
    # Step 6: Create a new FantasyTeam for the user
    max_team_id = session.query(FantasyTeam.fantasy_team_id).order_by(FantasyTeam.fantasy_team_id.desc()).first()
    new_team_id = max_team_id[0] + 1 if max_team_id else 1
    
    # Step 7: Check if the team name is unique in the league
    if teamname:
        existing_team = session.query(FantasyTeam).filter_by(league_id=league.league_id, fantasy_team_name=teamname).first()
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
    session.flush()
    # Step 8: Link the player to the new FantasyTeam
    player_authorized = PlayerAuthorized(
        player_id=str(interaction.user.id),
        fantasy_team_id=new_team_id
    )
    
    session.add(player_authorized)
    
    # Step 8: Commit changes and send a success message
    session.commit()
    await interaction.response.send_message(f"Successfully joined the offseason draft with team '{new_team_name}' and team ID {new_fantasy_team.fantasy_team_id}!")

    
    session.close()

async def setup(bot: commands.Bot) -> None:
  cog = General(bot)
  guild = await bot.fetch_guild(int(os.getenv("GUILD_ID")))
  assert guild is not None

  await bot.add_cog(
      cog,
    guilds=[guild]
  )