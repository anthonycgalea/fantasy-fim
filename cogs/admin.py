import discord, sqlalchemy
from discord import app_commands
from discord import Embed
from discord.ext import commands
from sqlalchemy import select, delete, or_
from sqlalchemy.sql import text
import requests
import logging
import traceback
import os
import asyncio
import random, datetime
import cogs.drafting as drafting
import cogs.manageteam as manageteam
from models.users import Player
from models.scores import Team, League, FRCEvent, TeamScore, FantasyTeam, PlayerAuthorized, WeekStatus, TeamStarted, TeamOwned, FantasyScores
from models.draft import Draft, DraftOrder, DraftPick, StatboticsData
from models.transactions import WaiverPriority, WaiverClaim, TeamOnWaivers, TradeProposal, TradeTeams


logger = logging.getLogger('discord')
TBA_API_ENDPOINT = "https://www.thebluealliance.com/api/v3/"
TBA_AUTH_KEY = os.getenv("TBA_API_KEY")
FORUM_CHANNEL_ID = os.getenv("DRAFT_FORUM_ID")
STATBOTICS_ENDPOINT = "https://api.statbotics.io/v3/team_years"


class Admin(commands.Cog):
  def __init__(self, bot):
    self.bot = bot
    

  async def put_teams_on_waivers(self, interaction: discord.Interaction):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    currentWeek = (
        session.query(WeekStatus)
        .filter(WeekStatus.active == True)
        .order_by(WeekStatus.year.asc(), WeekStatus.week.asc())
        .first()
    )

    if not currentWeek:
        await message.channel.send(content="No active weeks found. No teams will be put on waivers.")
        return

    leagues = session.query(League).filter(
        League.is_fim == True, League.active == True
    ).all()

    if not leagues:
        await message.channel.send(content="No active FIM leagues found. No teams will be put on waivers.")
        return

    for league in leagues:
        competing_teams = (
            session.query(TeamScore.team_key)
            .join(Team, Team.team_number == TeamScore.team_key)
            .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key)
            .filter(Team.is_fim == True, FRCEvent.week == currentWeek.week)
            .filter(FRCEvent.year==currentWeek.year)
            .all()
        )

        teams_to_put_on_waivers = []
        for team_number in competing_teams:
            is_owned = session.query(TeamOwned).filter(TeamOwned.league_id==league.league_id, TeamOwned.team_key == team_number[0]).first() is not None
            is_on_waivers = session.query(TeamOnWaivers).filter(TeamOnWaivers.team_number == team_number[0], TeamOnWaivers.league_id==league.league_id).first() is not None
            
            if not is_owned and not is_on_waivers:
                teams_to_put_on_waivers.append(team_number[0])

        if teams_to_put_on_waivers:
            team_on_waivers_objects = [
                TeamOnWaivers(league_id=league.league_id, team_number=team_number) 
                for team_number in teams_to_put_on_waivers
            ]
            for wTeam in team_on_waivers_objects:
              if (session.query(TeamOnWaivers).filter(TeamOnWaivers.league_id==league.league_id, TeamOnWaivers.team_number==wTeam.team_number).count() == 0):
                session.add(wTeam)
                session.flush()
            #session.bulk_save_objects(team_on_waivers_objects)
            session.commit()
            await message.channel.send(embed=Embed(title=f"Placed teams on waivers for league {league.league_name}",description=f"{teams_to_put_on_waivers}"))
        else:
            await message.channel.send(content=f"No teams meet the criteria to be put on waivers for league {league.league_name}.")

  async def updateStatboticsTask(self, interaction, year):
    embed = Embed(title="Update Team List", description=f"Updating year end team data from Statbotics for {year}")
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    if (datetime.date.today().year < year or year < 2005):
      embed.description = "Invalid year. Please try again"
      await message.edit(embed=embed)
      return
    session = await self.bot.get_session()
    i = 0
    deleted_count = (
        session.query(StatboticsData)
        .filter(StatboticsData.year == year)
        .delete()
    )
    session.commit()
    logger.info(f"Deleted {deleted_count} Statbotics records for {year}")

    offset = 0
    while True:
      try:
        requestURL = f"{STATBOTICS_ENDPOINT}?year={year}&limit=500&offset={offset}"
        response = requests.get(requestURL)
        if response.status_code != 200:
          break
        data = response.json()
        if not data:
          break
        for team_year in data:
          team_number = str(team_year.get("team"))
          unitless_epa = team_year.get("unitless_epa_end")
          if unitless_epa is None:
            epa_end = team_year.get("epa_end")
            if isinstance(epa_end, dict):
              unitless_epa = epa_end.get("unitless")
            elif isinstance(epa_end, (int, float)):
              unitless_epa = epa_end
          if unitless_epa is None:
            epa = team_year.get("epa")
            if isinstance(epa, dict):
              unitless_epa = epa.get("unitless")
          if unitless_epa is None:
            unitless_epa = 0
          logger.info(f"Team number: {team_number} Year: {year} year_end_epa: {int(unitless_epa)}")
          session.add(StatboticsData(team_number=team_number, year=year, year_end_epa=int(unitless_epa)))
        session.commit()
        i += len(data)
        offset += 500
        if i % 50 == 0:
          embed.description=f"Processed {i} Teams"
          await message.edit(embed=embed)
      except Exception:
        logger.error(traceback.format_exc())
        break
    session.close()

  async def updateTeamsTask(self, interaction, startPage):
    embed = Embed(title="Update Team List", description="Updating team list from The Blue Alliance")
    await interaction.response.send_message(embed=embed)
    reqheaders = {"X-TBA-Auth-Key": TBA_AUTH_KEY}
    session = await self.bot.get_session()
    teams = session.query(Team)
    i = startPage
    while(True):
      try:
        requestURL = TBA_API_ENDPOINT + "teams/" + str(i) 
        response = requests.get(requestURL, headers=reqheaders).json()
        if (len(response) == 0):
          break
        for team in response:
          teamNumber = str(team["team_number"])
          teamName = str(team["nickname"])
          rookieYear = team["rookie_year"]
          if teams.filter(Team.team_number == teamNumber).count() == 0:
            logger.info(f"Inserting team number {teamNumber}")
            isFiM = False
            if (team["state_prov"] == "Michigan"):
              isFiM = True
            teamToAdd = Team(team_number=teamNumber, name=teamName, is_fim=isFiM)
            session.add(teamToAdd)
          elif not (teams.filter(Team.team_number == teamNumber).first().name == teamName\
                    and teams.filter(Team.team_number==teamNumber).first().rookie_year==rookieYear): 
            logger.info(f"Updating team number {teamNumber}, team name {teamName}, rookie year {rookieYear}")
            teams.filter(Team.team_number == teamNumber).first().name = teamName
            teams.filter(Team.team_number == teamNumber).first().rookie_year = rookieYear
        i += 1
        embed.description = f"Updating team list: Processed {i*500} teams (Page {i})"
        await interaction.channel.send(embed = embed)
        session.commit()
      except Exception:
        embed.description = "Error updating team list from The Blue Alliance"
        await interaction.channel.send(embed = embed)
        logger.error(traceback.format_exc())
        return
    embed.description = "Updated team list from The Blue Alliance"
    await interaction.edit_original_response(embed = embed)
    session.close()

  async def updateEventsTask(self, interaction, year):
    embed = Embed(title="Update Event List", description=f"Updating event list for {year} from The Blue Alliance")
    newEventsEmbed = Embed(title="New Events", description="No new events")
    eventsLog = await self.bot.log_message("New Events", "No new events")
    await interaction.response.send_message(embed=embed)
    reqheaders = {"X-TBA-Auth-Key": TBA_AUTH_KEY}
    session = await self.bot.get_session()
    yearevents = session.query(FRCEvent).filter(FRCEvent.year == year)
    try:
      requestURL = TBA_API_ENDPOINT + "events/" + str(year)
      response = requests.get(requestURL, headers=reqheaders).json()
      totalEvents = len(response)
      i = 0
      for event in response:
        if (not event["event_type"] in [99, 100]):
          eventKey = str(event["key"])
          eventName = str(event["name"])
          if event["event_type"] in [3, 4]:
            week = 8
          else:
            week = str(event["week"]+1)
          filteredEvents = yearevents.filter(FRCEvent.event_key == eventKey)
          if filteredEvents.count() == 0:
            logger.info(f"Inserting event {eventKey}: {eventName}")
            newEventsEmbed.description = f"Found new event {eventKey}: {eventName}"
            eventsLog.edit(embed=newEventsEmbed)
            isFiM = False
            if (not event["district"] == None and event["district"]["abbreviation"] == "fim"):
              isFiM = True
            eventToAdd = FRCEvent(event_key=eventKey, event_name=eventName, year=year, week=week, is_fim=isFiM)
            session.add(eventToAdd)
          elif not (filteredEvents.first().event_name == eventName\
                    and str(filteredEvents.first().year) == str(year)\
                    and str(filteredEvents.first().week) == str(week)): 
            logger.info(f"Updating event {eventKey}")
            filteredEvents.first().event_name = eventName
            filteredEvents.first().year = year
            filteredEvents.first().week = week
        i+=1
        if (i%25 == 0):
          embed.description = f"Updating event list: Processed {i}/{totalEvents} events"
          await interaction.edit_original_response(embed = embed)
      session.commit()
    except Exception:
      logger.error(traceback.format_exc())
      embed.description = "Error updating event list from The Blue Alliance"
      await interaction.edit_original_response(embed = embed)
      return
    embed.description = "Updated event list from The Blue Alliance"
    await interaction.edit_original_response(embed = embed)
    session.close()

  async def importSingleEventTask(self, interaction, eventKey):
    embed = Embed(title=f"Import Event {eventKey}", description=f"Importing event info for key {eventKey} from The Blue Alliance")
    await interaction.response.send_message(embed = embed)
    reqheaders = {"X-TBA-Auth-Key": TBA_AUTH_KEY}
    session = await self.bot.get_session()
    eventResult = session.query(FRCEvent).filter(FRCEvent.event_key == eventKey)
    try:
      requestURL = TBA_API_ENDPOINT + "event/" + str(eventKey)
      response = requests.get(requestURL, headers=reqheaders).json()
      if (not "key" in response.keys()):
        await interaction.response.send_message(f"Event {eventKey} does not exist on The Blue Alliance")
        return
      eventKey = str(response["key"])
      eventName = str(response["name"])
      week=99
      year=eventKey[:4]
      if eventResult.count() == 0:
        logger.info(f"Inserting event {eventKey}: {eventName}")
        isFiM = False
        eventToAdd = FRCEvent(event_key=eventKey, event_name=eventName, year=year, week=week, is_fim=isFiM)
        session.add(eventToAdd)
      elif not (eventResult.first().event_name == eventName\
                and str(eventResult.first().year) == str(year)\
                and str(eventResult.first().week) == str(week)): 
        logger.info(f"Updating event {eventKey}")
        eventResult.first().event_name = eventName
        eventResult.first().year = year
        eventResult.first().week = week
      embed.description = f"Retrieving {eventKey} teams"
      await interaction.edit_original_response(embed=embed)
      requestURL += "/teams/simple"
      response = requests.get(requestURL, headers=reqheaders).json()
      teamscores = session.query(TeamScore).filter(TeamScore.event_key==eventKey)
      for team in response:
        teamNumber = str(team["team_number"])
        if teamscores.filter(TeamScore.team_key == teamNumber).count() == 0:
          logger.info(f"Team {teamNumber} registered for {eventKey}")
          teamScoreToAdd = TeamScore(team_key=teamNumber, event_key=eventKey)
          session.add(teamScoreToAdd)
      session.commit()
      embed.description = f"Retrieved all {eventKey} information"
      await interaction.edit_original_response(embed=embed)
      session.close()
    except Exception:
      embed.description = f"Error retrieving offseason event {eventKey} from The Blue Alliance"
      await interaction.edit_original_response(embed=embed)
      logger.error(traceback.format_exc())
      session.close()
      return

  async def createOffseasonEventTask(self, interaction: discord.Interaction, eventKey, eventName, year):
    message = await interaction.original_response()
    with await self.bot.get_session() as session:
      eventResult = session.query(FRCEvent).filter(FRCEvent.event_key == eventKey)
      if eventResult.count() > 0:
        await message.channel.send(content=f"{eventKey} already in database")
      else:
        newEvent = FRCEvent(event_key=eventKey, event_name=eventName, year=year, week=99, is_fim=False)
        session.add(newEvent)
        session.commit()
        await message.channel.send(content=f"{eventKey} created!")

  async def importFullDistrctTask(self, year, district: str = "fim"):
    embed = Embed(title=f"Importing {district} District", description=f"Importing event info for all {district} districts from The Blue Alliance")
    originalMessage = await self.bot.log_message(embed = embed)
    newEventsEmbed = Embed(title="New Events", description="No new events")
    eventsLog = await self.bot.log_message("New Events", "No new events")
    TBA_AUTH_KEY = os.getenv("TBA_API_KEY")
    reqheaders = {"X-TBA-Auth-Key": TBA_AUTH_KEY}
    session = await self.bot.get_session()
    try:
      requestURL = TBA_API_ENDPOINT + "district/" + str(year) + str(district) + "/events"
      logger.info(requestURL)
      response = requests.get(requestURL, headers=reqheaders).json()
      logger.info(response)
      if (not isinstance(response, list)):
        embed.description = f"District {district} does not exist on The Blue Alliance"
        await originalMessage.edit(embed=embed)
        return
      numberOfEvents = len(response)
      i = 1
      first = True
      for event in response:
        week=int(event["week"])+1
        if event["event_type"] in [1,2,5]:
          eventKey = str(event["key"])
          eventName = str(event["name"])
          year=eventKey[:4]
          eventResult = session.query(FRCEvent).filter(FRCEvent.event_key == eventKey)
          if eventResult.count() == 0:
            if first:
              first=False
              newEventsEmbed.description=""
            logger.info(f"Inserting event {eventKey}: {eventName}")
            newEventsEmbed.description += f"Found new event {eventKey}: {eventName}\n"
            await eventsLog.edit(embed=newEventsEmbed)
            isFiM = district == "fim"
            eventToAdd = FRCEvent(event_key=eventKey, event_name=eventName, year=year, week=week, is_fim=isFiM)
            session.add(eventToAdd)
          elif not (eventResult.first().event_name == eventName\
                    and str(eventResult.first().year) == str(year)\
                    and str(eventResult.first().week) == str(week)): 
            logger.info(f"Updating event {eventKey}")
            eventResult.first().event_name = eventName
            eventResult.first().year = year
            eventResult.first().week = week
          embed.description = f"Retrieving {eventKey} teams (Event {i}/{numberOfEvents})"
          await originalMessage.edit(embed=embed)
          requestURL = TBA_API_ENDPOINT + "event/" + str(eventKey) + "/teams/simple"
          response = requests.get(requestURL, headers=reqheaders).json()
          teamscores = session.query(TeamScore).filter(TeamScore.event_key==eventKey)
          teamlist = set()
          teamRegistrationChangeEmbed = None
          teamRegistrationChangeMsg = None
          embedSentYet=False
          for team in response:
            teamNumber = str(team["team_number"])
            teamlist.add(teamNumber)
            if teamscores.filter(TeamScore.team_key == teamNumber).count() == 0:
              if not embedSentYet:
                teamRegistrationChangeMsg = await self.bot.log_message(f"{eventKey} registration changes", f"Team {teamNumber} registered for {eventKey}")
                teamRegistrationChangeEmbed = Embed(title=f"{eventKey} registration changes", description=f"Team {teamNumber} registered for {eventKey}")
                embedSentYet = True
              else:
                teamRegistrationChangeEmbed.description+=f"\nTeam {teamNumber} registered for {eventKey}"
                await teamRegistrationChangeMsg.edit(embed=teamRegistrationChangeEmbed)
              logger.info(f"Team {teamNumber} registered for {eventKey}")
              teamScoreToAdd = TeamScore(team_key=teamNumber, event_key=eventKey)
              session.add(teamScoreToAdd)
          for team in teamscores.all():
            if not str(team.team_key) in teamlist:
              logger.info(f"Team {team.team_key} un-registered from {team.event_key}")
              session.delete(team)
              if not embedSentYet:
                teamRegistrationChangeMsg = await self.bot.log_message(f"{eventKey} registration changes", f"Team {team.team_key} un-registered from {team.event_key}")
                teamRegistrationChangeEmbed = Embed(title=f"{eventKey} registration changes", description=f"Team {team.team_key} un-registered from {team.event_key}")
                embedSentYet = True
              else:
                teamRegistrationChangeEmbed.description+=f"\nTeam {team.team_key} un-registered from {team.event_key}"
                await teamRegistrationChangeMsg.edit(embed=teamRegistrationChangeEmbed)
        i+=1
      session.commit()
      embed.description = f"Retrieved all {district} information"
      await originalMessage.edit(embed=embed)
      session.close()
    except Exception:
      embed.description = f"Error retrieving offseason event {eventKey} from The Blue Alliance"
      await originalMessage.edit(embed=embed)
      logger.error(traceback.format_exc())
      session.close()
      return

  async def scoreSingularEventTask(self, interaction: discord.Interaction, eventKey: str):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    eventToScore: FRCEvent = session.query(FRCEvent).filter(FRCEvent.event_key==eventKey).first()
    embed = Embed(title=f"Scoring {eventKey}", description=f"Importing event info for {eventKey} from The Blue Alliance")
    await message.edit(content="", embed = embed)
    embed.description = ""
    if eventToScore and eventToScore.is_fim:
      logger.info(f"Event to score: {eventToScore.event_name}")
      requestURL = TBA_API_ENDPOINT + "event/" + eventToScore.event_key + "/district_points"
      reqheaders = {"X-TBA-Auth-Key": TBA_AUTH_KEY}
      eventresponse = requests.get(requestURL, headers=reqheaders).json()
      currentScores = session.query(TeamScore).filter(TeamScore.event_key==eventToScore.event_key)
      for team in eventresponse["points"]:
        teamscore = None
        if currentScores.filter(TeamScore.team_key==team[3:]).count() == 0:
          teamscore = TeamScore(team_key=team[3:], event_key=eventToScore.event_key)
          session.add(teamscore)
        else:
          teamscore = currentScores.filter(TeamScore.team_key==team[3:]).first()
        teamscore.qual_points=eventresponse["points"]["frc"+teamscore.team_key]["qual_points"]
        teamscore.alliance_points=eventresponse["points"]["frc"+teamscore.team_key]["alliance_points"]
        teamscore.elim_points=eventresponse["points"]["frc"+teamscore.team_key]["elim_points"]
        teamscore.award_points=eventresponse["points"]["frc"+teamscore.team_key]["award_points"]
        team = session.query(Team).filter(Team.team_number==teamscore.team_key).first()
        if (not eventToScore.week == 6):
          if (int(team.rookie_year) == int(eventToScore.year)):
            teamscore.rookie_points = 5
          elif (int(team.rookie_year) == int(eventToScore.year)-1):
            teamscore.rookie_points = 2
      embed.description += f"Successfully scored **{eventToScore.event_name}**\n"
      await message.edit(embed=embed)
      session.commit() 
    elif eventToScore:
      await self.scoreOffseasonEventTask(interaction, eventKey)
    else:
      await message.edit(content=f"Could not find event {eventKey}")

  async def scoreOffseasonEventTask(self, interaction: discord.Interaction, eventKey: str):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    eventToScore: FRCEvent = session.query(FRCEvent).filter(FRCEvent.event_key==eventKey).first()
    embed = Embed(title=f"Scoring {eventKey}", description=f"Importing event info for {eventKey} from The Blue Alliance")
    await message.edit(content="", embed = embed)
    embed.description = ""
    if eventToScore:
      logger.info(f"Event to score: {eventToScore.event_name}")
      requestURL = TBA_API_ENDPOINT + "event/" + eventToScore.event_key + "/teams/statuses"
      reqheaders = {"X-TBA-Auth-Key": TBA_AUTH_KEY}
      statusesResponse = requests.get(requestURL, headers=reqheaders).json()
      for teamKey in statusesResponse.keys():
        teamJson = statusesResponse[teamKey]
        teamNum = teamKey[3:]
        teamScoreToMod: TeamScore = session.query(TeamScore).filter(TeamScore.event_key==eventKey, TeamScore.team_key==teamNum).first()
        if not teamScoreToMod:
          teamScoreToMod = TeamScore(team_key=teamNum, event_key=eventKey)
          session.add(teamScoreToMod)
          session.flush()
        notCompeted = teamJson["qual"] == None
        if notCompeted:
          continue
        #TODO: fix ranking data
        rankData = teamJson["qual"]["ranking"]
        numTeams = teamJson["qual"]["num_teams"]
        teamScoreToMod.update_qualification_points(int(rankData["rank"]), int(numTeams)) #qual points
        allianceData = teamJson["alliance"]
        if not allianceData:
          teamScoreToMod.update_alliance_points()
        else:
          pick = None
          if allianceData["pick"] in [0, 1]:
            pick = int(allianceData["number"])
          elif allianceData["pick"] == 2:
            pick = 17-int(allianceData["number"])
          teamScoreToMod.update_alliance_points(pick)
        elimsData = teamJson["playoff"]
        if not elimsData:
          teamScoreToMod.update_elim_points()
        else:
          if elimsData["level"] == "f" and elimsData["status"] == "won":
            teamScoreToMod.update_elim_points(won_finals=True)
          elif elimsData["level"] == "f":
            teamScoreToMod.update_elim_points(lost_finals=True)
          elif elimsData["double_elim_round"] == "Round 5":
            teamScoreToMod.update_elim_points(lost_match_13=True)
          elif elimsData["double_elim_round"] == "Round 4":
            teamScoreToMod.update_elim_points(lost_match_12=True)
          else:
            teamScoreToMod.update_elim_points()
        session.flush()
      embed.description += f"Successfully scored **{eventToScore.event_name}**\n"
      await message.edit(embed=embed)
      session.commit() 
    else:
      await message.edit(content=f"Could not find event {eventKey}")

  async def scoreWeekTask(self, interaction: discord.Interaction, year, week):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    weekStatus = session.query(WeekStatus).filter(WeekStatus.week==week).filter(WeekStatus.year==year)
    if (weekStatus.count() == 0):
      await message.edit(content="No week to score.")
      return
    elif (weekStatus.first().scores_finalized == True):
      await message.edit(content="Scores are already finalized.")
      return
    eventsToScore = session.query(FRCEvent).filter(FRCEvent.year==year).filter(FRCEvent.is_fim==True).filter(FRCEvent.week==week)
    embed = Embed(title=f"Scoring week {week} for {year}", description=f"Importing event info for all {year} week {week} districts from The Blue Alliance")
    await message.edit(content="", embed = embed)
    embed.description = ""
    logger.info(f"Events to score: {eventsToScore.count()}")
    for event in eventsToScore.all():
      logger.info(f"Event to score: {event.event_name}")
      requestURL = TBA_API_ENDPOINT + "event/" + event.event_key + "/district_points"
      reqheaders = {"X-TBA-Auth-Key": TBA_AUTH_KEY}
      eventresponse = requests.get(requestURL, headers=reqheaders).json()
      currentScores = session.query(TeamScore).filter(TeamScore.event_key==event.event_key)
      for team in eventresponse["points"]:
        teamscore = None
        if currentScores.filter(TeamScore.team_key==team[3:]).count() == 0:
          teamscore = TeamScore(team_key=team[3:], event_key=event.event_key)
          session.add(teamscore)
        else:
          teamscore = currentScores.filter(TeamScore.team_key==team[3:]).first()
        teamscore.qual_points=eventresponse["points"]["frc"+teamscore.team_key]["qual_points"]
        teamscore.alliance_points=eventresponse["points"]["frc"+teamscore.team_key]["alliance_points"]
        teamscore.elim_points=eventresponse["points"]["frc"+teamscore.team_key]["elim_points"]
        teamscore.award_points=eventresponse["points"]["frc"+teamscore.team_key]["award_points"]
        if (teamscore.award_points == 10):
          teamscore.award_points += 10
        elif(teamscore.award_points == 30):
          teamscore.award_points += 30
        team = session.query(Team).filter(Team.team_number==teamscore.team_key).first()
        if (not week == 6):
          if (int(team.rookie_year) == int(year)):
            teamscore.rookie_points = 5
          elif (int(team.rookie_year) == int(year)-1):
            teamscore.rookie_points = 2
      embed.description += f"Successfully scored **{event.event_name}**\n"
      await message.edit(embed=embed)
      session.commit() 
    embed.description += f"**All events scored for week {week}**"
    await message.edit(embed=embed)
    session.close()

  async def scoreAllLeaguesTask(self, interaction: discord.Interaction, year, week, states=False):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    allLeagues = session.query(League).filter(League.is_fim==True).filter(League.year==year).all()
    weekStatus = session.query(WeekStatus).filter(WeekStatus.week==week).filter(WeekStatus.year==year)
    if (weekStatus.count() == 0):
      await message.edit(content="No week to score.")
      session.close()
      return
    elif (weekStatus.first().scores_finalized == True):
      await message.edit(content="Scores are already finalized.")
      session.close()
      return
    for league in allLeagues:
        fantasyTeams = session.query(FantasyTeam).filter(FantasyTeam.league_id==league.league_id).all()

        # Calculate scores for each fantasy team
        for fantasyTeam in fantasyTeams:
            teamscore = session.query(FantasyScores).filter(
                FantasyScores.fantasy_team_id == fantasyTeam.fantasy_team_id
            ).filter(FantasyScores.week == week).first()
            if not teamscore:
                teamscore = FantasyScores(
                    league_id=league.league_id,
                    fantasy_team_id=fantasyTeam.fantasy_team_id,
                    event_key=f"fim{league.year}",
                    week=week,
                    rank_points=0,
                    weekly_score=0
                )
                session.add(teamscore)
                session.flush()

            teamstarts = session.query(TeamStarted).filter(
                TeamStarted.fantasy_team_id == fantasyTeam.fantasy_team_id
            ).filter(TeamStarted.week == week).all()

            # Calculate weekly score based on team starts
            weekly_score = 0

            for start in teamstarts:
                if states:
                    # States Week: Count all points across all events the team competes in,
                    # including the Michigan Championship event
                    team_scores = session.query(TeamScore).join(FRCEvent).filter(
                        TeamScore.team_key == start.team_number
                    ).filter(FRCEvent.year == year).filter(
                        or_(FRCEvent.week == week, FRCEvent.event_key == f"{year}micmp")
                    ).all()
                else:
                    # Pre-States: Only include points for the specific event in TeamStarted
                    team_scores = session.query(TeamScore).filter(
                        TeamScore.team_key == start.team_number
                    ).filter(TeamScore.event_key == start.event_key).all()

                # Sum up the scores for this team
                for score in team_scores:
                    weekly_score += score.score_team()

            teamscore.weekly_score = weekly_score
            session.flush()

        # Retrieve all scores for the league in the current week
        scoresToRank = session.query(FantasyScores).filter(
            FantasyScores.league_id == league.league_id,
            FantasyScores.week == week
        ).order_by(FantasyScores.weekly_score.desc()).all()

        # Special case: If this is States, lock the top 3 teams from previous weeks
        if states:
            # Calculate cumulative scores up to the current week for the States
            cumulativeScores = {}
            for fantasyTeam in fantasyTeams:
                total_score = session.query(FantasyScores).filter(
                    FantasyScores.fantasy_team_id == fantasyTeam.fantasy_team_id,
                    FantasyScores.week < week  # Exclude the current week
                ).with_entities(FantasyScores.rank_points).all()

                cumulativeScores[fantasyTeam.fantasy_team_id] = sum(score[0] for score in total_score)

            # Get the top 3 teams based on cumulative scores
            lockedTop3 = sorted(cumulativeScores.items(), key=lambda x: x[1], reverse=True)[:3]
            lockedTop3TeamIds = [team_id for team_id, _ in lockedTop3]

            # Ensure the top 3 are locked in their positions for this week
            lockedTeamsRanked = session.query(FantasyScores).filter(
                FantasyScores.fantasy_team_id.in_(lockedTop3TeamIds),
                FantasyScores.week == week
            ).all()

            # Assign rank points manually for locked top 3
            for i, teamscore in enumerate(lockedTeamsRanked):
                teamscore.rank_points = 100 - i*25  # Assign rank points from the top

            # Remove the top 3 from the scoresToRank, leaving the rest to be ranked normally
            scoresToRank = [score for score in scoresToRank if score.fantasy_team_id not in lockedTop3TeamIds]

            # Normal ranking for the rest of the teams
            for i, teamscore in enumerate(scoresToRank):
                rank = i + len(lockedTop3TeamIds) + 1  # Start rank after the locked top 3
                # Check for ties
                if i > 0 and teamscore.weekly_score == scoresToRank[i - 1].weekly_score:
                    teamscore.rank_points = scoresToRank[i - 1].rank_points  # Same rank as the previous team
                else:
                    teamscore.rank_points = len(fantasyTeams) - rank
        else:
          # Normal ranking for non-states weeks
          for i, teamscore in enumerate(scoresToRank):
              rank = i + 1  # Rank starting from 1
              # Check for ties
              if i > 0 and teamscore.weekly_score == scoresToRank[i - 1].weekly_score:
                  teamscore.rank_points = scoresToRank[i - 1].rank_points  # Same rank as the previous team
              else:
                  teamscore.rank_points = len(fantasyTeams) - rank

          session.flush()

        session.commit()

    session.close()
    await message.edit(content=f"Updated all scores for {year} week {week}, {'with states rules applied' if states else ''}")

  async def scoreSingleDraft(self, interaction: discord.Interaction, draft_id: int):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    draft: Draft = session.query(Draft).filter(Draft.draft_id==draft_id).first()
    league: League = session.query(League).filter(League.league_id==draft.league_id).first()
    frcEvent: FRCEvent = session.query(FRCEvent).filter(FRCEvent.event_key==draft.event_key).first()
    if league:
        fantasyTeams = session.query(FantasyTeam).filter(FantasyTeam.league_id==league.league_id).all()
        # Calculate scores for each fantasy team
        for fantasyTeam in fantasyTeams:
            teamscore = session.query(FantasyScores).filter(
                FantasyScores.fantasy_team_id == fantasyTeam.fantasy_team_id
            ).filter(FantasyScores.week == frcEvent.week).first()
            if not teamscore:
                teamscore = FantasyScores(
                    league_id=league.league_id,
                    fantasy_team_id=fantasyTeam.fantasy_team_id,
                    event_key=frcEvent.event_key,
                    week=frcEvent.week,
                    rank_points=0,
                    weekly_score=0
                )
                session.add(teamscore)
                session.flush()
            draftPicks = session.query(DraftPick).filter(
                DraftPick.fantasy_team_id == fantasyTeam.fantasy_team_id,
                DraftPick.draft_id == draft.draft_id
            ).all()
            # Calculate weekly score based on team starts
            weekly_score = 0
            for pick in draftPicks:
                if frcEvent.week in [6, 7, 8, 9]: #future proofing for future champs week shifting
                    # States+Champs Weeks: Count all points across all events the team competes in
                    team_scores = session.query(TeamScore).join(League).filter(
                        TeamScore.team_key == pick.team_number
                    ).filter(League.year == league.year).all()
                else:
                    # Non-States: Only include points for the specific event
                    team_scores = session.query(TeamScore).filter(
                        TeamScore.team_key == pick.team_number
                    ).filter(TeamScore.event_key == draft.event_key).all()
                # Sum up the scores for this team
                for score in team_scores:
                    weekly_score += score.score_team()
            teamscore.weekly_score = weekly_score
            session.flush()
        # Retrieve all scores for the league in the current week
        scoresToRank = session.query(FantasyScores).filter(
            FantasyScores.league_id == league.league_id
        ).order_by(FantasyScores.weekly_score.desc()).all()
        for i, teamscore in enumerate(scoresToRank):
            rank = i + 1  # Rank starting from 1
            # Check for ties
            if i > 0 and teamscore.weekly_score == scoresToRank[i - 1].weekly_score:
                teamscore.rank_points = scoresToRank[i - 1].rank_points  # Same rank as the previous team
            else:
                teamscore.rank_points = len(fantasyTeams) - rank
        session.flush()

    session.commit()
    await message.edit(content=f"Updated all scores for {frcEvent.event_key}")
    session.close()

  async def notifyWeeklyScoresTask(self, interaction: discord.Interaction, year, week):
    session = await self.bot.get_session()
    week_status = session.query(WeekStatus).filter(WeekStatus.year == year).filter(WeekStatus.week == week).first()
    if not week_status:
        await interaction.followup.send(f"No status found for year {year}, week {week}.")
        session.close()
        return
    leagues = session.query(League).filter(League.is_fim == True).filter(League.active == True).all()
    for league in leagues:
        teams = session.query(FantasyScores).filter(FantasyScores.league_id == league.league_id)\
                    .filter(FantasyScores.week == week)\
                    .order_by(FantasyScores.rank_points.desc()).all()
        if not teams:
            continue
        if week_status.scores_finalized:
            title = f"Week {week} Final Scores for {league.league_name}"
        else:
            title = f"Week {week} Unofficial Scores for {league.league_name}"
        embed = Embed(title=title, description=f"Here are the {'official' if week_status.scores_finalized else 'unofficial'} scores for Week {week}")
        for idx, team_score in enumerate(teams):
            fantasy_team = team_score.fantasyTeam
            embed.add_field(name=f"{idx + 1}. {fantasy_team.fantasy_team_name}", 
                            value=f"Score: {team_score.weekly_score} points", inline=False)
        if week_status.scores_finalized:
            winning_team = teams[0].fantasyTeam
            winning_score = teams[0].weekly_score
            playersToNotify = session.query(PlayerAuthorized).filter(PlayerAuthorized.fantasy_team_id==winning_team.fantasy_team_id).all()
            congrats_message = f"**Congratulations to {winning_team.fantasy_team_name} for winning this week with {winning_score} points!**\n"
            for player in playersToNotify:
              congrats_message += f"<@{player.player_id}> "

        else:
            congrats_message = f"Unofficial scores for Week {week}. Check back later for final results!"
        channel = self.bot.get_channel(int(league.discord_channel))
        await channel.send(content=congrats_message, embed=embed)
    session.close()
    await interaction.followup.send(f"Weekly scores for Week {week} have been sent to all active leagues.")

  async def notifySingleDraftTask(self, interaction: discord.Interaction, draft_id):
    session = await self.bot.get_session()
    message = await interaction.original_response()
    draft: Draft = session.query(Draft).filter(Draft.draft_id==draft_id).first()
    league: League = session.query(League).filter(League.league_id==draft.league_id).first()
    frcEvent: FRCEvent = session.query(FRCEvent).filter(FRCEvent.event_key==draft.event_key).first()
    if league:
        teams = session.query(FantasyScores).filter(FantasyScores.league_id == league.league_id)\
                    .filter(FantasyScores.event_key == frcEvent.event_key)\
                    .order_by(FantasyScores.weekly_score.desc()).all()
        title = f"Final Scores for {frcEvent.event_name}"
        embed = Embed(title=title, description=f"Here are the official scores for {frcEvent.event_name}")
        for idx, team_score in enumerate(teams):
            fantasy_team = team_score.fantasyTeam
            embed.add_field(name=f"{idx + 1}. {fantasy_team.fantasy_team_name}", 
                            value=f"Score: {team_score.weekly_score} points", inline=False)
        winning_team = teams[0].fantasyTeam
        winning_score = teams[0].weekly_score
        playersToNotify = session.query(PlayerAuthorized).filter(PlayerAuthorized.fantasy_team_id==winning_team.fantasy_team_id).all()
        congrats_message = f"**Congratulations to {winning_team.fantasy_team_name} for winning this draft with {winning_score} points!**\n"
        for player in playersToNotify:
          congrats_message += f"<@{player.player_id}> "
        channel = self.bot.get_channel(int(league.discord_channel))
        await channel.send(content=congrats_message, embed=embed)
    session.close()

  async def getLeagueStandingsTask(self, interaction: discord.Interaction, year, week):
    session = await self.bot.get_session()

    # Query for the week status to check if scores are finalized
    week_status = session.query(WeekStatus).filter(WeekStatus.year == year, WeekStatus.week == week).first()

    if not week_status:
        await interaction.followup.send(f"No status found for week {week} in year {year}.")
        session.close()
        return

    leagues = session.query(League).filter(League.is_fim == True, League.active == True).all()
    
    for league in leagues:
        # Retrieve all fantasy teams in the league
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
                            value=f"Ranking Points: {standing['total_score']} | Tiebreaker (Total Score): {standing['tiebreaker']}", 
                            inline=False)

        # Send the standings embed to the Discord channel
        channel = self.bot.get_channel(int(league.discord_channel))
        await channel.send(embed=embed)

    session.close()

    # Notify the user who triggered the command that the task is complete
    await interaction.followup.send(f"League standings for {year} up to week {week} have been sent to all active leagues.")

  async def addTeamsToEventTask(self, interaction: discord.Interaction, teams: str, draft: Draft): 
    session = await self.bot.get_session()
    # Step 1: Retrieve the associated FRCEvent from the draft object
    event = session.query(FRCEvent).filter_by(event_key=draft.event_key).first()
    if not event:
        await interaction.followup.send(f"Event with key {draft.event_key} not found.")
        return
    # Step 2: Split the comma-separated team list
    team_numbers = [team.strip() for team in teams.split(",")]
    # Step 3: Iterate through each team and create Team objects if they don't exist
    for team_number in team_numbers:
        team = session.query(Team).filter_by(team_number=team_number).first()
        if not team:
            # Create a new Team object
            team = Team(
                team_number=team_number,
                name="Offseason Team",
                rookie_year=1992
            )
            session.add(team)
    # Step 4: Flush the session to insert Team objects and generate primary keys
    session.flush()
    # Step 5: Create TeamScore objects for the event
    for team_number in team_numbers:
        team_score = TeamScore(
            team_key=team_number,
            event_key=event.event_key
        )
        session.add(team_score)
    # Step 6: Commit the changes
    session.commit()
    await interaction.followup.send(f"Teams added to event {event.event_name} successfully.")

  async def reassignBTeamTask(self, interaction: discord.Interaction, originalBTeam: str, newBTeamNumber: str, draft: Draft):
    session = await self.bot.get_session()

    try:
        # Step 1: Check if the draft and the originalBTeam exist in the current draft
        team_score = session.query(TeamScore).filter_by(
            team_key=originalBTeam,
            event_key=draft.event_key
        ).first()

        draft_pick = session.query(DraftPick).filter_by(
            team_number=originalBTeam,
            draft_id=draft.draft_id
        ).first()

        # If neither TeamScore nor DraftPick exist, notify the user
        if not team_score or not draft_pick:
            await interaction.followup.send(f"Could not find team '{originalBTeam}' in this draft.")
            return

        # Step 2: Check if the newBTeam exists
        new_team = session.query(Team).filter_by(team_number=newBTeamNumber).first()

        if not new_team:
            # Create the new Team object
            new_team = Team(
                team_number=newBTeamNumber,
                name="Offseason Team",
                rookie_year=1992
            )
            session.add(new_team)

            # Flush to ensure the new team is added to the session and available for foreign key references
            session.flush()

        # Check if a TeamScore already exists for the new team
        existing_team_score = session.query(TeamScore).filter_by(
            team_key=newBTeamNumber,
            event_key=draft.event_key
        ).first()

        if existing_team_score:
            await interaction.followup.send(f"A TeamScore already exists for team '{newBTeamNumber}'.")
            return

        # Step 3: Update the TeamScore and DraftPick to reflect the new team
        team_score.team_key = newBTeamNumber
        draft_pick.team_number = newBTeamNumber

        # Step 4: Commit changes
        session.commit()
        
        # Step 5: Send success message
        await interaction.followup.send(f"Successfully reassigned team '{originalBTeam}' to '{newBTeamNumber}'.")

    except Exception as e:
        await interaction.followup.send("An error occurred while reassigning the team. Please check the logs for more details.")
        print(e)  # Print the stack trace or log it appropriately
    finally:
        session.close()

  async def verifyAdmin(self, interaction: discord.Interaction):
    session = await self.bot.get_session()
    isAdmin = session.query(Player).filter(Player.user_id==str(interaction.user.id), Player.is_admin==True).first()
    if not isAdmin:
      await interaction.response.send_message("You are not authorized to use this command.")
      return False
    else:
      return True
    
  async def getForum(self):
    return self.bot.get_channel(int(FORUM_CHANNEL_ID))

  async def getLeagueId(self): #league id generation for primary key
    session = await self.bot.get_session()
    maxleague = session.query(League).order_by(League.league_id.desc()).first()
    if not maxleague == None:
      return maxleague.league_id + 1
    else:
      return 1
    
  async def getFantasyTeamId(self): #fantasy team id generation for primary key
    session = await self.bot.get_session()
    maxFantasyTeam = session.query(FantasyTeam).order_by(FantasyTeam.fantasy_team_id.desc()).first()
    if not maxFantasyTeam == None:
      return maxFantasyTeam.fantasy_team_id + 1
    else:
      return 1
    
  async def getDraftId(self): #draft id generation for primary key
    session = await self.bot.get_session()
    maxDraft = session.query(Draft).order_by(Draft.draft_id.desc()).first()
    if not maxDraft == None:
      return maxDraft.draft_id + 1
    else:
      return 1

  async def getFantasyTeamIdFromUserAndInteraction(self, interaction: discord.Interaction, user: discord.User):
        session = await self.bot.get_session()
        largeQuery = session.query(FantasyTeam)\
            .join(PlayerAuthorized, FantasyTeam.fantasy_team_id == PlayerAuthorized.fantasy_team_id)\
            .join(League, FantasyTeam.league_id == League.league_id)\
            .filter(PlayerAuthorized.player_id == str(user.id))\
            .filter(League.discord_channel == str(interaction.channel_id))
        team = largeQuery.first()
        session.close()
        if team:
            return team.fantasy_team_id
        else:
            return None

  @app_commands.command(name="updateteamlist", description="Grabs all teams from TBA (ADMIN)")
  async def updateTeamList(self, interaction: discord.Interaction, startpage: int = 0):    
    if (await self.verifyAdmin(interaction)):
      asyncio.create_task(self.updateTeamsTask(interaction, startpage))
      
  @app_commands.command(name="addleague", description="Create a new league (ADMIN)")
  async def createLeague(self, interaction: discord.Interaction, league_name: str, team_limit: int, year: int, is_fim: bool = False, team_starts: int = 3, team_size_limit: int = 3):
    if (await self.verifyAdmin(interaction)):
      forum = await self.getForum()
      threadName = f"{league_name} Thread"
      thread = (await forum.create_thread(content=f"This is your league thread for {league_name}",name=threadName))[0]
      threadId = thread.id   
      newLeagueId = await self.getLeagueId()
      leagueToAdd = League(league_id=newLeagueId, league_name=league_name, team_limit=team_limit,\
                           team_starts=team_starts, offseason=False, is_fim=is_fim, year=year, discord_channel=threadId, team_size_limit=team_size_limit)
      session = await self.bot.get_session()
      session.add(leagueToAdd)
      session.commit()
      await interaction.response.send_message(f"League created successfully! <#{threadId}>")
      session.close()

  @app_commands.command(name="createoffseason", description="Create a new offseason 'league' (ADMIN)")
  async def createOffseasonLeague(self, interaction: discord.Interaction, league_name: str, year: int, teams_to_draft: int = 3):
    if (await self.verifyAdmin(interaction)):
      forum = await self.getForum()
      threadName = f"{league_name} Thread"
      thread = (await forum.create_thread(content=f"This is your league thread for {league_name}",name=threadName))[0]
      threadId = thread.id   
      newLeagueId = await self.getLeagueId()
      leagueToAdd = League(league_id=newLeagueId, league_name=league_name, team_limit=100,\
                           team_starts=teams_to_draft, offseason=True, is_fim=False, year=year, discord_channel=threadId, team_size_limit=teams_to_draft)
      session = await self.bot.get_session()
      session.add(leagueToAdd)
      session.commit()
      await interaction.response.send_message(f"League created successfully! <#{threadId}>")
      session.close()

  @app_commands.command(name="createevent", description="Create an offseason event, only do if offseason + event isn't on TBA (ADMIN)")
  async def createOffseasonEvent(self, interaction: discord.Interaction, eventkey: str, eventname: str, year: int):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to create event {eventkey}")
      await self.createOffseasonEventTask(interaction, eventkey, eventname, year)

  @app_commands.command(name="registerteam", description="Register Fantasy Team (ADMIN)")
  async def registerTeam(self, interaction:discord.Interaction, teamname: str):
    if (await self.verifyAdmin(interaction)):
      session = await self.bot.get_session()
      leagues = session.query(League).filter(League.discord_channel==str(interaction.channel_id))
      leagueid = leagues.first().league_id
      teamsInLeague = session.query(FantasyTeam).filter(FantasyTeam.league_id==leagueid)
      if (leagues.count() == 0):
        await interaction.response.send_message(f"No leagues exist with id {leagueid}.")
        return
      elif (leagues.first().team_limit <= teamsInLeague.count()):
        await interaction.response.send_message(f"League with id {leagueid} is at max capacity.") 
        return
      newTeamId = await self.getFantasyTeamId()
      fantasyTeamToAdd = FantasyTeam(fantasy_team_id=newTeamId, fantasy_team_name=teamname, league_id=leagueid)
      #session = await self.bot.get_session()
      session.add(fantasyTeamToAdd)
      session.commit()
      await interaction.response.send_message(f"Team {teamname} created successfully in league with id {leagueid}. Team id is {fantasyTeamToAdd.fantasy_team_id}")
      session.close()

  @app_commands.command(name="fillleague", description="Populates a League to the max amount of teams with generic teams (ADMIN)")
  async def populateLeague(self, interaction:discord.Interaction):
      if (await self.verifyAdmin(interaction)):
        session = await self.bot.get_session()
        leagues = session.query(League).filter(League.discord_channel==str(interaction.channel_id))
        if (leagues.count() == 0):
          await interaction.response.send_message(f"No league exists in this channel.")
        leagueid = leagues.first().league_id
        teamsInLeague = session.query(FantasyTeam).filter(FantasyTeam.league_id==leagueid)
        teamLimit = leagues.first().team_limit
        if (teamLimit <= teamsInLeague.count()):
          await interaction.response.send_message(f"League is at max capacity.") 
          return
        while(teamLimit > teamsInLeague.count()):
          newTeamId = await self.getFantasyTeamId()
          fantasyTeamToAdd = FantasyTeam(fantasy_team_id=newTeamId, fantasy_team_name=f"Team {newTeamId}", league_id=leagueid)
          session.add(fantasyTeamToAdd)
          session.commit()
          teamsInLeague = session.query(FantasyTeam).filter(FantasyTeam.league_id==leagueid)
        await interaction.response.send_message(f"Teams created successfully!.")
        session.close()

  @app_commands.command(name="createdraft", description="Creates a fantasy draft for a given League and populates it with picks (ADMIN)")
  async def createDraft(self, interaction:discord.Interaction, event_key: str):
    if (await self.verifyAdmin(interaction)):
      session = await self.bot.get_session()
      leagues = session.query(League).filter(League.discord_channel==str(interaction.channel_id)).filter(League.active == True)
      rounds = leagues.first().team_size_limit
      if (leagues.count() == 0):
        await interaction.response.send_message(f"No active leagues exist in current channel.")
        return
      leagueid = leagues.first().league_id
      teamsInLeague = session.query(FantasyTeam).filter(FantasyTeam.league_id==leagueid)
      if (teamsInLeague.count() == 0):
        await interaction.response.send_message(f"Cannot create draft with no teams to draft")
        return
      if (leagues.first().team_starts > rounds):
        await interaction.response.send_message(f"Don't have enough rounds to draft!")
        return
      forum = await self.getForum()
      nameOfDraft = f"{leagues.first().league_name} draft for {event_key}"
      thread = (await forum.create_thread(content=f"{leagues.first().league_name} draft for {event_key}",name=nameOfDraft))[0]
      threadId = thread.id
      newDraftId = await self.getDraftId()
      draftToCreate = Draft(draft_id=newDraftId, league_id=leagueid, rounds=rounds, event_key=event_key, discord_channel=threadId)
      session.add(draftToCreate)
      session.commit()
      await interaction.response.send_message(f"Draft generated! <#{threadId}>")
      #generate draft order
      draftOrderEmbed = Embed(title=f"**Draft order**", description="```Draft Slot    Team Name (id)\n")
      randomizedteams = [fantasyTeam.fantasy_team_id for fantasyTeam in teamsInLeague]
      random.shuffle(randomizedteams)
      i = 1
      for team in randomizedteams:
        draftOrder = DraftOrder(draft_id = draftToCreate.draft_id, draft_slot = i, fantasy_team_id=team)
        teamname = teamsInLeague.filter(FantasyTeam.fantasy_team_id==team).first().fantasy_team_name
        draftOrderEmbed.description+=f"{i:>10d}    {teamname} ({team})\n"
        session.add(draftOrder)
        i+=1
      draftOrderEmbed.description+="```"
      await thread.send(embed=draftOrderEmbed)
      session.commit()
      session.close()      

  @app_commands.command(name="startdraft", description="Starts the draft in the current channel (ADMIN)")
  async def startDraft(self, interaction:discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      session = await self.bot.get_session()
      drafts = session.query(Draft).filter(Draft.discord_channel==str(interaction.channel_id))
      if (drafts.count() == 0):
        await interaction.response.send_message(f"This is not an active draft channel.")
        return
      await interaction.response.send_message(f"Generating draft picks")
      message = await interaction.original_response()
      draftid = drafts.first().draft_id
      draftOrders = session.query(DraftOrder).filter(DraftOrder.draft_id==draftid)
      if (draftOrders.count() == 0):
        await message.edit(content=f"Error generating draft picks.")
        return
      for teamDraftOrder in draftOrders.all():
        for k in range(drafts.first().rounds):
          pickNumber = k*draftOrders.count()
          if k%2 == 0: #handle serpentine
            pickNumber += teamDraftOrder.draft_slot
          else:
            pickNumber += (draftOrders.count()-teamDraftOrder.draft_slot)+1
          draftPickToAdd = DraftPick(draft_id=draftid, fantasy_team_id=teamDraftOrder.fantasy_team_id, pick_number=pickNumber, team_number=-1)
          session.add(draftPickToAdd)
      session.commit()
      await message.edit(content=f"Draft rounds generated!") 
      session.close()
      draftCog = drafting.Drafting(self.bot)
      await draftCog.postDraftBoard(interaction=interaction)
      await draftCog.notifyNextPick(interaction, draft_id=draftid)

  @app_commands.command(name="resetdraft", description="Resets an already started draft. (ADMIN)") 
  async def resetDraft(self, interaction:discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      session = await self.bot.get_session()
      drafts = session.query(Draft).filter(Draft.discord_channel==str(interaction.channel_id))
      if (drafts.count() == 0):
        await interaction.response.send_message(f"This is not a draft channel.")
        return
      draftid = drafts.first().draft_id
      session.query(DraftPick).filter(DraftPick.draft_id==draftid).delete()
      session.commit()
    await interaction.response.send_message(f"Successfully reset draft! Use command /startdraft to restart the draft.")

  @app_commands.command(name="updateevents", description="Update events for a given year (ADMIN)")
  async def updateEvents(self, interaction: discord.Interaction, year: int):
    if (await self.verifyAdmin(interaction)):
      asyncio.create_task(self.updateEventsTask(interaction, year))
    
  @app_commands.command(name="importoffseasonevent", description="Imports offseason event and team list from TBA (ADMIN)")
  async def importOffseasonEvent(self, interaction: discord.Interaction, eventkey: str):
    if (await self.verifyAdmin(interaction)):
      asyncio.create_task(self.importSingleEventTask(interaction, eventkey))

  @app_commands.command(name="importdistrict", description="Pull all registration data for district events and load db (ADMIN)")
  async def importDistrict(self, interaction: discord.Interaction, year: str, district: str = "fim"):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Force updating district {district}")
      asyncio.create_task(self.importFullDistrctTask(year, district))
  
  @app_commands.command(name="scoreupdate", description="Generate a score update for the given week (ADMIN)")
  async def updateScores(self, interaction: discord.Interaction, year: int, week: int, final: bool=False, states: bool=False):
    if await self.verifyAdmin(interaction):
      await interaction.response.send_message(f"Scoring all leagues for {year} week {week}")
      await self.scoreWeekTask(interaction, year, week)
      await self.scoreAllLeaguesTask(interaction, year, week, states=states)
      if final:
        session = await self.bot.get_session()
        weekToMod = session.query(WeekStatus).filter(WeekStatus.year==year).filter(WeekStatus.week==week).first()
        weekToMod.scores_finalized=True
        session.commit()
        session.close()
      await self.notifyWeeklyScoresTask(interaction, year, week)
      await self.getLeagueStandingsTask(interaction, year, week)

  @app_commands.command(name="authorize", description="Add an authorized user to a fantasy team (ADMIN)")
  async def authorizeUser(self, interaction:discord.Interaction, fantasyteamid: int, user: discord.User):
    if (await self.verifyAdmin(interaction)):
      session = await self.bot.get_session()
      player = session.query(Player).filter(Player.user_id==str(user.id))
      if (player.count() == 0):
        session.add(Player(user_id=user.id, is_admin=False))
        session.commit()
      if not (await self.bot.verifyTeamMemberByTeamId(fantasyteamid, user)):
        authorizeToAdd = PlayerAuthorized(fantasy_team_id=fantasyteamid, player_id=user.id)
        session.add(authorizeToAdd)
        session.commit()
        session.close()
        fantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyteamid).first()
        await interaction.response.send_message(f"Successfully added <@{user.id}> to {fantasyTeam.fantasy_team_name}!", ephemeral=True)
      else:
        session.close()
        await interaction.response.send_message("You can't add someone already on it to their own team dummy!", ephemeral=True)
    
  @app_commands.command(name="forcepick", description="Admin ability to force a draft pick (ADMIN)")
  async def forceDraftPick(self, interaction:discord.Interaction, team_number: str):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to force pick team {team_number}.")
      draftCog = drafting.Drafting(self.bot)
      await draftCog.makeDraftPickHandler(interaction=interaction, team_number=team_number, force=True)

  @app_commands.command(name="autopick", description="Admin ability to force an auto draft pick (ADMIN)")   
  async def forceAutoPick(self, interaction:discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to force pick best available team.")
      draftCog = drafting.Drafting(self.bot)
      draft: Draft = await draftCog.getDraftFromChannel(interaction=interaction)
      if (draft == None):
          await interaction.channel.send(content="No draft associated with this channel.")
          return
      league: League = await draftCog.getLeague(draft_id=draft.draft_id)
      suggestedTeams = await draftCog.getSuggestedTeamsList(eventKey=draft.event_key, year=league.year, isFiM=league.is_fim, draft_id=draft.draft_id, isOffseason=league.offseason)
      teamToPick = suggestedTeams[0][0]
      await draftCog.makeDraftPickHandler(interaction=interaction, team_number=teamToPick, force=True)

  @app_commands.command(name="statboticsupdate", description="Updates cache of Statbotics data (ADMIN)")   
  async def updateStatbotics(self, interaction:discord.Interaction, year: int):
    if (await self.verifyAdmin(interaction)):
      asyncio.create_task(self.updateStatboticsTask(interaction, year))

  @app_commands.command(name="deauthplayer", description="Remove a player from a team (ADMIN)")
  async def deauthPlayer(self, interaction:discord.Interaction, user: discord.User):
    if (await self.verifyAdmin(interaction)):
      if not await self.bot.verifyNotInLeague(interaction, user):
        session = await self.bot.get_session()
        fantasyId = await self.getFantasyTeamIdFromUserAndInteraction(interaction, user)
        playerAuthToDelete = session.query(PlayerAuthorized).filter(PlayerAuthorized.player_id==str(user.id)).filter(PlayerAuthorized.fantasy_team_id==fantasyId)
        playerAuthToDelete.delete()
        session.commit()
        session.close()
        await interaction.response.send_message(f"Successfully removed <@{user.id}> from league.", ephemeral=True)
      else:
        await interaction.response.send_message("Player is not on a team.")

  @app_commands.command(name="forcestart", description="Admin ability to force a team into a starting lineup (ADMIN)")
  async def forceStart(self, interaction:discord.Interaction, fantasyteamid: int, week: int, team_number: str):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to force start team {team_number}.")
      manageTeamCog = manageteam.ManageTeam(self.bot)
      await manageTeamCog.startTeamTask(interaction, team_number, week, fantasyteamid)

  @app_commands.command(name="forcesit", description="Admin ability to force a team out of a starting lineup (ADMIN)")
  async def forceSit(self, interaction:discord.Interaction, fantasyteamid: int, week: int, team_number: str):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to force sit team {team_number}.")
      manageTeamCog = manageteam.ManageTeam(self.bot)
      await manageTeamCog.sitTeamTask(interaction, team_number, week, fantasyteamid)

  @app_commands.command(name="viewteamlineup", description="Admin ability to view a team's starting lineup (ADMIN)")
  async def viewStartingLineup(self, interaction:discord.Interaction, fantasyteamid: int):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to view starting lineup of team {fantasyteamid}.")
      manageTeamCog = manageteam.ManageTeam(self.bot)
      await manageTeamCog.viewStartsTask(interaction, fantasyteamid)

  @app_commands.command(name="adminrenameteam", description="Admin ability to rename a team (ADMIN)")
  async def renameFantasyTeam(self, interaction:discord.Interaction, fantasyteamid: int, newname: str):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to rename team {fantasyteamid} to {newname}.")
      manageTeamCog = manageteam.ManageTeam(self.bot)
      await manageTeamCog.renameTeamTask(interaction, fantasyId=fantasyteamid, newname=newname)

  @app_commands.command(name="locklineups", description="Admin ability to lock lineups for the week (ADMIN)")
  async def lockLineups(self, interaction:discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      currentWeek = await self.bot.getCurrentWeek()
      if currentWeek == None:
        await interaction.response.send_message("No active week")
        return
      session = await self.bot.get_session()
      weekToMod = session.query(WeekStatus).filter(WeekStatus.year==currentWeek.year).filter(WeekStatus.week==currentWeek.week).first()
      weekToMod.lineups_locked=True
      session.query(TradeTeams).delete()
      session.flush()
      session.query(TradeProposal).delete()
      session.commit()
      session.close()
      await interaction.response.send_message(f"Locked lineups for week {currentWeek.week} in {currentWeek.year}")

  @app_commands.command(name="finishweek", description="Admin ability to deactivate the currently active week (ADMIN)")
  async def finishWeek(self, interaction:discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      currentWeek = await self.bot.getCurrentWeek()
      if currentWeek == None:
        await interaction.response.send_message("No active week")
        return
      await interaction.response.defer()
      message = await interaction.original_response()
      await self.put_teams_on_waivers(interaction)
      session = await self.bot.get_session()
      weekToMod = session.query(WeekStatus).filter(WeekStatus.year==currentWeek.year).filter(WeekStatus.week==currentWeek.week).first()
      weekToMod.active=False
      weekToMod.lock_lineups=True
      session.commit()
      session.close()
      await message.edit(content=f"Deactivated week {currentWeek.week} in {currentWeek.year}")
  
  @app_commands.command(name="remind", description="Remind players to set their lineups (ADMIN)")
  async def remindPlayers(self, interaction:discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message("Reminding all users with unfilled lineups to fill them.")
      session = await self.bot.get_session()
      leagues = session.query(League).where(League.active == True)
      if (leagues.count() == 0):
        await interaction.channel.send(content="There are no active leagues!")
      else:  
        for league in leagues.all():
          sendReminder = False
          reminderMessage = "Teams with unfilled lineups:\n"
          leagueTeams = session.query(FantasyTeam).where(FantasyTeam.league_id==league.league_id)
          for team in leagueTeams.all():
            numberOfStarters = session.query(TeamStarted).filter(TeamStarted.fantasy_team_id == team.fantasy_team_id)
            if (numberOfStarters.count() < league.team_starts):
              sendReminder = True
              playersToNotify = session.query(PlayerAuthorized).filter(PlayerAuthorized.fantasy_team_id == team.fantasy_team_id)
              reminderMessage+=f"{team.fantasy_team_name} "
              for player in playersToNotify.all():
                reminderMessage+=f"<@{player.player_id}> "
              reminderMessage+=f"currently starting {numberOfStarters.count()} of {league.team_starts}\n"
          if sendReminder:
            channel = await self.bot.fetch_channel(int(league.discord_channel))
            if not channel == None:
              await channel.send(content=reminderMessage)
      session.close()

  @app_commands.command(name="processwaivers", description="Process all waivers (ADMIN)")
  async def processWaivers(self, interaction: discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to process waivers")
      message = await interaction.original_response()
      session = await self.bot.get_session()
      leagues = session.query(League).where(League.active == True)
      week: WeekStatus = await self.bot.getCurrentWeek()
      if (leagues.count() == 0):
        await message.edit(content="There are no active leagues!")
      else:  
        for league in leagues.all():
          waiverReportEmbed = Embed(title=f"**{league.league_name} Week {week.week} Waiver Report**", description="")
          waiverClaims = session.query(WaiverClaim).filter(WaiverClaim.league_id==league.league_id)
          teamOnWaiversToAdd = []
          if (waiverClaims.count() > 0):
            waiverNum=1
            waiverPriorities = session.query(WaiverPriority).filter(WaiverPriority.league_id==league.league_id).order_by(WaiverPriority.priority.asc())
            lastTeam = waiverPriorities.count()
            while(waiverNum <= lastTeam):
              waiverPriorities = session.query(WaiverPriority).filter(WaiverPriority.league_id==league.league_id).order_by(WaiverPriority.priority.asc())
              currentPriority = waiverPriorities.filter(WaiverPriority.priority==waiverNum)
              priorityToCheck = currentPriority.first()
              fantasyTeam: FantasyTeam = priorityToCheck.fantasy_team
              waiverClaims = session.query(WaiverClaim).filter(WaiverClaim.fantasy_team_id==fantasyTeam.fantasy_team_id).order_by(WaiverClaim.priority.asc())
              if (waiverClaims.count() > 0):
                for waiverclaim in waiverClaims.all():
                  isTeamOnWaivers = session.query(TeamOnWaivers).filter(TeamOnWaivers.league_id==league.league_id).filter(TeamOnWaivers.team_number==waiverclaim.team_claimed)
                  isDropTeamOnRoster = session.query(TeamOwned).filter(TeamOwned.fantasy_team_id==fantasyTeam.fantasy_team_id).filter(TeamOwned.team_key==waiverclaim.team_to_drop)
                  if (isTeamOnWaivers.count() > 0 and isDropTeamOnRoster.count() > 0):
                    newWaiver = TeamOnWaivers(league_id=fantasyTeam.league_id, team_number=waiverclaim.team_to_drop)
                    teamOnWaiversToAdd.append(newWaiver)
                    #session.add(newWaiver)
                    isTeamOnWaivers.delete()
                    session.flush()
                    session.query(TeamStarted).filter(TeamStarted.league_id==fantasyTeam.league_id)\
                    .filter(TeamStarted.team_number==waiverclaim.team_to_drop).filter(TeamStarted.week >= week.week).delete()
                    session.flush()
                    session.query(TeamOwned).filter(TeamOwned.league_id==fantasyTeam.league_id).filter(TeamOwned.team_key==waiverclaim.team_to_drop).delete()
                    draftSoNotFail: Draft = session.query(Draft).filter(Draft.league_id==fantasyTeam.league_id).filter(Draft.event_key==str(league.year)+"fim").first()
                    session.flush()
                    newTeamToAdd = TeamOwned(
                        team_key=str(waiverclaim.team_claimed),
                        fantasy_team_id=fantasyTeam.fantasy_team_id,
                        league_id=fantasyTeam.league_id,
                        draft_id=draftSoNotFail.draft_id
                    )
                    session.add(newTeamToAdd)
                    session.flush()  
                    waiverReportEmbed.description+=f"{fantasyTeam.fantasy_team_name} successfully added team {waiverclaim.team_claimed} and dropped {waiverclaim.team_to_drop}!\n"
                    session.flush()
                    #move waiver priority
                    # Temporary placeholder value (e.g., set to -1 for the current priority)
                    priorityToCheck.priority = -1
                    session.flush()

                    # Now adjust all priorities (e.g., shift them down)
                    for prio in waiverPriorities.filter(WaiverPriority.priority > waiverNum).all():
                        prio.priority -= 1
                        session.flush()

                    # Finally, assign the last priority to the current team
                    priorityToCheck.priority = lastTeam
                    session.delete(waiverclaim)
                    session.flush()
                    break
                  elif (isTeamOnWaivers.count() == 0):
                    waiverReportEmbed.description+=f"{fantasyTeam.fantasy_team_name} tried to claim team {waiverclaim.team_claimed}, however they are no longer on waivers, unable to process\n"
                    session.delete(waiverclaim)
                    session.flush()
                  else:
                    waiverReportEmbed.description+=f"{fantasyTeam.fantasy_team_name} tried to claim team {waiverclaim.team_claimed} but their designated drop team {waiverclaim.team_to_drop} is no longer on the team, unable to process\n"
                    session.delete(waiverclaim)
                    session.flush()
              else:
                waiverNum+=1
          else:
            waiverReportEmbed.description+="No waiver claims to process"
          channel = await self.bot.fetch_channel(int(league.discord_channel))
          if not channel == None:
            await channel.send(embed=waiverReportEmbed)
          session.query(TeamOnWaivers).filter(TeamOnWaivers.league_id==league.league_id).delete()
          session.flush()
          session.add_all(teamOnWaiversToAdd)
          session.flush()
      session.commit()
      session.close()

  @app_commands.command(name="forceadddrop", description="Force an add/drop (ADMIN)")
  async def forceAddDrop(self, interaction: discord.Interaction, fantasyteamid: int, addteam: str, dropteam: str, towaivers: bool = True):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to admin drop {dropteam} to add {addteam} from team id {fantasyteamid}", ephemeral=True)
      manageTeamCog = manageteam.ManageTeam(self.bot)
      await manageTeamCog.addDropTeamTask(interaction, addTeam=addteam,dropTeam=dropteam, fantasyId=fantasyteamid, force=True, toWaivers=towaivers)

  @app_commands.command(name="forcetrade", description="Force a trade through (ADMIN)")
  async def forceTrade(self, interaction: discord.Interaction, teamid1: int, teamid2: int, team1trading: str, team2trading: str):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to admin force trade {team1trading} force {team2trading} for team ids {teamid1} and {teamid2}", ephemeral=True)
      manageTeamCog = manageteam.ManageTeam(self.bot)
      tradeProp: TradeProposal = await manageTeamCog.createTradeProposalTask(interaction, teamid1, teamid2, team1trading, team2trading, force=True)
      await manageTeamCog.acceptTradeTask(interaction, teamid2, tradeProp.trade_id, force=True)

  @app_commands.command(name="genweeks", description="Generate weeks for a given year (ADMIN)")
  async def genWeeks(self, interaction: discord.Interaction, year: int, week: int = -1):
    if (await self.verifyAdmin(interaction)):
      session = await self.bot.get_session()
      if week == -1:
        await interaction.response.send_message(f"Attempting to generate all weeks for {year}")
        session.query(WeekStatus).filter(WeekStatus.year==year).delete()
        session.flush()
        for k in range(1, 7):
          weekStatToadd = WeekStatus(week=k, year=year, lineups_locked=False, scores_finalized=False, active=True)
          session.add(weekStatToadd)
          session.flush()
      else:
        await interaction.response.send_message(f"Attempting to generate week {week} for {year}")
        session.query(WeekStatus).filter(WeekStatus.year==year).filter(WeekStatus.week==week).delete()
        session.flush()
        weekStatToadd = WeekStatus(week=week, year=year, lineups_locked=False, scores_finalized=False, active=True)
        session.add(weekStatToadd)
        session.flush()
      msg = await interaction.original_response()
      session.commit()
      await msg.edit(content="Success!")
      session.close()

  @app_commands.command(name="scoredraft", description="Score an individual draft")
  async def score_draft(self, interaction: discord.Interaction):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to score draft.")
      response = await interaction.original_response()
      draftCog = drafting.Drafting(self.bot)
      draft: Draft = await draftCog.getDraftFromChannel(interaction)
      if not draft:
        await response.edit(content="No draft associated with this channel")
        return
      league: League = await draftCog.getLeague(draft.draft_id)
      if league.is_fim:
        await response.edit(content="Not a valid league to run scoredraft in")
        return
      else:
        if league.offseason:
          await self.scoreOffseasonEventTask(interaction, draft.event_key)
        else:
          await self.scoreSingularEventTask(interaction, draft.event_key)
        await self.scoreSingleDraft(interaction, draft.draft_id)
        await self.notifySingleDraftTask(interaction, draft.draft_id)

  @app_commands.command(name="addeventteams", description="Add teams to an event (use for offseasons with released team list) (ADMIN)")
  async def addEventTeams(self, interaction: discord.Interaction, teams: str):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to admin add teams {teams} to event")
      response = await interaction.original_response()
      draftCog = drafting.Drafting(self.bot)
      draft: Draft = await draftCog.getDraftFromChannel(interaction)
      if not draft:
        await response.edit(content="No draft associated with this channel")
        return
      await self.addTeamsToEventTask(interaction, teams, draft)
      
  @app_commands.command(name="reassignbteam", description="Reassign B teams to different numbers (for use with offseasons) (ADMIN)")
  async def reassignBTeam(self, interaction: discord.Interaction, oldteamnumber: str, newteamnumber: str):
    if (await self.verifyAdmin(interaction)):
      await interaction.response.send_message(f"Attempting to admin reassign {oldteamnumber} to {newteamnumber} for this event")
      response = await interaction.original_response()
      draftCog = drafting.Drafting(self.bot)
      draft: Draft = await draftCog.getDraftFromChannel(interaction)
      if not draft:
        await response.edit(content="No draft associated with this channel")
        return
      await self.reassignBTeamTask(interaction, oldteamnumber, newteamnumber, draft)

async def setup(bot: commands.Bot) -> None:
  cog = Admin(bot)
  guild = await bot.fetch_guild(int(os.getenv("GUILD_ID")))
  assert guild is not None

  await bot.add_cog(
      cog,
    guilds=[guild]
  )
