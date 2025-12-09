import discord
from discord import app_commands, Embed
from discord.ext import commands
from sqlalchemy import select, func, Integer
from models.draft import Draft, DraftPick, DraftOrder, StatboticsData
from models.scores import League, PlayerAuthorized, FantasyTeam, TeamOwned, Team, FRCEvent, TeamScore
from models.transactions import WaiverPriority
import logging
import os
from discord.ui import Button, View
from math import ceil

logger = logging.getLogger('discord')

class Drafting(commands.Cog):

  class DraftPaginationView(View):
    def __init__(self, bot, interaction, session, draftOrder, draft, rounds_per_page, total_pages):
        super().__init__(timeout=5000)
        self.bot = bot
        self.interaction = interaction
        self.session = session
        self.draftOrder = draftOrder
        self.draft = draft
        self.rounds_per_page = rounds_per_page
        self.total_pages = total_pages
        self.current_page = 0
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_embed(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_embed(interaction)

    async def update_embed(self, interaction: discord.Interaction):
        draftCog = Drafting(self.bot)
        new_embed = await draftCog.createDraftBoardEmbed(self.session, self.draftOrder, self.draft, self.current_page, self.total_pages, self.rounds_per_page)
        self.children[0].disabled = self.current_page <= 0
        self.children[1].disabled = self.current_page >= self.total_pages - 1       
        await interaction.message.edit(embed=new_embed, view=self)

    async def on_timeout(self):
      for child in self.children:
        child.disabled = True
      await self.interaction.message.edit(view=self)

  def __init__(self, bot):
    self.bot = bot

  async def getCurrentPickTeamId(self, draft_id):
    async with self.bot.async_session() as session:
      stmt = select(DraftPick).where(DraftPick.draft_id==draft_id, DraftPick.team_number=="-1").order_by(DraftPick.pick_number.asc())
      result = await session.execute(stmt)
      unmadepicks = result.scalars().all()
      if len(unmadepicks) == 0:
        return -1
      else:
        return unmadepicks[0].fantasy_team_id
    
  async def getCurrentPickNumber(self, draft_id):
    async with self.bot.async_session() as session:
      stmt = select(DraftPick).where(DraftPick.draft_id==draft_id, DraftPick.team_number=="-1").order_by(DraftPick.pick_number.asc())
      result = await session.execute(stmt)
      unmadepicks = result.scalars().all()
      if len(unmadepicks) == 0:
        return -1
      else:
        return unmadepicks[0].pick_number

  async def makeDraftPickTask(self, draft_id: int, team_number: str):
    async with self.bot.async_session() as session:
      stmt = select(DraftPick).where(DraftPick.draft_id==draft_id, DraftPick.team_number=="-1").order_by(DraftPick.pick_number.asc())
      result = await session.execute(stmt)
      pickToMake = result.scalars().first()
      pickToMake.team_number = team_number
      await session.commit()

  async def teamIsUnpicked(self, draft_id: int, team_number: str):
    async with self.bot.async_session() as session:
      stmt = select(DraftPick).where(DraftPick.draft_id==draft_id, DraftPick.team_number!="-1")
      result = await session.execute(stmt)
      picksMade = result.scalars().all()
      teamsPicked = set()
      teamsPicked.update([pick.team_number for pick in picksMade])
      return not team_number in teamsPicked
  
  async def teamIsInDraft(self, team_number: str, eventKey: str, year: int, isFiM: bool):
    async with self.bot.async_session() as session:
      # Query to get eligible teams based on whether it's FiM or not
      if isFiM:
          stmt = select(Team.team_number).distinct() \
              .join(TeamScore, Team.team_number == TeamScore.team_key) \
              .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key) \
              .where(
                  Team.is_fim == isFiM,
                  FRCEvent.year == year
              )
      else:
          stmt = select(TeamScore.team_key).distinct() \
              .where(TeamScore.event_key == eventKey)

      # Execute the query and get the result
      result = await session.execute(stmt)
      teams = result.scalars().all()

      # Update the set of eligible teams and check if the given team is in the list
      teamsEligible = {team for team in teams}
      return team_number in teamsEligible
  
  async def getSuggestedTeamsList(self, eventKey: str, year: int, isFiM: bool, draft_id: int, isOffseason: bool=False):
    async with self.bot.async_session() as session:
      # Subquery for picked teams
      picked_subq = select(DraftPick.team_number).where(
          DraftPick.draft_id == draft_id, 
          DraftPick.team_number != '-1'
      ).scalar_subquery()

      # Base query for Team and StatboticsData
      if isFiM:
          stmt = select(Team.team_number, StatboticsData.year_end_epa).distinct() \
              .join(TeamScore, Team.team_number == TeamScore.team_key) \
              .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key) \
              .join(StatboticsData, Team.team_number == StatboticsData.team_number) \
              .where(
                  Team.is_fim == isFiM, 
                  FRCEvent.year == year, 
                  StatboticsData.year == year - 1,
                  Team.team_number.notin_(picked_subq)
              )
      elif not isOffseason:
          stmt = select(TeamScore.team_key, StatboticsData.year_end_epa).distinct() \
              .join(StatboticsData, TeamScore.team_key == StatboticsData.team_number) \
              .where(
                  TeamScore.event_key == eventKey,
                  StatboticsData.year == year - 1,
                  TeamScore.team_key.notin_(picked_subq)
              )
      else:
          stmt = select(TeamScore.team_key, StatboticsData.year_end_epa).distinct() \
              .join(StatboticsData, TeamScore.team_key == StatboticsData.team_number) \
              .where(
                  TeamScore.event_key == eventKey,
                  StatboticsData.year == year,
                  TeamScore.team_key.notin_(picked_subq)
              )

      # Order by year_end_epa descending
      stmt = stmt.order_by(StatboticsData.year_end_epa.desc())

      # Execute the query
      result = await session.execute(stmt)
      return result.all()

  async def getAllAvailableTeamsList(self, eventKey: str, year: int, isFiM: bool, draft_id: int):
    async with self.bot.async_session() as session:
      # Subquery for picked teams
      picked_subq = select(DraftPick.team_number).where(
          DraftPick.draft_id == draft_id,
          DraftPick.team_number != '-1'
      ).scalar_subquery()

      if isFiM:
          # Query for FiM teams
          stmt = select(Team.team_number, Team.team_number.cast(Integer).label('team_number_int')).distinct() \
              .join(TeamScore, Team.team_number == TeamScore.team_key) \
              .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key) \
              .where(
                  Team.is_fim == isFiM,
                  FRCEvent.year == year,
                  Team.team_number.notin_(picked_subq)
              )
      else:
          # Query for non-FiM teams
          stmt = select(TeamScore.team_key, TeamScore.team_key.cast(Integer).label('team_number_int')).distinct() \
              .where(
                  TeamScore.event_key == eventKey,
                  TeamScore.team_key.notin_(picked_subq)
              )

      # Order by team number (cast to int for sorting)
      stmt = stmt.order_by('team_number_int')

      # Execute the query and get the result
      result = await session.execute(stmt)
      return result.all()

  async def postSuggestedTeams(self, interaction: discord.Interaction):
    draft: Draft = await self.getDraftFromChannel(interaction=interaction)
    message = await interaction.original_response()
    if (draft == None):
        await message.edit(content="No draft associated with this channel.")
        return
    league: League = await self.getLeague(draft_id=draft.draft_id)
    suggestedTeams = await self.getSuggestedTeamsList(eventKey=draft.event_key, year=league.year, isFiM=league.is_fim, draft_id=draft.draft_id, isOffseason=league.offseason)
    yearToSuggest = league.year if league.offseason else league.year - 1
    embed = Embed(title="**Suggested teams (autodraft)**", description=f"```{'Team':>10s}{f'{yearToSuggest} EPA':>12s}\n")
    teamsRemaining = len(suggestedTeams)
    teamsToReport = 10
    if (teamsRemaining < 10):
       teamsToReport = teamsRemaining
    for k in range(teamsToReport):
       embed.description+=f"{suggestedTeams[k][0]:>10s}{suggestedTeams[k][1]:>12d}\n"
    embed.description += "```"
    await message.edit(embed=embed)

  async def getDraft(self, draft_id):
    async with self.bot.async_session() as session:
      stmt = select(Draft).where(Draft.draft_id==draft_id)
      result = await session.execute(stmt)
      draft = result.scalars().first()
      return draft

  async def getDraftFromChannel(self, interaction: discord.Interaction):
    async with self.bot.async_session() as session:
      stmt = select(Draft).where(Draft.discord_channel==str(interaction.channel_id))
      result = await session.execute(stmt)
      draft = result.scalars().first()
      return draft

  async def getFantasyTeamIdFromDraftInteraction(self, interaction: discord.Interaction):
    async with self.bot.async_session() as session:
      stmt = select(FantasyTeam)\
          .join(PlayerAuthorized, FantasyTeam.fantasy_team_id == PlayerAuthorized.fantasy_team_id)\
          .join(League, FantasyTeam.league_id == League.league_id)\
          .join(Draft, League.league_id == Draft.league_id)\
          .where(PlayerAuthorized.player_id == str(interaction.user.id))\
          .where(Draft.discord_channel == str(interaction.channel_id))
      result = await session.execute(stmt)
      team = result.scalars().first()
      if team:
          return team.fantasy_team_id
      else:
          return None

  async def getLeague(self, draft_id):
    draft: Draft = await self.getDraft(draft_id)
    if draft == None:
      return None
    async with self.bot.async_session() as session:
      stmt = select(League).where(League.league_id==draft.league_id)
      result = await session.execute(stmt)
      league = result.scalars().first()
      return league
  
  async def getCurrentPickTeamId(self, draft_id):
    async with self.bot.async_session() as session:
      stmt = select(DraftPick).where(DraftPick.draft_id==draft_id, DraftPick.team_number=="-1").order_by(DraftPick.pick_number.asc())
      result = await session.execute(stmt)
      unmadepicks = result.scalars().all()
      if len(unmadepicks) == 0:
          return -1
      else:
          return unmadepicks[0].fantasy_team_id
    
  async def makeDraftPickHandler(self, interaction: discord.Interaction, team_number: str, force: bool):
    message = await interaction.original_response()
    draft: Draft = await self.getDraftFromChannel(interaction=interaction)
    if (draft == None):
        await message.edit(content=f"Invalid draft channel")
    draft_id=draft.draft_id
    currentPickId = await self.getCurrentPickTeamId(draft_id)
    league: League = await self.getLeague(draft_id)
    userFantasyTeamId = await self.getFantasyTeamIdFromDraftInteraction(interaction)
    if (currentPickId == -1):
        await message.edit(content="Draft is complete! Invalid command.")
    elif (force or currentPickId==userFantasyTeamId):
        if (await self.teamIsUnpicked(draft_id=draft_id, team_number=team_number)):
            if (await self.teamIsInDraft(team_number=team_number, eventKey=draft.event_key, year=league.year, isFiM=league.is_fim)):
                await self.makeDraftPickTask(draft_id=draft_id, team_number=team_number)
                await message.channel.send(content=f"Team {team_number} has been successfully selected!")
            else:
                await message.edit(content=f"Team {team_number} is not able to be drafted in this draft.")
        else:
            await message.edit(content=f"Team {team_number} has already been picked. Please try again.")
        #await self.postDraftBoard(interaction)
        await message.channel.send(content=f"https://fantasyfim.com/drafts/{draft_id}")
        await self.postSuggestedTeams(interaction)
        await self.notifyNextPick(interaction, draft_id=draft_id)
        if (await self.getCurrentPickTeamId(draft_id=draft_id) == '-1'):
           await interaction.channel.edit(archived=True, locked=True)
    else:
        await message.edit(content="It is not your turn to pick!")
    
  async def postDraftBoard(self, interaction: discord.Interaction):
      async with self.bot.async_session() as session:
        draft: Draft = await self.getDraftFromChannel(interaction=interaction)
        if (draft == None):
           ogresponse = await interaction.original_response()
           await ogresponse.edit(content="No draft associated with this channel.")
           return
        draft_id = draft.draft_id
        stmt = select(DraftOrder).where(DraftOrder.draft_id == draft_id).order_by(DraftOrder.draft_slot.asc())
        result = await session.execute(stmt)
        draftOrder = result.scalars().all()
        total_rounds = draft.rounds
        rounds_per_page = 4
        total_pages = ceil(total_rounds / rounds_per_page)
        currentPick = await self.getCurrentPickNumber(draft_id=draft_id)
        currentPage = int((currentPick-1)/(rounds_per_page*len(draftOrder)))
        if currentPage >= total_pages:
           currentPage=total_pages-1
        draftBoardEmbed = await self.createDraftBoardEmbed(session, draftOrder, draft, currentPage, total_pages, rounds_per_page)
        view = self.DraftPaginationView(self.bot, interaction, session, draftOrder, draft, rounds_per_page, total_pages)
        await interaction.channel.send(embed=draftBoardEmbed, view=view)

  async def postFullDraftBoard(self, interaction: discord.Interaction):
      async with self.bot.async_session() as session:
        draft: Draft = await self.getDraftFromChannel(interaction=interaction)
        if (draft == None):
           ogresponse = await interaction.original_response()
           await ogresponse.edit(content="No draft associated with this channel.")
           return
        draft_id = draft.draft_id
        stmt = select(DraftOrder).where(DraftOrder.draft_id == draft_id).order_by(DraftOrder.draft_slot.asc())
        result = await session.execute(stmt)
        draftOrder = result.scalars().all()
        total_rounds = draft.rounds
        rounds_per_page = 4
        total_pages = ceil(total_rounds / rounds_per_page)
        for k in range(total_pages):
          draftBoardEmbed = await self.createDraftBoardEmbed(session, draftOrder, draft, k, total_pages, rounds_per_page)
          view = self.DraftPaginationView(self.bot, interaction, session, draftOrder, draft, rounds_per_page, total_pages)
          await interaction.channel.send(embed=draftBoardEmbed, view=view)

  async def createDraftBoardEmbed(self, session, draftOrder, draft, current_page, total_pages, rounds_per_page):
      draft_id = draft.draft_id
      draftBoardEmbed = Embed(title=f"**Draft Board - Page {current_page+1}/{total_pages}**", description="```")
      header = f"{'Team':^15s}{'':3s}"
      for round_num in range(1 + current_page * rounds_per_page, min((current_page + 1) * rounds_per_page, draft.rounds) + 1):
          header += f"{'Pick ' + str(round_num):>7s}{'':2s}"
      draftBoardEmbed.description += header + "\n"
      for draftSlot in draftOrder:
          stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == draftSlot.fantasy_team_id)
          result = await session.execute(stmt)
          fantasyteam = result.scalars().first()
          
          stmt = select(DraftPick)\
              .where(DraftPick.fantasy_team_id == draftSlot.fantasy_team_id)\
              .where(DraftPick.pick_number > current_page*rounds_per_page*len(draftOrder))\
              .where(DraftPick.pick_number <= (current_page + 1)*rounds_per_page*len(draftOrder))\
              .where(DraftPick.draft_id == draft_id)\
              .order_by(DraftPick.pick_number.asc())
          result = await session.execute(stmt)
          draftPicks = result.scalars().all()

          abbrevName = fantasyteam.fantasy_team_name[:15]  # Limit team name to 15 characters
          draftBoardEmbed.description += f"{abbrevName:<15s}{'':3s}"
          for pick in draftPicks:
              pickToAdd = "---"
              if pick.team_number == "-1" and ((await self.getCurrentPickNumber(draft_id=draft_id)) == pick.pick_number):
                pickToAdd = "!PICK!"
              elif not pick.team_number == "-1":
                pickToAdd = pick.team_number
              draftBoardEmbed.description+=f"{pickToAdd:>7s}{'':2s}"
          draftBoardEmbed.description += "\n"
      draftBoardEmbed.description += "```"
      return draftBoardEmbed
    
  async def postAllAvailableTeams(self, interaction: discord.Interaction):
      teamcount=0
      draft: Draft = await self.getDraftFromChannel(interaction)
      league: League = await self.getLeague(draft.draft_id)
      allavailableteams = await self.getAllAvailableTeamsList(draft.event_key, league.year, league.is_fim, draft.draft_id)
      #logger.info(allavailableteams)
      embed = None
      totalteams = len(allavailableteams)
      while(teamcount < totalteams):
        if (teamcount%168 == 0):
           if not embed == None:
              embed.description+="```"
              await interaction.channel.send(embed=embed)
           embed = Embed(description="```")
        teamnumber = allavailableteams[teamcount][0]
        embed.description+=f"{teamnumber:>7s}"
        teamcount+=1
        if (teamcount%8 == 0):
           embed.description+="\n"
      if not embed == None:
         embed.description+="```"
         await interaction.channel.send(embed=embed)
     #embed = Embed(description="```")
     
  async def finishDraft(self, draft_id):
    async with self.bot.async_session() as session:
      stmt = select(DraftPick).where(DraftPick.draft_id==draft_id)
      result = await session.execute(stmt)
      allDraftPicks = result.scalars().all()
      league = await self.getLeague(draft_id)
      for team in allDraftPicks:
        teamOwnedToAdd = TeamOwned(team_key=team.team_number, fantasy_team_id=team.fantasy_team_id, league_id=league.league_id, draft_id=draft_id)
        session.add(teamOwnedToAdd)
      
      stmt = select(DraftOrder).where(DraftOrder.draft_id==draft_id).order_by(DraftOrder.draft_slot.desc())
      result = await session.execute(stmt)
      draftOrders = result.scalars().all()
      waiverPriority = 1
      for slot in draftOrders:
         prioToAdd = WaiverPriority()
         prioToAdd.priority=waiverPriority
         prioToAdd.fantasy_team_id=slot.fantasy_team_id
         fTeam: FantasyTeam = slot.fantasyTeam
         league: League = fTeam.league
         prioToAdd.league_id=league.league_id
         session.add(prioToAdd)
         waiverPriority+=1
      await session.commit()

  async def notifyNextPick(self, interaction: discord.Interaction, draft_id):
    async with self.bot.async_session() as session:
      teamIdToPick = await self.getCurrentPickTeamId(draft_id=draft_id)
      msg = ""
      if teamIdToPick == -1:
        msg += "Draft is complete!"
        await self.finishDraft(draft_id=draft_id)
        await self.postFullDraftBoard(interaction=interaction)
      else:
        stmt = select(PlayerAuthorized).where(PlayerAuthorized.fantasy_team_id==teamIdToPick)
        result = await session.execute(stmt)
        usersToNotify = result.scalars().all()
        
        stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id==teamIdToPick)
        result = await session.execute(stmt)
        teamToNotify = result.scalars().first()
        
        for user in usersToNotify:
          msg+= f"<@{user.player_id}> "
        msg += f" **({teamToNotify.fantasy_team_name})** it is your turn to pick!"
      await interaction.channel.send(msg)

  async def postTeamDraftBoard(self, interaction: discord.Interaction, team_id, draft_id):
    async with self.bot.async_session() as session:
      message = await interaction.original_response()
      
      stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id==team_id)
      result = await session.execute(stmt)
      fTeamFirst = result.scalars().first()
      
      if fTeamFirst is None:
          await message.edit(content="Invalid team id")
          return
      
      teamBoardEmbed = Embed(title=f"**{fTeamFirst.fantasy_team_name} Week-by-Week board**", description="```")
      teamBoardEmbed.description += f"{'Team':^4s}{'':1s}{'Week 1':^9s}{'':1s}{'Week 2':^9s}{'':1s}{'Week 3':^9s}{'':1s}{'Week 4':^9s}{'':1s}{'Week 5':^9}\n"
      
      stmt = select(DraftPick).where(DraftPick.fantasy_team_id==team_id, DraftPick.team_number != "-1").order_by(DraftPick.team_number.asc())
      result = await session.execute(stmt)
      teamsDrafted = result.scalars().all()
      
      for team in teamsDrafted:
          stmt = select(TeamScore).join(FRCEvent, TeamScore.event_key == FRCEvent.event_key).where(
              TeamScore.team_key == team.team_number,
              FRCEvent.year == fTeamFirst.league.year
          )
          result = await session.execute(stmt)
          teamEvents = result.scalars().all()
          
          weeks = ["---" for k in range(6)]
          for event in teamEvents:
              stmt = select(FRCEvent).where(FRCEvent.event_key==event.event_key)
              result = await session.execute(stmt)
              frcEvent = result.scalars().first()
              if int(frcEvent.week) < 7:
                  if (weeks[int(frcEvent.week)-1] == "---"):
                      weeks[int(frcEvent.week)-1] = event.event_key
                  else:
                      weeks[int(frcEvent.week)-1] = "2 Events"
          teamBoardEmbed.description+=f"{team.team_number:>4s}{'':1s}{weeks[0]:^9s}{'':1s}{weeks[1]:^9s}{'':1s}{weeks[2]:^9s}{'':1s}{weeks[3]:^9s}{'':1s}{weeks[4]:^9}\n"
      teamBoardEmbed.description += "```"
      await message.edit(embed=teamBoardEmbed, content="")

  @app_commands.command(name="pick", description="Make a draft pick!")
  async def make_pick(self, interaction: discord.Interaction, team_number: str): 
    await interaction.response.send_message(f"Attempting to pick team {team_number}.", ephemeral=True)
    await self.makeDraftPickHandler(interaction=interaction, team_number=team_number, force=False)

  """@app_commands.command(name="draftboard", description="Re-post the Draft Board")
  @commands.cooldown(rate=1, per=60)
  async def repost_draft_board(self, interaction: discord.Interaction):
    await interaction.response.send_message("Sending draft board...")
    await self.postDraftBoard(interaction)"""

  @app_commands.command(name="suggest", description="Provides a list of suggested teams based on the previous season's year-end EPA.")
  @commands.cooldown(rate=1, per=60)
  async def suggestTenTeams(self, interaction: discord.Interaction):
     await interaction.response.defer()
     await self.postSuggestedTeams(interaction=interaction)

  @app_commands.command(name="available", description="Posts all available teams in current draft.")
  @commands.cooldown(rate=1, per=60)
  async def getAllAvailable(self, interaction: discord.Interaction):
     await interaction.response.send_message("**Fetching all available teams**")
     await self.postAllAvailableTeams(interaction)

  @app_commands.command(name="mydraft", description="View your draft board and when their FRC teams compete")
  async def viewMyTeam(self, interaction: discord.Interaction):
    await interaction.response.send_message("Collecting draft board", ephemeral=True)
    draft: Draft = await self.getDraftFromChannel(interaction=interaction)
    if (draft == None):
        await message.edit(content=f"Invalid draft channel")
    draft_id=draft.draft_id
    teamId = await self.getFantasyTeamIdFromDraftInteraction(interaction)
    if not teamId == None:
        await self.postTeamDraftBoard(interaction, teamId, draft_id)
    else:
        message = await interaction.original_response()
        await message.edit(content="You are not part of any team in this draft!")

async def setup(bot: commands.Bot) -> None:
  cog = Drafting(bot)
  guild = await bot.fetch_guild(int(os.getenv("GUILD_ID")))
  assert guild is not None

  await bot.add_cog(
      cog,
    guilds=[guild]
  )