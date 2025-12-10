import asyncio
import datetime
import logging
import os
import random
import traceback

import discord
import requests
from discord import Embed, app_commands
from discord.ext import commands
from sqlalchemy import delete, or_, select, update

import cogs.drafting as drafting
import cogs.manageteam as manageteam
from models.draft import Draft, DraftOrder, DraftPick, StatboticsData
from models.scores import (
    FantasyScores,
    FantasyTeam,
    FRCEvent,
    League,
    PlayerAuthorized,
    Team,
    TeamOwned,
    TeamScore,
    TeamStarted,
    WeekStatus,
)
from models.transactions import (
    TeamOnWaivers,
    TradeProposal,
    TradeTeams,
    WaiverClaim,
    WaiverPriority,
)
from models.users import Player

logger = logging.getLogger("discord")
TBA_API_ENDPOINT = "https://www.thebluealliance.com/api/v3/"


def get_tba_headers() -> dict:
    auth_key = os.getenv("TBA_API_KEY")
    if not auth_key:
        logger.error(
            "TBA_API_KEY environment variable is not set; cannot contact The Blue Alliance API."
        )
        raise RuntimeError("TBA_API_KEY environment variable is not set")
    return {"X-TBA-Auth-Key": auth_key}


FORUM_CHANNEL_ID = os.getenv("DRAFT_FORUM_ID")
STATBOTICS_ENDPOINT = "https://api.statbotics.io/v3/team_years"


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def put_teams_on_waivers(self, interaction: discord.Interaction):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            result = await session.execute(
                select(WeekStatus)
                .where(WeekStatus.active)
                .order_by(WeekStatus.year.asc(), WeekStatus.week.asc())
            )
            currentWeek = result.scalars().first()

            if not currentWeek:
                await message.channel.send(
                    content="No active weeks found. No teams will be put on waivers."
                )
                return

            leagues_result = await session.execute(
                select(League).where(League.is_fim, League.active)
            )
            leagues = leagues_result.scalars().all()

            if not leagues:
                await message.channel.send(
                    content="No active FIM leagues found. No teams will be put on waivers."
                )
                return

            for league in leagues:
                competing_result = await session.execute(
                    select(TeamScore.team_key)
                    .join(Team, Team.team_number == TeamScore.team_key)
                    .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key)
                    .where(Team.is_fim, FRCEvent.week == currentWeek.week)
                    .where(FRCEvent.year == currentWeek.year)
                )
                competing_teams = competing_result.all()

                teams_to_put_on_waivers = []
                for team_number in competing_teams:
                    owned_result = await session.execute(
                        select(TeamOwned).where(
                            TeamOwned.league_id == league.league_id,
                            TeamOwned.team_key == team_number[0],
                        )
                    )
                    is_owned = owned_result.scalars().first() is not None
                    waivers_result = await session.execute(
                        select(TeamOnWaivers).where(
                            TeamOnWaivers.team_number == team_number[0],
                            TeamOnWaivers.league_id == league.league_id,
                        )
                    )
                    is_on_waivers = waivers_result.scalars().first() is not None

                    if not is_owned and not is_on_waivers:
                        teams_to_put_on_waivers.append(team_number[0])

                if teams_to_put_on_waivers:
                    team_on_waivers_objects = [
                        TeamOnWaivers(
                            league_id=league.league_id, team_number=team_number
                        )
                        for team_number in teams_to_put_on_waivers
                    ]
                    for wTeam in team_on_waivers_objects:
                        check_result = await session.execute(
                            select(TeamOnWaivers).where(
                                TeamOnWaivers.league_id == league.league_id,
                                TeamOnWaivers.team_number == wTeam.team_number,
                            )
                        )
                        if check_result.scalars().first() is None:
                            session.add(wTeam)
                            await session.flush()
                    await session.commit()
                    await message.channel.send(
                        embed=Embed(
                            title=f"Placed teams on waivers for league {league.league_name}",
                            description=f"{teams_to_put_on_waivers}",
                        )
                    )
                else:
                    await message.channel.send(
                        content=f"No teams meet the criteria to be put on waivers for league {league.league_name}."
                    )

    async def updateStatboticsTask(self, interaction, year):
        embed = Embed(
            title="Update Team List",
            description=f"Updating year end team data from Statbotics for {year}",
        )
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        if datetime.date.today().year < year or year < 2005:
            embed.description = "Invalid year. Please try again"
            await message.edit(embed=embed)
            return
        async with self.bot.async_session() as session:
            i = 0
            delete_result = await session.execute(
                delete(StatboticsData).where(StatboticsData.year == year)
            )
            deleted_count = delete_result.rowcount
            await session.commit()
            logger.info(f"Deleted {deleted_count} Statbotics records for {year}")

            offset = 0
            while True:
                try:
                    requestURL = (
                        f"{STATBOTICS_ENDPOINT}?year={year}&limit=500&offset={offset}"
                    )
                    response = requests.get(requestURL, timeout=30)
                    if response.status_code != 200:
                        break
                    data = response.json()
                    if not data:
                        break
                    for team_year in data:
                        team_number = str(team_year.get("team"))
                        team_result = await session.execute(
                            select(Team).where(Team.team_number == team_number)
                        )
                        if team_result.scalars().first() is None:
                            logger.warning(
                                f"Skipping team {team_number} - not present in teams table"
                            )
                            continue
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
                        logger.info(
                            f"Team number: {team_number} Year: {year} year_end_epa: {int(unitless_epa)}"
                        )
                        session.add(
                            StatboticsData(
                                team_number=team_number,
                                year=year,
                                year_end_epa=int(unitless_epa),
                            )
                        )
                    await session.commit()
                    i += len(data)
                    offset += 500
                    if i % 50 == 0:
                        embed.description = f"Processed {i} Teams"
                        await message.edit(embed=embed)
                except Exception:
                    logger.error(traceback.format_exc())
                    break

    async def updateTeamsTask(self, interaction, startPage):
        embed = Embed(
            title="Update Team List",
            description="Updating team list from The Blue Alliance",
        )
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        reqheaders = get_tba_headers()

        async with self.bot.async_session() as session:
            try:
                teams_result = await session.execute(select(Team))
                existing_teams = {
                    team.team_number: team for team in teams_result.scalars().all()
                }
                current_page = startPage
                processed = startPage * 500

                with requests.Session() as http_session:
                    while True:
                        requestURL = f"{TBA_API_ENDPOINT}teams/{current_page}"
                        try:
                            response = http_session.get(
                                requestURL, headers=reqheaders, timeout=30
                            )
                            response.raise_for_status()
                        except requests.RequestException:
                            embed.description = (
                                "Error updating team list from The Blue Alliance"
                            )
                            await message.edit(embed=embed)
                            logger.error(traceback.format_exc())
                            return

                        teams_payload = response.json()
                        if not teams_payload:
                            break

                        for team in teams_payload:
                            team_number = str(team.get("team_number"))
                            if not team_number:
                                continue

                            nickname = team.get("nickname") or team.get("name") or ""
                            rookie_year = team.get("rookie_year")
                            is_fim = team.get("state_prov") == "Michigan"

                            existing_team = existing_teams.get(team_number)

                            if existing_team is None:
                                logger.info(f"Inserting team number {team_number}")
                                new_team = Team(
                                    team_number=team_number,
                                    name=str(nickname),
                                    is_fim=is_fim,
                                    rookie_year=rookie_year,
                                )
                                session.add(new_team)
                                existing_teams[team_number] = new_team
                            else:
                                updated = False

                                if existing_team.name != str(nickname):
                                    existing_team.name = str(nickname)
                                    updated = True

                                if existing_team.rookie_year != rookie_year:
                                    existing_team.rookie_year = rookie_year
                                    updated = True

                                if existing_team.is_fim != is_fim:
                                    existing_team.is_fim = is_fim
                                    updated = True

                                if updated:
                                    logger.info(
                                        f"Updating team number {team_number}, team name {nickname}, rookie year {rookie_year}"
                                    )

                        current_page += 1
                        processed += len(teams_payload)
                        embed.description = f"Updating team list: Processed {processed} teams (Page {current_page})"
                        await message.edit(embed=embed)
                        await session.commit()

                embed.description = "Updated team list from The Blue Alliance"
                await message.edit(embed=embed)
            except Exception:
                embed.description = "Error updating team list from The Blue Alliance"
                await message.edit(embed=embed)
                logger.error(traceback.format_exc())

    async def updateEventsTask(self, interaction, year):
        embed = Embed(
            title="Update Event List",
            description=f"Updating event list for {year} from The Blue Alliance",
        )
        newEventsEmbed = Embed(title="New Events", description="No new events")
        eventsLog = await self.bot.log_message("New Events", "No new events")
        await interaction.response.send_message(embed=embed)
        reqheaders = get_tba_headers()
        async with self.bot.async_session() as session:
            try:
                requestURL = TBA_API_ENDPOINT + "events/" + str(year)
                response = requests.get(
                    requestURL, headers=reqheaders, timeout=30
                ).json()
                totalEvents = len(response)
                i = 0
                for event in response:
                    if event["event_type"] not in [99, 100]:
                        eventKey = str(event["key"])
                        eventName = str(event["name"])
                        if event["event_type"] in [3, 4]:
                            week = 8
                        else:
                            week = str(event["week"] + 1)
                        filtered_result = await session.execute(
                            select(FRCEvent).where(
                                FRCEvent.year == year, FRCEvent.event_key == eventKey
                            )
                        )
                        existing_event = filtered_result.scalars().first()
                        if existing_event is None:
                            logger.info(f"Inserting event {eventKey}: {eventName}")
                            newEventsEmbed.description = (
                                f"Found new event {eventKey}: {eventName}"
                            )
                            eventsLog.edit(embed=newEventsEmbed)
                            isFiM = False
                            if (
                                event["district"] is not None
                                and event["district"]["abbreviation"] == "fim"
                            ):
                                isFiM = True
                            eventToAdd = FRCEvent(
                                event_key=eventKey,
                                event_name=eventName,
                                year=year,
                                week=week,
                                is_fim=isFiM,
                            )
                            session.add(eventToAdd)
                        elif not (
                            existing_event.event_name == eventName
                            and str(existing_event.year) == str(year)
                            and str(existing_event.week) == str(week)
                        ):
                            logger.info(f"Updating event {eventKey}")
                            existing_event.event_name = eventName
                            existing_event.year = year
                            existing_event.week = week
                    i += 1
                    if i % 25 == 0:
                        embed.description = (
                            f"Updating event list: Processed {i}/{totalEvents} events"
                        )
                        await interaction.edit_original_response(embed=embed)
                await session.commit()
            except Exception:
                logger.error(traceback.format_exc())
                embed.description = "Error updating event list from The Blue Alliance"
                await interaction.edit_original_response(embed=embed)
                return
            embed.description = "Updated event list from The Blue Alliance"
            await interaction.edit_original_response(embed=embed)

    async def importSingleEventTask(self, interaction, eventKey):
        embed = Embed(
            title=f"Import Event {eventKey}",
            description=f"Importing event info for key {eventKey} from The Blue Alliance",
        )
        await interaction.response.send_message(embed=embed)
        reqheaders = get_tba_headers()
        async with self.bot.async_session() as session:
            try:
                requestURL = TBA_API_ENDPOINT + "event/" + str(eventKey)
                response = requests.get(
                    requestURL, headers=reqheaders, timeout=30
                ).json()
                if "key" not in response.keys():
                    await interaction.response.send_message(
                        f"Event {eventKey} does not exist on The Blue Alliance"
                    )
                    return
                eventKey = str(response["key"])
                eventName = str(response["name"])
                week = 99
                year = eventKey[:4]
                event_result = await session.execute(
                    select(FRCEvent).where(FRCEvent.event_key == eventKey)
                )
                existing_event = event_result.scalars().first()
                if existing_event is None:
                    logger.info(f"Inserting event {eventKey}: {eventName}")
                    isFiM = False
                    eventToAdd = FRCEvent(
                        event_key=eventKey,
                        event_name=eventName,
                        year=year,
                        week=week,
                        is_fim=isFiM,
                    )
                    session.add(eventToAdd)
                elif not (
                    existing_event.event_name == eventName
                    and str(existing_event.year) == str(year)
                    and str(existing_event.week) == str(week)
                ):
                    logger.info(f"Updating event {eventKey}")
                    existing_event.event_name = eventName
                    existing_event.year = year
                    existing_event.week = week
                embed.description = f"Retrieving {eventKey} teams"
                await interaction.edit_original_response(embed=embed)
                requestURL += "/teams/simple"
                response = requests.get(
                    requestURL, headers=reqheaders, timeout=30
                ).json()
                for team in response:
                    teamNumber = str(team["team_number"])
                    score_result = await session.execute(
                        select(TeamScore).where(
                            TeamScore.event_key == eventKey,
                            TeamScore.team_key == teamNumber,
                        )
                    )
                    if score_result.scalars().first() is None:
                        logger.info(f"Team {teamNumber} registered for {eventKey}")
                        teamScoreToAdd = TeamScore(
                            team_key=teamNumber, event_key=eventKey
                        )
                        session.add(teamScoreToAdd)
                await session.commit()
                embed.description = f"Retrieved all {eventKey} information"
                await interaction.edit_original_response(embed=embed)
            except Exception:
                embed.description = f"Error retrieving offseason event {eventKey} from The Blue Alliance"
                await interaction.edit_original_response(embed=embed)
                logger.error(traceback.format_exc())
                return

    async def createOffseasonEventTask(
        self, interaction: discord.Interaction, eventKey, eventName, year
    ):
        message = await interaction.original_response()
        async with self.bot.async_session() as session:
            event_result = await session.execute(
                select(FRCEvent).where(FRCEvent.event_key == eventKey)
            )
            if event_result.scalars().first() is not None:
                await message.channel.send(content=f"{eventKey} already in database")
            else:
                newEvent = FRCEvent(
                    event_key=eventKey,
                    event_name=eventName,
                    year=year,
                    week=99,
                    is_fim=False,
                )
                session.add(newEvent)
                await session.commit()
                await message.channel.send(content=f"{eventKey} created!")

    async def importFullDistrctTask(self, year, district: str = "fim"):
        embed = Embed(
            title=f"Importing {district} District",
            description=f"Importing event info for all {district} districts from The Blue Alliance",
        )
        originalMessage = await self.bot.log_message(embed=embed)
        newEventsEmbed = Embed(title="New Events", description="No new events")
        eventsLog = await self.bot.log_message("New Events", "No new events")

        reqheaders = get_tba_headers()

        async with self.bot.async_session() as session:
            try:
                with requests.Session() as http_session:
                    requestURL = (
                        TBA_API_ENDPOINT
                        + "district/"
                        + str(year)
                        + str(district)
                        + "/events"
                    )
                    logger.info(requestURL)

                    response = http_session.get(
                        requestURL, headers=reqheaders, timeout=30
                    )
                    response.raise_for_status()
                    events_payload = response.json()
                    logger.info(events_payload)

                    if not isinstance(events_payload, list):
                        embed.description = (
                            f"District {district} does not exist on The Blue Alliance"
                        )
                        await originalMessage.edit(embed=embed)
                        return

                    numberOfEvents = len(events_payload)

                    events_result = await session.execute(
                        select(FRCEvent).where(FRCEvent.year == year)
                    )
                    existing_events = {
                        event.event_key: event
                        for event in events_result.scalars().all()
                    }

                    first_new_event = True

                    for index, event in enumerate(events_payload, start=1):
                        week = int(event.get("week", 0)) + 1
                        if event.get("event_type") in [1, 2, 5]:
                            eventKey = str(event.get("key"))
                            eventName = str(event.get("name"))
                            eventYear = int(eventKey[:4])

                            existing_event = existing_events.get(eventKey)

                            if existing_event is None:
                                logger.info(f"Inserting event {eventKey}: {eventName}")
                                if first_new_event:
                                    newEventsEmbed.description = ""
                                    first_new_event = False
                                newEventsEmbed.description += (
                                    f"Found new event {eventKey}: {eventName}\n"
                                )
                                await eventsLog.edit(embed=newEventsEmbed)
                                isFiM = district.lower() == "fim"
                                eventToAdd = FRCEvent(
                                    event_key=eventKey,
                                    event_name=eventName,
                                    year=eventYear,
                                    week=week,
                                    is_fim=isFiM,
                                )
                                session.add(eventToAdd)
                                existing_events[eventKey] = eventToAdd
                            else:
                                updated = False
                                if existing_event.event_name != eventName:
                                    existing_event.event_name = eventName
                                    updated = True
                                if existing_event.year != eventYear:
                                    existing_event.year = eventYear
                                    updated = True
                                if existing_event.week != week:
                                    existing_event.week = week
                                    updated = True
                                if updated:
                                    logger.info(f"Updating event {eventKey}")

                            embed.description = f"Retrieving {eventKey} teams (Event {index}/{numberOfEvents})"
                            await originalMessage.edit(embed=embed)

                            teams_url = (
                                f"{TBA_API_ENDPOINT}event/{eventKey}/teams/simple"
                            )
                            teams_response = http_session.get(
                                teams_url, headers=reqheaders, timeout=30
                            )
                            teams_response.raise_for_status()
                            teams_payload = teams_response.json()

                            scores_result = await session.execute(
                                select(TeamScore).where(TeamScore.event_key == eventKey)
                            )
                            existing_scores = {
                                score.team_key: score
                                for score in scores_result.scalars().all()
                            }

                            teamRegistrationChangeEmbed = None
                            teamRegistrationChangeMsg = None

                            for team in teams_payload:
                                teamNumber = str(team.get("team_number"))
                                if not teamNumber:
                                    continue

                                if teamNumber not in existing_scores:
                                    logger.info(
                                        f"Team {teamNumber} registered for {eventKey}"
                                    )
                                    session.add(
                                        TeamScore(
                                            team_key=teamNumber, event_key=eventKey
                                        )
                                    )
                                    change_text = (
                                        f"Team {teamNumber} registered for {eventKey}"
                                    )
                                    if teamRegistrationChangeMsg is None:
                                        teamRegistrationChangeMsg = (
                                            await self.bot.log_message(
                                                f"{eventKey} registration changes",
                                                change_text,
                                            )
                                        )
                                        teamRegistrationChangeEmbed = Embed(
                                            title=f"{eventKey} registration changes",
                                            description=change_text,
                                        )
                                        await teamRegistrationChangeMsg.edit(
                                            embed=teamRegistrationChangeEmbed
                                        )
                                    else:
                                        teamRegistrationChangeEmbed.description += (
                                            f"\n{change_text}"
                                        )
                                        await teamRegistrationChangeMsg.edit(
                                            embed=teamRegistrationChangeEmbed
                                        )
                                else:
                                    existing_scores.pop(teamNumber, None)

                            for teamNumber, teamscore in existing_scores.items():
                                logger.info(
                                    f"Team {teamNumber} un-registered from {eventKey}"
                                )
                                await session.delete(teamscore)
                                change_text = (
                                    f"Team {teamNumber} un-registered from {eventKey}"
                                )
                                if teamRegistrationChangeMsg is None:
                                    teamRegistrationChangeMsg = (
                                        await self.bot.log_message(
                                            f"{eventKey} registration changes",
                                            change_text,
                                        )
                                    )
                                    teamRegistrationChangeEmbed = Embed(
                                        title=f"{eventKey} registration changes",
                                        description=change_text,
                                    )
                                    await teamRegistrationChangeMsg.edit(
                                        embed=teamRegistrationChangeEmbed
                                    )
                                else:
                                    teamRegistrationChangeEmbed.description += (
                                        f"\n{change_text}"
                                    )
                                    await teamRegistrationChangeMsg.edit(
                                        embed=teamRegistrationChangeEmbed
                                    )

                    await session.commit()

                    await eventsLog.edit(embed=newEventsEmbed)

                    embed.description = f"Retrieved all {district} information"
                    await originalMessage.edit(embed=embed)
            except requests.RequestException:
                embed.description = f"Error retrieving district {district} information from The Blue Alliance"
                await originalMessage.edit(embed=embed)
                logger.error(traceback.format_exc())
            except Exception:
                embed.description = (
                    f"Unexpected error retrieving district {district} information"
                )
                await originalMessage.edit(embed=embed)
                logger.error(traceback.format_exc())

    async def scoreSingularEventTask(
        self, interaction: discord.Interaction, eventKey: str
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            event_result = await session.execute(
                select(FRCEvent).where(FRCEvent.event_key == eventKey)
            )
            eventToScore: FRCEvent = event_result.scalars().first()
            embed = Embed(
                title=f"Scoring {eventKey}",
                description=f"Importing event info for {eventKey} from The Blue Alliance",
            )
            await message.edit(content="", embed=embed)
            embed.description = ""
            if eventToScore and eventToScore.is_fim:
                logger.info(f"Event to score: {eventToScore.event_name}")
                requestURL = (
                    TBA_API_ENDPOINT
                    + "event/"
                    + eventToScore.event_key
                    + "/district_points"
                )
                reqheaders = get_tba_headers()
                eventresponse = requests.get(
                    requestURL, headers=reqheaders, timeout=30
                ).json()
                for team in eventresponse["points"]:
                    team_key = team[3:]
                    score_result = await session.execute(
                        select(TeamScore).where(
                            TeamScore.event_key == eventToScore.event_key,
                            TeamScore.team_key == team_key,
                        )
                    )
                    teamscore = score_result.scalars().first()
                    if teamscore is None:
                        teamscore = TeamScore(
                            team_key=team_key, event_key=eventToScore.event_key
                        )
                        session.add(teamscore)
                        await session.flush()
                    teamscore.qual_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["qual_points"]
                    teamscore.alliance_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["alliance_points"]
                    teamscore.elim_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["elim_points"]
                    teamscore.award_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["award_points"]
                    team_result = await session.execute(
                        select(Team).where(Team.team_number == teamscore.team_key)
                    )
                    team_obj = team_result.scalars().first()
                    if not eventToScore.week == 6:
                        if int(team_obj.rookie_year) == int(eventToScore.year):
                            teamscore.rookie_points = 5
                        elif int(team_obj.rookie_year) == int(eventToScore.year) - 1:
                            teamscore.rookie_points = 2
                embed.description += (
                    f"Successfully scored **{eventToScore.event_name}**\n"
                )
                await message.edit(embed=embed)
                await session.commit()
            elif eventToScore:
                await self.scoreOffseasonEventTask(interaction, eventKey)
            else:
                await message.edit(content=f"Could not find event {eventKey}")

    async def scoreOffseasonEventTask(
        self, interaction: discord.Interaction, eventKey: str
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            event_result = await session.execute(
                select(FRCEvent).where(FRCEvent.event_key == eventKey)
            )
            eventToScore: FRCEvent = event_result.scalars().first()
            embed = Embed(
                title=f"Scoring {eventKey}",
                description=f"Importing event info for {eventKey} from The Blue Alliance",
            )
            await message.edit(content="", embed=embed)
            embed.description = ""
            if eventToScore:
                logger.info(f"Event to score: {eventToScore.event_name}")
                requestURL = (
                    TBA_API_ENDPOINT
                    + "event/"
                    + eventToScore.event_key
                    + "/teams/statuses"
                )
                reqheaders = get_tba_headers()
                statusesResponse = requests.get(
                    requestURL, headers=reqheaders, timeout=30
                ).json()
                for teamKey in statusesResponse.keys():
                    teamJson = statusesResponse[teamKey]
                    if teamJson is None:
                        continue
                    teamNum = teamKey[3:]
                    score_result = await session.execute(
                        select(TeamScore).where(
                            TeamScore.event_key == eventKey,
                            TeamScore.team_key == teamNum,
                        )
                    )
                    teamScoreToMod: TeamScore = score_result.scalars().first()
                    if not teamScoreToMod:
                        teamScoreToMod = TeamScore(team_key=teamNum, event_key=eventKey)
                        session.add(teamScoreToMod)
                        await session.flush()
                    notCompeted = teamJson["qual"] is None
                    if notCompeted:
                        continue
                    # TODO: fix ranking data
                    rankData = teamJson["qual"]["ranking"]
                    numTeams = teamJson["qual"]["num_teams"]
                    teamScoreToMod.update_qualification_points(
                        int(rankData["rank"]), int(numTeams)
                    )  # qual points
                    allianceData = teamJson["alliance"]
                    if not allianceData:
                        teamScoreToMod.update_alliance_points()
                    else:
                        pick = None
                        if allianceData["pick"] in [0, 1]:
                            pick = int(allianceData["number"])
                        elif allianceData["pick"] == 2:
                            pick = 17 - int(allianceData["number"])
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
                    await session.flush()
                embed.description += (
                    f"Successfully scored **{eventToScore.event_name}**\n"
                )
                await message.edit(embed=embed)
                await session.commit()
            else:
                await message.edit(content=f"Could not find event {eventKey}")

    async def scoreWeekTask(self, interaction: discord.Interaction, year, week):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            week_result = await session.execute(
                select(WeekStatus).where(
                    WeekStatus.week == week, WeekStatus.year == year
                )
            )
            weekStatus = week_result.scalars().first()
            if weekStatus is None:
                await message.edit(content="No week to score.")
                return
            elif weekStatus.scores_finalized:
                await message.edit(content="Scores are already finalized.")
                return
            events_result = await session.execute(
                select(FRCEvent).where(
                    FRCEvent.year == year,
                    FRCEvent.is_fim,
                    FRCEvent.week == week,
                )
            )
            eventsToScore = events_result.scalars().all()
            embed = Embed(
                title=f"Scoring week {week} for {year}",
                description=f"Importing event info for all {year} week {week} districts from The Blue Alliance",
            )
            await message.edit(content="", embed=embed)
            embed.description = ""
            logger.info(f"Events to score: {len(eventsToScore)}")
            for event in eventsToScore:
                logger.info(f"Event to score: {event.event_name}")
                requestURL = (
                    TBA_API_ENDPOINT + "event/" + event.event_key + "/district_points"
                )
                reqheaders = get_tba_headers()
                eventresponse = requests.get(
                    requestURL, headers=reqheaders, timeout=30
                ).json()
                for team in eventresponse["points"]:
                    team_key = team[3:]
                    score_result = await session.execute(
                        select(TeamScore).where(
                            TeamScore.event_key == event.event_key,
                            TeamScore.team_key == team_key,
                        )
                    )
                    teamscore = score_result.scalars().first()
                    if teamscore is None:
                        teamscore = TeamScore(
                            team_key=team_key, event_key=event.event_key
                        )
                        session.add(teamscore)
                        await session.flush()
                    teamscore.qual_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["qual_points"]
                    teamscore.alliance_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["alliance_points"]
                    teamscore.elim_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["elim_points"]
                    teamscore.award_points = eventresponse["points"][
                        "frc" + teamscore.team_key
                    ]["award_points"]
                    if teamscore.award_points == 10:
                        teamscore.award_points += 10
                    elif teamscore.award_points == 30:
                        teamscore.award_points += 30
                    team_result = await session.execute(
                        select(Team).where(Team.team_number == teamscore.team_key)
                    )
                    team_obj = team_result.scalars().first()
                    if not week == 6:
                        if int(team_obj.rookie_year) == int(year):
                            teamscore.rookie_points = 5
                        elif int(team_obj.rookie_year) == int(year) - 1:
                            teamscore.rookie_points = 2
                embed.description += f"Successfully scored **{event.event_name}**\n"
                await message.edit(embed=embed)
                await session.commit()
            embed.description += f"**All events scored for week {week}**"
            await message.edit(embed=embed)

    async def scoreAllLeaguesTask(
        self, interaction: discord.Interaction, year, week, states=False
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            leagues_result = await session.execute(
                select(League).where(League.is_fim, League.year == year)
            )
            allLeagues = leagues_result.scalars().all()
            week_result = await session.execute(
                select(WeekStatus).where(
                    WeekStatus.week == week, WeekStatus.year == year
                )
            )
            weekStatus = week_result.scalars().first()
            if weekStatus is None:
                await message.edit(content="No week to score.")
                return
            elif weekStatus.scores_finalized:
                await message.edit(content="Scores are already finalized.")
                return
            for league in allLeagues:
                teams_result = await session.execute(
                    select(FantasyTeam).where(FantasyTeam.league_id == league.league_id)
                )
                fantasyTeams = teams_result.scalars().all()

                # Calculate scores for each fantasy team
                for fantasyTeam in fantasyTeams:
                    score_result = await session.execute(
                        select(FantasyScores).where(
                            FantasyScores.fantasy_team_id
                            == fantasyTeam.fantasy_team_id,
                            FantasyScores.week == week,
                        )
                    )
                    teamscore = score_result.scalars().first()
                    if not teamscore:
                        teamscore = FantasyScores(
                            league_id=league.league_id,
                            fantasy_team_id=fantasyTeam.fantasy_team_id,
                            event_key=f"fim{league.year}",
                            week=week,
                            rank_points=0,
                            weekly_score=0,
                        )
                        session.add(teamscore)
                        await session.flush()

                    starts_result = await session.execute(
                        select(TeamStarted).where(
                            TeamStarted.fantasy_team_id == fantasyTeam.fantasy_team_id,
                            TeamStarted.week == week,
                        )
                    )
                    teamstarts = starts_result.scalars().all()

                    # Calculate weekly score based on team starts
                    weekly_score = 0

                    for start in teamstarts:
                        if states:
                            # States Week: Count all points across all events the team competes in,
                            # including the Michigan Championship event
                            team_scores_result = await session.execute(
                                select(TeamScore)
                                .join(FRCEvent)
                                .where(
                                    TeamScore.team_key == start.team_number,
                                    FRCEvent.year == year,
                                    or_(
                                        FRCEvent.week == week,
                                        FRCEvent.event_key == f"{year}micmp",
                                    ),
                                )
                            )
                            team_scores = team_scores_result.scalars().all()
                        else:
                            # Pre-States: Only include points for the specific event in TeamStarted
                            team_scores_result = await session.execute(
                                select(TeamScore).where(
                                    TeamScore.team_key == start.team_number,
                                    TeamScore.event_key == start.event_key,
                                )
                            )
                            team_scores = team_scores_result.scalars().all()

                        # Sum up the scores for this team
                        for score in team_scores:
                            weekly_score += score.score_team()

                    teamscore.weekly_score = weekly_score
                    await session.flush()

                # Retrieve all scores for the league in the current week
                rank_result = await session.execute(
                    select(FantasyScores)
                    .where(
                        FantasyScores.league_id == league.league_id,
                        FantasyScores.week == week,
                    )
                    .order_by(FantasyScores.weekly_score.desc())
                )
                scoresToRank = rank_result.scalars().all()

                # Special case: If this is States, lock the top 3 teams from previous weeks
                if states:
                    # Calculate cumulative scores up to the current week for the States
                    cumulativeScores = {}
                    for fantasyTeam in fantasyTeams:
                        cumul_result = await session.execute(
                            select(FantasyScores.rank_points).where(
                                FantasyScores.fantasy_team_id
                                == fantasyTeam.fantasy_team_id,
                                FantasyScores.week < week,
                            )
                        )
                        total_score = cumul_result.all()
                        cumulativeScores[fantasyTeam.fantasy_team_id] = sum(
                            score[0] for score in total_score
                        )

                    # Get the top 3 teams based on cumulative scores
                    lockedTop3 = sorted(
                        cumulativeScores.items(), key=lambda x: x[1], reverse=True
                    )[:3]
                    lockedTop3TeamIds = [team_id for team_id, _ in lockedTop3]

                    # Ensure the top 3 are locked in their positions for this week
                    locked_result = await session.execute(
                        select(FantasyScores).where(
                            FantasyScores.fantasy_team_id.in_(lockedTop3TeamIds),
                            FantasyScores.week == week,
                        )
                    )
                    lockedTeamsRanked = locked_result.scalars().all()

                    # Assign rank points manually for locked top 3
                    for i, teamscore in enumerate(lockedTeamsRanked):
                        teamscore.rank_points = (
                            100 - i * 25
                        )  # Assign rank points from the top

                    # Remove the top 3 from the scoresToRank, leaving the rest to be ranked normally
                    scoresToRank = [
                        score
                        for score in scoresToRank
                        if score.fantasy_team_id not in lockedTop3TeamIds
                    ]

                    # Normal ranking for the rest of the teams
                    for i, teamscore in enumerate(scoresToRank):
                        rank = (
                            i + len(lockedTop3TeamIds) + 1
                        )  # Start rank after the locked top 3
                        # Check for ties
                        if (
                            i > 0
                            and teamscore.weekly_score
                            == scoresToRank[i - 1].weekly_score
                        ):
                            teamscore.rank_points = scoresToRank[
                                i - 1
                            ].rank_points  # Same rank as the previous team
                        else:
                            teamscore.rank_points = len(fantasyTeams) - rank
                else:
                    # Normal ranking for non-states weeks
                    for i, teamscore in enumerate(scoresToRank):
                        rank = i + 1  # Rank starting from 1
                        # Check for ties
                        if (
                            i > 0
                            and teamscore.weekly_score
                            == scoresToRank[i - 1].weekly_score
                        ):
                            teamscore.rank_points = scoresToRank[
                                i - 1
                            ].rank_points  # Same rank as the previous team
                        else:
                            teamscore.rank_points = len(fantasyTeams) - rank

                    await session.flush()

                await session.commit()

            await message.edit(
                content=f"Updated all scores for {year} week {week}, {'with states rules applied' if states else ''}"
            )

    async def scoreSingleDraft(self, interaction: discord.Interaction, draft_id: int):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            draft_result = await session.execute(
                select(Draft).where(Draft.draft_id == draft_id)
            )
            draft: Draft = draft_result.scalars().first()
            league_result = await session.execute(
                select(League).where(League.league_id == draft.league_id)
            )
            league: League = league_result.scalars().first()
            event_result = await session.execute(
                select(FRCEvent).where(FRCEvent.event_key == draft.event_key)
            )
            frcEvent: FRCEvent = event_result.scalars().first()
            if league:
                teams_result = await session.execute(
                    select(FantasyTeam).where(FantasyTeam.league_id == league.league_id)
                )
                fantasyTeams = teams_result.scalars().all()
                # Calculate scores for each fantasy team
                for fantasyTeam in fantasyTeams:
                    score_result = await session.execute(
                        select(FantasyScores).where(
                            FantasyScores.fantasy_team_id
                            == fantasyTeam.fantasy_team_id,
                            FantasyScores.week == frcEvent.week,
                        )
                    )
                    teamscore = score_result.scalars().first()
                    if not teamscore:
                        teamscore = FantasyScores(
                            league_id=league.league_id,
                            fantasy_team_id=fantasyTeam.fantasy_team_id,
                            event_key=frcEvent.event_key,
                            week=frcEvent.week,
                            rank_points=0,
                            weekly_score=0,
                        )
                        session.add(teamscore)
                        await session.flush()
                    picks_result = await session.execute(
                        select(DraftPick).where(
                            DraftPick.fantasy_team_id == fantasyTeam.fantasy_team_id,
                            DraftPick.draft_id == draft.draft_id,
                        )
                    )
                    draftPicks = picks_result.scalars().all()
                    # Calculate weekly score based on team starts
                    weekly_score = 0
                    for pick in draftPicks:
                        if frcEvent.week in [
                            6,
                            7,
                            8,
                            9,
                        ]:  # future proofing for future champs week shifting
                            # States+Champs Weeks: Count all points across all events the team competes in
                            team_scores_result = await session.execute(
                                select(TeamScore)
                                .join(League)
                                .where(
                                    TeamScore.team_key == pick.team_number,
                                    League.year == league.year,
                                )
                            )
                            team_scores = team_scores_result.scalars().all()
                        else:
                            # Non-States: Only include points for the specific event
                            team_scores_result = await session.execute(
                                select(TeamScore).where(
                                    TeamScore.team_key == pick.team_number,
                                    TeamScore.event_key == draft.event_key,
                                )
                            )
                            team_scores = team_scores_result.scalars().all()
                        # Sum up the scores for this team
                        for score in team_scores:
                            weekly_score += score.score_team()
                    teamscore.weekly_score = weekly_score
                    await session.flush()
                # Retrieve all scores for the league in the current week
                rank_result = await session.execute(
                    select(FantasyScores)
                    .where(FantasyScores.league_id == league.league_id)
                    .order_by(FantasyScores.weekly_score.desc())
                )
                scoresToRank = rank_result.scalars().all()
                for i, teamscore in enumerate(scoresToRank):
                    rank = i + 1  # Rank starting from 1
                    # Check for ties
                    if (
                        i > 0
                        and teamscore.weekly_score == scoresToRank[i - 1].weekly_score
                    ):
                        teamscore.rank_points = scoresToRank[
                            i - 1
                        ].rank_points  # Same rank as the previous team
                    else:
                        teamscore.rank_points = len(fantasyTeams) - rank
                await session.flush()

            await session.commit()
            await message.edit(content=f"Updated all scores for {frcEvent.event_key}")

    async def notifyWeeklyScoresTask(
        self, interaction: discord.Interaction, year, week
    ):
        async with self.bot.async_session() as session:
            week_result = await session.execute(
                select(WeekStatus).where(
                    WeekStatus.year == year, WeekStatus.week == week
                )
            )
            week_status = week_result.scalars().first()
            if not week_status:
                await interaction.followup.send(
                    f"No status found for year {year}, week {week}."
                )
                return
            leagues_result = await session.execute(
                select(League).where(League.is_fim, League.active)
            )
            leagues = leagues_result.scalars().all()
            for league in leagues:
                scores_result = await session.execute(
                    select(FantasyScores)
                    .where(
                        FantasyScores.league_id == league.league_id,
                        FantasyScores.week == week,
                    )
                    .order_by(FantasyScores.rank_points.desc())
                )
                teams = scores_result.scalars().all()
                if not teams:
                    continue
                if week_status.scores_finalized:
                    title = f"Week {week} Final Scores for {league.league_name}"
                else:
                    title = f"Week {week} Unofficial Scores for {league.league_name}"
                embed = Embed(
                    title=title,
                    description=f"Here are the {'official' if week_status.scores_finalized else 'unofficial'} scores for Week {week}",
                )
                for idx, team_score in enumerate(teams):
                    fantasy_team = team_score.fantasyTeam
                    embed.add_field(
                        name=f"{idx + 1}. {fantasy_team.fantasy_team_name}",
                        value=f"Score: {team_score.weekly_score} points",
                        inline=False,
                    )
                if week_status.scores_finalized:
                    winning_team = teams[0].fantasyTeam
                    winning_score = teams[0].weekly_score
                    players_result = await session.execute(
                        select(PlayerAuthorized).where(
                            PlayerAuthorized.fantasy_team_id
                            == winning_team.fantasy_team_id
                        )
                    )
                    playersToNotify = players_result.scalars().all()
                    congrats_message = f"**Congratulations to {winning_team.fantasy_team_name} for winning this week with {winning_score} points!**\n"
                    for player in playersToNotify:
                        congrats_message += f"<@{player.player_id}> "

                else:
                    congrats_message = f"Unofficial scores for Week {week}. Check back later for final results!"
                channel = self.bot.get_channel(int(league.discord_channel))
                await channel.send(content=congrats_message, embed=embed)
            await interaction.followup.send(
                f"Weekly scores for Week {week} have been sent to all active leagues."
            )

    async def notifySingleDraftTask(self, interaction: discord.Interaction, draft_id):
        async with self.bot.async_session() as session:
            await interaction.original_response()
            draft_result = await session.execute(
                select(Draft).where(Draft.draft_id == draft_id)
            )
            draft: Draft = draft_result.scalars().first()
            league_result = await session.execute(
                select(League).where(League.league_id == draft.league_id)
            )
            league: League = league_result.scalars().first()
            event_result = await session.execute(
                select(FRCEvent).where(FRCEvent.event_key == draft.event_key)
            )
            frcEvent: FRCEvent = event_result.scalars().first()
            if league:
                scores_result = await session.execute(
                    select(FantasyScores)
                    .where(
                        FantasyScores.league_id == league.league_id,
                        FantasyScores.event_key == frcEvent.event_key,
                    )
                    .order_by(FantasyScores.weekly_score.desc())
                )
                teams = scores_result.scalars().all()
                title = f"Final Scores for {frcEvent.event_name}"
                embed = Embed(
                    title=title,
                    description=f"Here are the official scores for {frcEvent.event_name}",
                )
                for idx, team_score in enumerate(teams):
                    fantasy_team = team_score.fantasyTeam
                    embed.add_field(
                        name=f"{idx + 1}. {fantasy_team.fantasy_team_name}",
                        value=f"Score: {team_score.weekly_score} points",
                        inline=False,
                    )
                winning_team = teams[0].fantasyTeam
                winning_score = teams[0].weekly_score
                players_result = await session.execute(
                    select(PlayerAuthorized).where(
                        PlayerAuthorized.fantasy_team_id == winning_team.fantasy_team_id
                    )
                )
                playersToNotify = players_result.scalars().all()
                congrats_message = f"**Congratulations to {winning_team.fantasy_team_name} for winning this draft with {winning_score} points!**\n"
                for player in playersToNotify:
                    congrats_message += f"<@{player.player_id}> "
                channel = self.bot.get_channel(int(league.discord_channel))
                await channel.send(content=congrats_message, embed=embed)

    async def getLeagueStandingsTask(
        self, interaction: discord.Interaction, year, week
    ):
        async with self.bot.async_session() as session:
            # Query for the week status to check if scores are finalized
            week_result = await session.execute(
                select(WeekStatus).where(
                    WeekStatus.year == year, WeekStatus.week == week
                )
            )
            week_status = week_result.scalars().first()

            if not week_status:
                await interaction.followup.send(
                    f"No status found for week {week} in year {year}."
                )
                return

            leagues_result = await session.execute(
                select(League).where(League.is_fim, League.active)
            )
            leagues = leagues_result.scalars().all()

            for league in leagues:
                # Retrieve all fantasy teams in the league
                teams_result = await session.execute(
                    select(FantasyTeam).where(FantasyTeam.league_id == league.league_id)
                )
                fantasy_teams = teams_result.scalars().all()

                standings = []
                for fantasy_team in fantasy_teams:
                    # Get scores up to the specified week
                    scores_result = await session.execute(
                        select(FantasyScores).where(
                            FantasyScores.fantasy_team_id
                            == fantasy_team.fantasy_team_id,
                            FantasyScores.week <= week,
                        )
                    )
                    scores = scores_result.scalars().all()

                    # Calculate total score and tiebreaker
                    total_score = sum(
                        score.rank_points for score in scores
                    )  # Total score based on rank points
                    tiebreaker = sum(
                        score.weekly_score for score in scores
                    )  # Tiebreaker based on weekly score

                    standings.append(
                        {
                            "team_name": fantasy_team.fantasy_team_name,
                            "total_score": total_score,
                            "tiebreaker": tiebreaker,
                        }
                    )

                # Sort standings first by total score, then by tiebreaker
                standings.sort(key=lambda x: (-x["total_score"], -x["tiebreaker"]))

                # Prepare embed
                if week_status.scores_finalized:
                    title = f"League Standings up to Week {week} for {league.league_name} ({year})"
                else:
                    title = f"Unofficial League Standings up to Week {week} for {league.league_name} ({year})"

                embed = Embed(
                    title=title, description="Here are the current standings:"
                )

                for idx, standing in enumerate(standings):
                    embed.add_field(
                        name=f"{idx + 1}. {standing['team_name']}",
                        value=f"Ranking Points: {standing['total_score']} | Tiebreaker (Total Score): {standing['tiebreaker']}",
                        inline=False,
                    )

                # Send the standings embed to the Discord channel
                channel = self.bot.get_channel(int(league.discord_channel))
                await channel.send(embed=embed)

            # Notify the user who triggered the command that the task is complete
            await interaction.followup.send(
                f"League standings for {year} up to week {week} have been sent to all active leagues."
            )

    async def addTeamsToEventTask(
        self, interaction: discord.Interaction, teams: str, draft: Draft
    ):
        async with self.bot.async_session() as session:
            # Step 1: Retrieve the associated FRCEvent from the draft object
            event_result = await session.execute(
                select(FRCEvent).where(FRCEvent.event_key == draft.event_key)
            )
            event = event_result.scalars().first()
            if not event:
                await interaction.followup.send(
                    f"Event with key {draft.event_key} not found."
                )
                return
            # Step 2: Split the team list (supports comma, space, or mixed separators)
            import re

            team_numbers = [
                team.strip() for team in re.split(r"[,\s]+", teams) if team.strip()
            ]
            # Step 3: Iterate through each team and create Team objects if they don't exist
            for team_number in team_numbers:
                team_result = await session.execute(
                    select(Team).where(Team.team_number == team_number)
                )
                team = team_result.scalars().first()
                if not team:
                    # Create a new Team object
                    team = Team(
                        team_number=team_number, name="Offseason Team", rookie_year=1992
                    )
                    session.add(team)
            # Step 4: Flush the session to insert Team objects and generate primary keys
            await session.flush()
            # Step 5: Create TeamScore objects for the event
            for team_number in team_numbers:
                team_score = TeamScore(team_key=team_number, event_key=event.event_key)
                session.add(team_score)
            # Step 6: Commit the changes
            await session.commit()
            await interaction.followup.send(
                f"Teams added to event {event.event_name} successfully."
            )

    async def reassignBTeamTask(
        self,
        interaction: discord.Interaction,
        originalBTeam: str,
        newBTeamNumber: str,
        draft: Draft,
    ):
        async with self.bot.async_session() as session:
            try:
                # Step 1: Check if the draft and the originalBTeam exist in the current draft
                score_result = await session.execute(
                    select(TeamScore).where(
                        TeamScore.team_key == originalBTeam,
                        TeamScore.event_key == draft.event_key,
                    )
                )
                team_score = score_result.scalars().first()

                pick_result = await session.execute(
                    select(DraftPick).where(
                        DraftPick.team_number == originalBTeam,
                        DraftPick.draft_id == draft.draft_id,
                    )
                )
                draft_pick = pick_result.scalars().first()

                # If neither TeamScore nor DraftPick exist, notify the user
                if not team_score or not draft_pick:
                    await interaction.followup.send(
                        f"Could not find team '{originalBTeam}' in this draft."
                    )
                    return

                # Step 2: Check if the newBTeam exists
                new_team_result = await session.execute(
                    select(Team).where(Team.team_number == newBTeamNumber)
                )
                new_team = new_team_result.scalars().first()

                if not new_team:
                    # Create the new Team object
                    new_team = Team(
                        team_number=newBTeamNumber,
                        name="Offseason Team",
                        rookie_year=1992,
                    )
                    session.add(new_team)

                    # Flush to ensure the new team is added to the session and available for foreign key references
                    await session.flush()

                # Check if a TeamScore already exists for the new team
                existing_score_result = await session.execute(
                    select(TeamScore).where(
                        TeamScore.team_key == newBTeamNumber,
                        TeamScore.event_key == draft.event_key,
                    )
                )
                existing_team_score = existing_score_result.scalars().first()

                if existing_team_score:
                    await interaction.followup.send(
                        f"A TeamScore already exists for team '{newBTeamNumber}'."
                    )
                    return

                # Step 3: Update the TeamScore and DraftPick to reflect the new team
                team_score.team_key = newBTeamNumber
                draft_pick.team_number = newBTeamNumber

                # Step 4: Commit changes
                await session.commit()

                # Step 5: Send success message
                await interaction.followup.send(
                    f"Successfully reassigned team '{originalBTeam}' to '{newBTeamNumber}'."
                )

            except Exception as e:
                await interaction.followup.send(
                    "An error occurred while reassigning the team. Please check the logs for more details."
                )
                print(e)  # Print the stack trace or log it appropriately

    async def moveOffseasonTeamTask(
        self, interaction: discord.Interaction, fantasy_team_id: int, new_league_id: int
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()

            team_result = await session.execute(
                select(FantasyTeam).where(
                    FantasyTeam.fantasy_team_id == fantasy_team_id
                )
            )
            fantasy_team: FantasyTeam | None = team_result.scalars().first()
            if not fantasy_team:
                await message.edit(content=f"Fantasy team {fantasy_team_id} not found")
                return

            old_league_result = await session.execute(
                select(League).where(League.league_id == fantasy_team.league_id)
            )
            old_league: League = old_league_result.scalars().first()
            new_league_result = await session.execute(
                select(League).where(League.league_id == new_league_id)
            )
            new_league: League | None = new_league_result.scalars().first()

            if not new_league:
                await message.edit(content=f"League {new_league_id} not found")
                return

            if not old_league.offseason or not new_league.offseason:
                await message.edit(content="Both leagues must be offseason leagues")
                return

            count_result = await session.execute(
                select(FantasyTeam).where(FantasyTeam.league_id == new_league_id)
            )
            team_count = len(count_result.scalars().all())
            if team_count >= new_league.team_limit:
                await message.edit(
                    content=f"League {new_league.league_name} is at capacity"
                )
                return

            fantasy_team.league_id = new_league_id
            await session.execute(
                update(TeamOwned)
                .where(TeamOwned.fantasy_team_id == fantasy_team_id)
                .values(league_id=new_league_id)
            )
            await session.execute(
                update(TeamStarted)
                .where(TeamStarted.fantasy_team_id == fantasy_team_id)
                .values(league_id=new_league_id)
            )
            await session.execute(
                update(WaiverPriority)
                .where(WaiverPriority.fantasy_team_id == fantasy_team_id)
                .values(league_id=new_league_id)
            )

            await session.commit()
            await message.edit(
                content=f"Moved team {fantasy_team_id} from {old_league.league_name} to {new_league.league_name}"
            )

    async def setStatCorrectionTask(
        self,
        interaction: discord.Interaction,
        team_number: str,
        event_key: str,
        correction: int,
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            score_result = await session.execute(
                select(TeamScore).where(
                    TeamScore.team_key == team_number, TeamScore.event_key == event_key
                )
            )
            team_score = score_result.scalars().first()
            if not team_score:
                await message.edit(
                    content=f"TeamScore for {team_number} at {event_key} not found"
                )
            else:
                team_score.stat_correction = correction
                await session.commit()
                await message.edit(
                    content=f"Stat correction for {team_number} at {event_key} set to {correction}"
                )

    async def resetStatCorrectionTask(
        self, interaction: discord.Interaction, team_number: str, event_key: str
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            score_result = await session.execute(
                select(TeamScore).where(
                    TeamScore.team_key == team_number, TeamScore.event_key == event_key
                )
            )
            team_score = score_result.scalars().first()
            if not team_score:
                await message.edit(
                    content=f"TeamScore for {team_number} at {event_key} not found"
                )
            else:
                team_score.stat_correction = 0
                await session.commit()
                await message.edit(
                    content=f"Stat correction for {team_number} at {event_key} reset"
                )

    async def verifyAdmin(self, interaction: discord.Interaction):
        async with self.bot.async_session() as session:
            admin_result = await session.execute(
                select(Player).where(
                    Player.user_id == str(interaction.user.id), Player.is_admin
                )
            )
            isAdmin = admin_result.scalars().first()
            if not isAdmin:
                await interaction.response.send_message(
                    "You are not authorized to use this command."
                )
                return False
            else:
                return True

    async def getForum(self):
        return self.bot.get_channel(int(FORUM_CHANNEL_ID))

    async def getLeagueId(self):  # league id generation for primary key
        async with self.bot.async_session() as session:
            result = await session.execute(
                select(League).order_by(League.league_id.desc())
            )
            maxleague = result.scalars().first()
            if maxleague is not None:
                return maxleague.league_id + 1
            else:
                return 1

    async def getFantasyTeamId(self):  # fantasy team id generation for primary key
        async with self.bot.async_session() as session:
            result = await session.execute(
                select(FantasyTeam).order_by(FantasyTeam.fantasy_team_id.desc())
            )
            maxFantasyTeam = result.scalars().first()
            if maxFantasyTeam is not None:
                return maxFantasyTeam.fantasy_team_id + 1
            else:
                return 1

    async def getDraftId(self):  # draft id generation for primary key
        async with self.bot.async_session() as session:
            result = await session.execute(
                select(Draft).order_by(Draft.draft_id.desc())
            )
            maxDraft = result.scalars().first()
            if maxDraft is not None:
                return maxDraft.draft_id + 1
            else:
                return 1

    async def getFantasyTeamIdFromUserAndInteraction(
        self, interaction: discord.Interaction, user: discord.User
    ):
        async with self.bot.async_session() as session:
            result = await session.execute(
                select(FantasyTeam)
                .join(
                    PlayerAuthorized,
                    FantasyTeam.fantasy_team_id == PlayerAuthorized.fantasy_team_id,
                )
                .join(League, FantasyTeam.league_id == League.league_id)
                .where(PlayerAuthorized.player_id == str(user.id))
                .where(League.discord_channel == str(interaction.channel_id))
            )
            team = result.scalars().first()
            if team:
                return team.fantasy_team_id
            else:
                return None

    @app_commands.command(
        name="updateteamlist", description="Grabs all teams from TBA (ADMIN)"
    )
    async def updateTeamList(
        self, interaction: discord.Interaction, startpage: int = 0
    ):
        if await self.verifyAdmin(interaction):
            asyncio.create_task(self.updateTeamsTask(interaction, startpage))

    @app_commands.command(name="addleague", description="Create a new league (ADMIN)")
    async def createLeague(
        self,
        interaction: discord.Interaction,
        league_name: str,
        team_limit: int,
        year: int,
        is_fim: bool = False,
        team_starts: int = 3,
        team_size_limit: int = 3,
    ):
        if await self.verifyAdmin(interaction):
            forum = await self.getForum()
            threadName = f"{league_name} Thread"
            thread = (
                await forum.create_thread(
                    content=f"This is your league thread for {league_name}",
                    name=threadName,
                )
            )[0]
            threadId = thread.id
            newLeagueId = await self.getLeagueId()
            leagueToAdd = League(
                league_id=newLeagueId,
                league_name=league_name,
                team_limit=team_limit,
                team_starts=team_starts,
                offseason=False,
                is_fim=is_fim,
                year=year,
                discord_channel=str(threadId),
                team_size_limit=team_size_limit,
            )
            async with self.bot.async_session() as session:
                session.add(leagueToAdd)
                await session.commit()
            await interaction.response.send_message(
                f"League created successfully! <#{threadId}>"
            )

    @app_commands.command(
        name="createoffseason", description="Create a new offseason 'league' (ADMIN)"
    )
    async def createOffseasonLeague(
        self,
        interaction: discord.Interaction,
        league_name: str,
        year: int,
        teams_to_draft: int = 3,
    ):
        if await self.verifyAdmin(interaction):
            forum = await self.getForum()
            threadName = f"{league_name} Thread"
            thread = (
                await forum.create_thread(
                    content=f"This is your league thread for {league_name}",
                    name=threadName,
                )
            )[0]
            threadId = thread.id
            newLeagueId = await self.getLeagueId()
            leagueToAdd = League(
                league_id=newLeagueId,
                league_name=league_name,
                team_limit=100,
                team_starts=teams_to_draft,
                offseason=True,
                is_fim=False,
                year=year,
                discord_channel=str(threadId),
                team_size_limit=teams_to_draft,
            )
            async with self.bot.async_session() as session:
                session.add(leagueToAdd)
                await session.commit()
            await interaction.response.send_message(
                f"League created successfully! <#{threadId}>"
            )

    @app_commands.command(
        name="createevent",
        description="Create an offseason event, only do if offseason + event isn't on TBA (ADMIN)",
    )
    async def createOffseasonEvent(
        self, interaction: discord.Interaction, eventkey: str, eventname: str, year: int
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to create event {eventkey}"
            )
            await self.createOffseasonEventTask(interaction, eventkey, eventname, year)

    @app_commands.command(
        name="registerteam", description="Register Fantasy Team (ADMIN)"
    )
    async def registerTeam(self, interaction: discord.Interaction, teamname: str):
        if await self.verifyAdmin(interaction):
            async with self.bot.async_session() as session:
                leagues_result = await session.execute(
                    select(League).where(
                        League.discord_channel == str(interaction.channel_id)
                    )
                )
                leagues = leagues_result.scalars().all()
                if len(leagues) == 0:
                    await interaction.response.send_message(
                        "No leagues exist in this channel."
                    )
                    return
                leagueid = leagues[0].league_id
                teams_result = await session.execute(
                    select(FantasyTeam).where(FantasyTeam.league_id == leagueid)
                )
                teamsInLeague = teams_result.scalars().all()
                if leagues[0].team_limit <= len(teamsInLeague):
                    await interaction.response.send_message(
                        f"League with id {leagueid} is at max capacity."
                    )
                    return
                newTeamId = await self.getFantasyTeamId()
                fantasyTeamToAdd = FantasyTeam(
                    fantasy_team_id=newTeamId,
                    fantasy_team_name=teamname,
                    league_id=leagueid,
                )
                session.add(fantasyTeamToAdd)
                await session.commit()
                await interaction.response.send_message(
                    f"Team {teamname} created successfully in league with id {leagueid}. Team id is {fantasyTeamToAdd.fantasy_team_id}"
                )

    @app_commands.command(
        name="fillleague",
        description="Populates a League to the max amount of teams with generic teams (ADMIN)",
    )
    async def populateLeague(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            async with self.bot.async_session() as session:
                leagues_result = await session.execute(
                    select(League).where(
                        League.discord_channel == str(interaction.channel_id)
                    )
                )
                leagues = leagues_result.scalars().all()
                if len(leagues) == 0:
                    await interaction.response.send_message(
                        "No league exists in this channel."
                    )
                    return
                leagueid = leagues[0].league_id
                teams_result = await session.execute(
                    select(FantasyTeam).where(FantasyTeam.league_id == leagueid)
                )
                teamsInLeague = teams_result.scalars().all()
                teamLimit = leagues[0].team_limit
                if teamLimit <= len(teamsInLeague):
                    await interaction.response.send_message(
                        "League is at max capacity."
                    )
                    return
                while teamLimit > len(teamsInLeague):
                    newTeamId = await self.getFantasyTeamId()
                    fantasyTeamToAdd = FantasyTeam(
                        fantasy_team_id=newTeamId,
                        fantasy_team_name=f"Team {newTeamId}",
                        league_id=leagueid,
                    )
                    session.add(fantasyTeamToAdd)
                    await session.commit()
                    teams_result = await session.execute(
                        select(FantasyTeam).where(FantasyTeam.league_id == leagueid)
                    )
                    teamsInLeague = teams_result.scalars().all()
                await interaction.response.send_message("Teams created successfully!.")

    @app_commands.command(
        name="createdraft",
        description="Creates a fantasy draft for a given League and populates it with picks (ADMIN)",
    )
    async def createDraft(self, interaction: discord.Interaction, event_key: str):
        if await self.verifyAdmin(interaction):
            async with self.bot.async_session() as session:
                leagues_result = await session.execute(
                    select(League).where(
                        League.discord_channel == str(interaction.channel_id),
                        League.active,
                    )
                )
                leagues = leagues_result.scalars().all()
                if len(leagues) == 0:
                    await interaction.response.send_message(
                        "No active leagues exist in current channel."
                    )
                    return
                # Verify event exists
                event_result = await session.execute(
                    select(FRCEvent).where(FRCEvent.event_key == event_key)
                )
                event = event_result.scalars().first()
                if not event:
                    await interaction.response.send_message(
                        f"Event with key `{event_key}` not found. Please create the event first."
                    )
                    return
                rounds = leagues[0].team_size_limit
                leagueid = leagues[0].league_id
                teams_result = await session.execute(
                    select(FantasyTeam).where(FantasyTeam.league_id == leagueid)
                )
                teamsInLeague = teams_result.scalars().all()
                if len(teamsInLeague) == 0:
                    await interaction.response.send_message(
                        "Cannot create draft with no teams to draft"
                    )
                    return
                if leagues[0].team_starts > rounds:
                    await interaction.response.send_message(
                        "Don't have enough rounds to draft!"
                    )
                    return
                forum = await self.getForum()
                nameOfDraft = f"{leagues[0].league_name} draft for {event_key}"
                thread = (
                    await forum.create_thread(
                        content=f"{leagues[0].league_name} draft for {event_key}",
                        name=nameOfDraft,
                    )
                )[0]
                threadId = thread.id
                newDraftId = await self.getDraftId()
                draftToCreate = Draft(
                    draft_id=newDraftId,
                    league_id=leagueid,
                    rounds=rounds,
                    event_key=event_key,
                    discord_channel=str(threadId),
                )
                session.add(draftToCreate)
                await session.commit()
                await interaction.response.send_message(
                    f"Draft generated! <#{threadId}>"
                )
                # generate draft order
                draftOrderEmbed = Embed(
                    title="**Draft order**",
                    description="```Draft Slot    Team Name (id)\n",
                )
                randomizedteams = [
                    fantasyTeam.fantasy_team_id for fantasyTeam in teamsInLeague
                ]
                random.shuffle(randomizedteams)
                i = 1
                for team_id in randomizedteams:
                    draftOrder = DraftOrder(
                        draft_id=draftToCreate.draft_id,
                        draft_slot=i,
                        fantasy_team_id=team_id,
                    )
                    teamname = next(
                        (
                            t.fantasy_team_name
                            for t in teamsInLeague
                            if t.fantasy_team_id == team_id
                        ),
                        "Unknown",
                    )
                    draftOrderEmbed.description += (
                        f"{i:>10d}    {teamname} ({team_id})\n"
                    )
                    session.add(draftOrder)
                    i += 1
                draftOrderEmbed.description += "```"
                await thread.send(embed=draftOrderEmbed)
                await session.commit()

    @app_commands.command(
        name="startdraft", description="Starts the draft in the current channel (ADMIN)"
    )
    async def startDraft(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            async with self.bot.async_session() as session:
                drafts_result = await session.execute(
                    select(Draft).where(
                        Draft.discord_channel == str(interaction.channel_id)
                    )
                )
                drafts = drafts_result.scalars().all()
                if len(drafts) == 0:
                    await interaction.response.send_message(
                        "This is not an active draft channel."
                    )
                    return
                await interaction.response.send_message("Generating draft picks")
                message = await interaction.original_response()
                draftid = drafts[0].draft_id
                orders_result = await session.execute(
                    select(DraftOrder).where(DraftOrder.draft_id == draftid)
                )
                draftOrders = orders_result.scalars().all()
                if len(draftOrders) == 0:
                    await message.edit(content="Error generating draft picks.")
                    return
                for teamDraftOrder in draftOrders:
                    for k in range(drafts[0].rounds):
                        pickNumber = k * len(draftOrders)
                        if k % 2 == 0:  # handle serpentine
                            pickNumber += teamDraftOrder.draft_slot
                        else:
                            pickNumber += (
                                len(draftOrders) - teamDraftOrder.draft_slot
                            ) + 1
                        draftPickToAdd = DraftPick(
                            draft_id=draftid,
                            fantasy_team_id=teamDraftOrder.fantasy_team_id,
                            pick_number=pickNumber,
                            team_number="-1",
                        )
                        session.add(draftPickToAdd)
                await session.commit()
                await message.edit(content="Draft rounds generated!")
            draftCog = drafting.Drafting(self.bot)
            await draftCog.postDraftBoard(interaction=interaction)
            await draftCog.notifyNextPick(interaction, draft_id=draftid)

    @app_commands.command(
        name="resetdraft", description="Resets an already started draft. (ADMIN)"
    )
    async def resetDraft(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            async with self.bot.async_session() as session:
                drafts_result = await session.execute(
                    select(Draft).where(
                        Draft.discord_channel == str(interaction.channel_id)
                    )
                )
                drafts = drafts_result.scalars().all()
                if len(drafts) == 0:
                    await interaction.response.send_message(
                        "This is not a draft channel."
                    )
                    return
                draftid = drafts[0].draft_id
                await session.execute(
                    delete(DraftPick).where(DraftPick.draft_id == draftid)
                )
                await session.commit()
            await interaction.response.send_message(
                "Successfully reset draft! Use command /startdraft to restart the draft."
            )

    @app_commands.command(
        name="updateevents", description="Update events for a given year (ADMIN)"
    )
    async def updateEvents(self, interaction: discord.Interaction, year: int):
        if await self.verifyAdmin(interaction):
            asyncio.create_task(self.updateEventsTask(interaction, year))

    @app_commands.command(
        name="importoffseasonevent",
        description="Imports offseason event and team list from TBA (ADMIN)",
    )
    async def importOffseasonEvent(
        self, interaction: discord.Interaction, eventkey: str
    ):
        if await self.verifyAdmin(interaction):
            asyncio.create_task(self.importSingleEventTask(interaction, eventkey))

    @app_commands.command(
        name="importdistrict",
        description="Pull all registration data for district events and load db (ADMIN)",
    )
    async def importDistrict(
        self, interaction: discord.Interaction, year: str, district: str = "fim"
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Force updating district {district}"
            )
            asyncio.create_task(self.importFullDistrctTask(year, district))

    @app_commands.command(
        name="scoreupdate",
        description="Generate a score update for the given week (ADMIN)",
    )
    async def updateScores(
        self,
        interaction: discord.Interaction,
        year: int,
        week: int,
        final: bool = False,
        states: bool = False,
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Scoring all leagues for {year} week {week}"
            )
            await self.scoreWeekTask(interaction, year, week)
            await self.scoreAllLeaguesTask(interaction, year, week, states=states)
            if final:
                async with self.bot.async_session() as session:
                    weekToMod_result = await session.execute(
                        select(WeekStatus).where(
                            WeekStatus.year == year, WeekStatus.week == week
                        )
                    )
                    weekToMod = weekToMod_result.scalars().first()
                    weekToMod.scores_finalized = True
                    await session.commit()
            await self.notifyWeeklyScoresTask(interaction, year, week)
            await self.getLeagueStandingsTask(interaction, year, week)

    @app_commands.command(
        name="authorize", description="Add an authorized user to a fantasy team (ADMIN)"
    )
    async def authorizeUser(
        self, interaction: discord.Interaction, fantasyteamid: int, user: discord.User
    ):
        if await self.verifyAdmin(interaction):
            async with self.bot.async_session() as session:
                player_result = await session.execute(
                    select(Player).where(Player.user_id == str(user.id))
                )
                player = player_result.scalars().first()
                if player is None:
                    session.add(Player(user_id=str(user.id), is_admin=False))
                    await session.commit()
                if not (await self.bot.verifyTeamMemberByTeamId(fantasyteamid, user)):
                    authorizeToAdd = PlayerAuthorized(
                        fantasy_team_id=fantasyteamid, player_id=str(user.id)
                    )
                    session.add(authorizeToAdd)
                    await session.commit()
                    fantasyTeam_result = await session.execute(
                        select(FantasyTeam).where(
                            FantasyTeam.fantasy_team_id == fantasyteamid
                        )
                    )
                    fantasyTeam = fantasyTeam_result.scalars().first()
                    await interaction.response.send_message(
                        f"Successfully added <@{user.id}> to {fantasyTeam.fantasy_team_name}!",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "You can't add someone already on it to their own team dummy!",
                        ephemeral=True,
                    )

    @app_commands.command(
        name="forcepick", description="Admin ability to force a draft pick (ADMIN)"
    )
    async def forceDraftPick(self, interaction: discord.Interaction, team_number: str):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to force pick team {team_number}."
            )
            draftCog = drafting.Drafting(self.bot)
            await draftCog.makeDraftPickHandler(
                interaction=interaction, team_number=team_number, force=True
            )

    @app_commands.command(
        name="autopick", description="Admin ability to force an auto draft pick (ADMIN)"
    )
    async def forceAutoPick(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                "Attempting to force pick best available team."
            )
            draftCog = drafting.Drafting(self.bot)
            draft: Draft = await draftCog.getDraftFromChannel(interaction=interaction)
            if draft is None:
                await interaction.channel.send(
                    content="No draft associated with this channel."
                )
                return
            league: League = await draftCog.getLeague(draft_id=draft.draft_id)
            suggestedTeams = await draftCog.getSuggestedTeamsList(
                eventKey=draft.event_key,
                year=league.year,
                isFiM=league.is_fim,
                draft_id=draft.draft_id,
                isOffseason=league.offseason,
            )
            teamToPick = suggestedTeams[0][0]
            await draftCog.makeDraftPickHandler(
                interaction=interaction, team_number=teamToPick, force=True
            )

    @app_commands.command(
        name="statboticsupdate", description="Updates cache of Statbotics data (ADMIN)"
    )
    async def updateStatbotics(self, interaction: discord.Interaction, year: int):
        if await self.verifyAdmin(interaction):
            asyncio.create_task(self.updateStatboticsTask(interaction, year))

    @app_commands.command(
        name="deauthplayer", description="Remove a player from a team (ADMIN)"
    )
    async def deauthPlayer(self, interaction: discord.Interaction, user: discord.User):
        if await self.verifyAdmin(interaction):
            if not await self.bot.verifyNotInLeague(interaction, user):
                fantasyId = await self.getFantasyTeamIdFromUserAndInteraction(
                    interaction, user
                )
                async with self.bot.async_session() as session:
                    await session.execute(
                        delete(PlayerAuthorized).where(
                            PlayerAuthorized.player_id == str(user.id),
                            PlayerAuthorized.fantasy_team_id == fantasyId,
                        )
                    )
                    await session.commit()
                await interaction.response.send_message(
                    f"Successfully removed <@{user.id}> from league.", ephemeral=True
                )
            else:
                await interaction.response.send_message("Player is not on a team.")

    @app_commands.command(
        name="forcestart",
        description="Admin ability to force a team into a starting lineup (ADMIN)",
    )
    async def forceStart(
        self,
        interaction: discord.Interaction,
        fantasyteamid: int,
        week: int,
        team_number: str,
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to force start team {team_number}."
            )
            manageTeamCog = manageteam.ManageTeam(self.bot)
            await manageTeamCog.startTeamTask(
                interaction, team_number, week, fantasyteamid
            )

    @app_commands.command(
        name="forcesit",
        description="Admin ability to force a team out of a starting lineup (ADMIN)",
    )
    async def forceSit(
        self,
        interaction: discord.Interaction,
        fantasyteamid: int,
        week: int,
        team_number: str,
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to force sit team {team_number}."
            )
            manageTeamCog = manageteam.ManageTeam(self.bot)
            await manageTeamCog.sitTeamTask(
                interaction, team_number, week, fantasyteamid
            )

    @app_commands.command(
        name="viewteamlineup",
        description="Admin ability to view a team's starting lineup (ADMIN)",
    )
    async def viewStartingLineup(
        self, interaction: discord.Interaction, fantasyteamid: int
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to view starting lineup of team {fantasyteamid}."
            )
            manageTeamCog = manageteam.ManageTeam(self.bot)
            await manageTeamCog.viewStartsTask(interaction, fantasyteamid)

    @app_commands.command(
        name="adminrenameteam", description="Admin ability to rename a team (ADMIN)"
    )
    async def renameFantasyTeam(
        self, interaction: discord.Interaction, fantasyteamid: int, newname: str
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to rename team {fantasyteamid} to {newname}."
            )
            manageTeamCog = manageteam.ManageTeam(self.bot)
            await manageTeamCog.renameTeamTask(
                interaction, fantasyId=fantasyteamid, newname=newname
            )

    @app_commands.command(
        name="moveoffseasonteam",
        description="Move a fantasy team to another offseason league (ADMIN)",
    )
    async def moveOffseasonTeam(
        self, interaction: discord.Interaction, fantasyteamid: int, newleagueid: int
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Moving team {fantasyteamid} to league {newleagueid}"
            )
            await self.moveOffseasonTeamTask(interaction, fantasyteamid, newleagueid)

    @app_commands.command(
        name="locklineups",
        description="Admin ability to lock lineups for the week (ADMIN)",
    )
    async def lockLineups(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            currentWeek = await self.bot.getCurrentWeek()
            if currentWeek is None:
                await interaction.response.send_message("No active week")
                return
            async with self.bot.async_session() as session:
                weekToMod_result = await session.execute(
                    select(WeekStatus).where(
                        WeekStatus.year == currentWeek.year,
                        WeekStatus.week == currentWeek.week,
                    )
                )
                weekToMod = weekToMod_result.scalars().first()
                weekToMod.lineups_locked = True
                await session.execute(delete(TradeTeams))
                await session.flush()
                await session.execute(delete(TradeProposal))
                await session.commit()
            await interaction.response.send_message(
                f"Locked lineups for week {currentWeek.week} in {currentWeek.year}"
            )

    @app_commands.command(
        name="finishweek",
        description="Admin ability to deactivate the currently active week (ADMIN)",
    )
    async def finishWeek(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            currentWeek = await self.bot.getCurrentWeek()
            if currentWeek is None:
                await interaction.response.send_message("No active week")
                return
            await interaction.response.defer()
            message = await interaction.original_response()
            await self.put_teams_on_waivers(interaction)
            async with self.bot.async_session() as session:
                weekToMod_result = await session.execute(
                    select(WeekStatus).where(
                        WeekStatus.year == currentWeek.year,
                        WeekStatus.week == currentWeek.week,
                    )
                )
                weekToMod = weekToMod_result.scalars().first()
                weekToMod.active = False
                weekToMod.lock_lineups = True
                await session.commit()
            await message.edit(
                content=f"Deactivated week {currentWeek.week} in {currentWeek.year}"
            )

    @app_commands.command(
        name="remind", description="Remind players to set their lineups (ADMIN)"
    )
    async def remindPlayers(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                "Reminding all users with unfilled lineups to fill them."
            )
            async with self.bot.async_session() as session:
                leagues_result = await session.execute(
                    select(League).where(League.active)
                )
                leagues = leagues_result.scalars().all()
                if len(leagues) == 0:
                    await interaction.channel.send(
                        content="There are no active leagues!"
                    )
                else:
                    for league in leagues:
                        sendReminder = False
                        reminderMessage = "Teams with unfilled lineups:\n"
                        leagueTeams_result = await session.execute(
                            select(FantasyTeam).where(
                                FantasyTeam.league_id == league.league_id
                            )
                        )
                        leagueTeams = leagueTeams_result.scalars().all()
                        for team in leagueTeams:
                            numberOfStarters_result = await session.execute(
                                select(TeamStarted).where(
                                    TeamStarted.fantasy_team_id == team.fantasy_team_id
                                )
                            )
                            numberOfStarters = len(
                                numberOfStarters_result.scalars().all()
                            )
                            if numberOfStarters < league.team_starts:
                                sendReminder = True
                                playersToNotify_result = await session.execute(
                                    select(PlayerAuthorized).where(
                                        PlayerAuthorized.fantasy_team_id
                                        == team.fantasy_team_id
                                    )
                                )
                                playersToNotify = playersToNotify_result.scalars().all()
                                reminderMessage += f"{team.fantasy_team_name} "
                                for player in playersToNotify:
                                    reminderMessage += f"<@{player.player_id}> "
                                reminderMessage += f"currently starting {numberOfStarters} of {league.team_starts}\n"
                        if sendReminder:
                            channel = await self.bot.fetch_channel(
                                int(league.discord_channel)
                            )
                            if not channel is None:
                                await channel.send(content=reminderMessage)

    @app_commands.command(
        name="processwaivers", description="Process all waivers (ADMIN)"
    )
    async def processWaivers(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message("Attempting to process waivers")
            message = await interaction.original_response()
            week: WeekStatus = await self.bot.getCurrentWeek()
            async with self.bot.async_session() as session:
                leagues_result = await session.execute(
                    select(League).where(League.active)
                )
                leagues = leagues_result.scalars().all()
                if len(leagues) == 0:
                    await message.edit(content="There are no active leagues!")
                else:
                    for league in leagues:
                        waiverReportEmbed = Embed(
                            title=f"**{league.league_name} Week {week.week} Waiver Report**",
                            description="",
                        )
                        waiverClaims_result = await session.execute(
                            select(WaiverClaim).where(
                                WaiverClaim.league_id == league.league_id
                            )
                        )
                        waiverClaimsList = waiverClaims_result.scalars().all()
                        teamOnWaiversToAdd = []
                        if len(waiverClaimsList) > 0:
                            waiverNum = 1
                            waiverPriorities_result = await session.execute(
                                select(WaiverPriority)
                                .where(WaiverPriority.league_id == league.league_id)
                                .order_by(WaiverPriority.priority.asc())
                            )
                            waiverPrioritiesList = (
                                waiverPriorities_result.scalars().all()
                            )
                            lastTeam = len(waiverPrioritiesList)
                            while waiverNum <= lastTeam:
                                waiverPriorities_result = await session.execute(
                                    select(WaiverPriority)
                                    .where(WaiverPriority.league_id == league.league_id)
                                    .order_by(WaiverPriority.priority.asc())
                                )
                                waiverPrioritiesList = (
                                    waiverPriorities_result.scalars().all()
                                )
                                priorityToCheck = None
                                for wp in waiverPrioritiesList:
                                    if wp.priority == waiverNum:
                                        priorityToCheck = wp
                                        break
                                if priorityToCheck is None:
                                    waiverNum += 1
                                    continue
                                fantasyTeam: FantasyTeam = priorityToCheck.fantasy_team
                                waiverClaims_result = await session.execute(
                                    select(WaiverClaim)
                                    .where(
                                        WaiverClaim.fantasy_team_id
                                        == fantasyTeam.fantasy_team_id
                                    )
                                    .order_by(WaiverClaim.priority.asc())
                                )
                                waiverClaimsForTeam = (
                                    waiverClaims_result.scalars().all()
                                )
                                if len(waiverClaimsForTeam) > 0:
                                    for waiverclaim in waiverClaimsForTeam:
                                        isTeamOnWaivers_result = await session.execute(
                                            select(TeamOnWaivers).where(
                                                TeamOnWaivers.league_id
                                                == league.league_id,
                                                TeamOnWaivers.team_number
                                                == waiverclaim.team_claimed,
                                            )
                                        )
                                        isTeamOnWaiversList = (
                                            isTeamOnWaivers_result.scalars().all()
                                        )
                                        isDropTeamOnRoster_result = (
                                            await session.execute(
                                                select(TeamOwned).where(
                                                    TeamOwned.fantasy_team_id
                                                    == fantasyTeam.fantasy_team_id,
                                                    TeamOwned.team_key
                                                    == waiverclaim.team_to_drop,
                                                )
                                            )
                                        )
                                        isDropTeamOnRosterList = (
                                            isDropTeamOnRoster_result.scalars().all()
                                        )
                                        if (
                                            len(isTeamOnWaiversList) > 0
                                            and len(isDropTeamOnRosterList) > 0
                                        ):
                                            newWaiver = TeamOnWaivers(
                                                league_id=fantasyTeam.league_id,
                                                team_number=waiverclaim.team_to_drop,
                                            )
                                            teamOnWaiversToAdd.append(newWaiver)
                                            await session.execute(
                                                delete(TeamOnWaivers).where(
                                                    TeamOnWaivers.league_id
                                                    == league.league_id,
                                                    TeamOnWaivers.team_number
                                                    == waiverclaim.team_claimed,
                                                )
                                            )
                                            await session.flush()
                                            await session.execute(
                                                delete(TeamStarted).where(
                                                    TeamStarted.league_id
                                                    == fantasyTeam.league_id,
                                                    TeamStarted.team_number
                                                    == waiverclaim.team_to_drop,
                                                    TeamStarted.week >= week.week,
                                                )
                                            )
                                            await session.flush()
                                            await session.execute(
                                                delete(TeamOwned).where(
                                                    TeamOwned.league_id
                                                    == fantasyTeam.league_id,
                                                    TeamOwned.team_key
                                                    == waiverclaim.team_to_drop,
                                                )
                                            )
                                            draftSoNotFail_result = (
                                                await session.execute(
                                                    select(Draft).where(
                                                        Draft.league_id
                                                        == fantasyTeam.league_id,
                                                        Draft.event_key
                                                        == str(league.year) + "fim",
                                                    )
                                                )
                                            )
                                            draftSoNotFail: Draft = (
                                                draftSoNotFail_result.scalars().first()
                                            )
                                            await session.flush()
                                            newTeamToAdd = TeamOwned(
                                                team_key=str(waiverclaim.team_claimed),
                                                fantasy_team_id=fantasyTeam.fantasy_team_id,
                                                league_id=fantasyTeam.league_id,
                                                draft_id=draftSoNotFail.draft_id,
                                            )
                                            session.add(newTeamToAdd)
                                            await session.flush()
                                            waiverReportEmbed.description += f"{fantasyTeam.fantasy_team_name} successfully added team {waiverclaim.team_claimed} and dropped {waiverclaim.team_to_drop}!\n"
                                            await session.flush()
                                            # Move waiver priority
                                            # Temporary placeholder value (e.g., set to -1 for the current priority)
                                            priorityToCheck.priority = -1
                                            await session.flush()

                                            # Now adjust all priorities (e.g., shift them down)
                                            for prio in waiverPrioritiesList:
                                                if prio.priority > waiverNum:
                                                    prio.priority -= 1
                                                    await session.flush()

                                            # Finally, assign the last priority to the current team
                                            priorityToCheck.priority = lastTeam
                                            await session.delete(waiverclaim)
                                            await session.flush()
                                            break
                                        elif len(isTeamOnWaiversList) == 0:
                                            waiverReportEmbed.description += f"{fantasyTeam.fantasy_team_name} tried to claim team {waiverclaim.team_claimed}, however they are no longer on waivers, unable to process\n"
                                            await session.delete(waiverclaim)
                                            await session.flush()
                                        else:
                                            waiverReportEmbed.description += f"{fantasyTeam.fantasy_team_name} tried to claim team {waiverclaim.team_claimed} but their designated drop team {waiverclaim.team_to_drop} is no longer on the team, unable to process\n"
                                            await session.delete(waiverclaim)
                                            await session.flush()
                                else:
                                    waiverNum += 1
                        else:
                            waiverReportEmbed.description += (
                                "No waiver claims to process"
                            )
                        channel = await self.bot.fetch_channel(
                            int(league.discord_channel)
                        )
                        if not channel is None:
                            await channel.send(embed=waiverReportEmbed)
                        await session.execute(
                            delete(TeamOnWaivers).where(
                                TeamOnWaivers.league_id == league.league_id
                            )
                        )
                        await session.flush()
                        session.add_all(teamOnWaiversToAdd)
                        await session.flush()
                await session.commit()

    @app_commands.command(name="forceadddrop", description="Force an add/drop (ADMIN)")
    async def forceAddDrop(
        self,
        interaction: discord.Interaction,
        fantasyteamid: int,
        addteam: str,
        dropteam: str,
        towaivers: bool = True,
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to admin drop {dropteam} to add {addteam} from team id {fantasyteamid}",
                ephemeral=True,
            )
            manageTeamCog = manageteam.ManageTeam(self.bot)
            await manageTeamCog.addDropTeamTask(
                interaction,
                addTeam=addteam,
                dropTeam=dropteam,
                fantasyId=fantasyteamid,
                force=True,
                toWaivers=towaivers,
            )

    @app_commands.command(
        name="forcetrade", description="Force a trade through (ADMIN)"
    )
    async def forceTrade(
        self,
        interaction: discord.Interaction,
        teamid1: int,
        teamid2: int,
        team1trading: str,
        team2trading: str,
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to admin force trade {team1trading} force {team2trading} for team ids {teamid1} and {teamid2}",
                ephemeral=True,
            )
            manageTeamCog = manageteam.ManageTeam(self.bot)
            tradeProp: TradeProposal = await manageTeamCog.createTradeProposalTask(
                interaction, teamid1, teamid2, team1trading, team2trading, force=True
            )
            await manageTeamCog.acceptTradeTask(
                interaction, teamid2, tradeProp.trade_id, force=True
            )

    @app_commands.command(
        name="genweeks", description="Generate weeks for a given year (ADMIN)"
    )
    async def genWeeks(
        self, interaction: discord.Interaction, year: int, week: int = -1
    ):
        if await self.verifyAdmin(interaction):
            async with self.bot.async_session() as session:
                if week == -1:
                    await interaction.response.send_message(
                        f"Attempting to generate all weeks for {year}"
                    )
                    await session.execute(
                        delete(WeekStatus).where(WeekStatus.year == year)
                    )
                    await session.flush()
                    for k in range(1, 7):
                        weekStatToadd = WeekStatus(
                            week=k,
                            year=year,
                            lineups_locked=False,
                            scores_finalized=False,
                            active=True,
                        )
                        session.add(weekStatToadd)
                        await session.flush()
                else:
                    await interaction.response.send_message(
                        f"Attempting to generate week {week} for {year}"
                    )
                    await session.execute(
                        delete(WeekStatus).where(
                            WeekStatus.year == year, WeekStatus.week == week
                        )
                    )
                    await session.flush()
                    weekStatToadd = WeekStatus(
                        week=week,
                        year=year,
                        lineups_locked=False,
                        scores_finalized=False,
                        active=True,
                    )
                    session.add(weekStatToadd)
                    await session.flush()
                msg = await interaction.original_response()
                await session.commit()
                await msg.edit(content="Success!")

    @app_commands.command(name="scoredraft", description="Score an individual draft")
    async def score_draft(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message("Attempting to score draft.")
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

    @app_commands.command(
        name="rescoredraft",
        description="Recalculate fantasy scores for an individual draft without pulling new event data (ADMIN)",
    )
    async def rescore_draft(self, interaction: discord.Interaction):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message("Attempting to rescore draft.")
            response = await interaction.original_response()
            draftCog = drafting.Drafting(self.bot)
            draft: Draft = await draftCog.getDraftFromChannel(interaction)
            if not draft:
                await response.edit(content="No draft associated with this channel")
                return
            league: League = await draftCog.getLeague(draft.draft_id)
            if league.is_fim:
                await response.edit(content="Not a valid league to run rescoredraft in")
                return
            else:
                await self.scoreSingleDraft(interaction, draft.draft_id)
                await self.notifySingleDraftTask(interaction, draft.draft_id)

    @app_commands.command(
        name="addeventteams",
        description="Add teams to an event (use for offseasons with released team list) (ADMIN)",
    )
    async def addEventTeams(self, interaction: discord.Interaction, teams: str):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to admin add teams {teams} to event"
            )
            response = await interaction.original_response()
            draftCog = drafting.Drafting(self.bot)
            draft: Draft = await draftCog.getDraftFromChannel(interaction)
            if not draft:
                await response.edit(content="No draft associated with this channel")
                return
            await self.addTeamsToEventTask(interaction, teams, draft)

    @app_commands.command(
        name="setstatcorrection",
        description="Set stat correction for a team score (ADMIN)",
    )
    async def setStatCorrection(
        self,
        interaction: discord.Interaction,
        team_number: str,
        event_key: str,
        correction: int,
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Setting stat correction for {team_number} at {event_key} to {correction}",
                ephemeral=True,
            )
            await self.setStatCorrectionTask(
                interaction, team_number, event_key, correction
            )

    @app_commands.command(
        name="resetstatcorrection",
        description="Reset stat correction for a team score (ADMIN)",
    )
    async def resetStatCorrection(
        self, interaction: discord.Interaction, team_number: str, event_key: str
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Resetting stat correction for {team_number} at {event_key}",
                ephemeral=True,
            )
            await self.resetStatCorrectionTask(interaction, team_number, event_key)

    @app_commands.command(
        name="reassignbteam",
        description="Reassign B teams to different numbers (for use with offseasons) (ADMIN)",
    )
    async def reassignBTeam(
        self, interaction: discord.Interaction, oldteamnumber: str, newteamnumber: str
    ):
        if await self.verifyAdmin(interaction):
            await interaction.response.send_message(
                f"Attempting to admin reassign {oldteamnumber} to {newteamnumber} for this event"
            )
            response = await interaction.original_response()
            draftCog = drafting.Drafting(self.bot)
            draft: Draft = await draftCog.getDraftFromChannel(interaction)
            if not draft:
                await response.edit(content="No draft associated with this channel")
                return
            await self.reassignBTeamTask(
                interaction, oldteamnumber, newteamnumber, draft
            )


async def setup(bot: commands.Bot) -> None:
    cog = Admin(bot)
    guild = await bot.fetch_guild(int(os.getenv("GUILD_ID")))
    assert guild is not None

    await bot.add_cog(cog, guilds=[guild])
