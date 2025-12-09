import logging
import os
from datetime import datetime, timedelta

import discord
from discord import Embed, app_commands
from discord.ext import commands
from sqlalchemy import delete, func, select

from models.draft import Draft
from models.scores import (
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
STATESWEEK = 7
STATESEXTRA = 1
MAXSTARTS = 2


class ManageTeam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def isEnglish(self, s):
        try:
            s.encode(encoding="utf-8").decode("ascii")
        except UnicodeDecodeError:
            return False
        else:
            return True

    async def getWaiverClaimPriority(self, fantasyId):
        async with self.bot.async_session() as session:
            stmt = (
                select(WaiverClaim)
                .where(WaiverClaim.fantasy_team_id == fantasyId)
                .order_by(WaiverClaim.priority.desc())
            )
            result = await session.execute(stmt)
            waiverprio = result.scalars().first()
            if not waiverprio:
                return 1
            else:
                return waiverprio.priority + 1

    async def postTeamBoard(self, interaction: discord.Interaction, fantasyTeam: int):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyTeam)
            result = await session.execute(stmt)
            fTeamFirst: FantasyTeam = result.scalars().first()
            if fTeamFirst is None:
                await message.edit(content="Invalid team id")
                return
            teamBoardEmbed = Embed(
                title=f"**{fTeamFirst.fantasy_team_name} Week-by-Week board**",
                description="```",
            )
            teamBoardEmbed.description += f"{'Team':^4s}{'':1s}{'Week 1':^9s}{'':1s}{'Week 2':^9s}{'':1s}{'Week 3':^9s}{'':1s}{'Week 4':^9s}{'':1s}{'Week 5':^9}\n"
            stmt = (
                select(TeamOwned)
                .where(TeamOwned.fantasy_team_id == fantasyTeam)
                .order_by(TeamOwned.team_key.asc())
            )
            result = await session.execute(stmt)
            teamsOwned = result.scalars().all()
            for team in teamsOwned:
                stmt = (
                    select(TeamScore)
                    .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key)
                    .where(
                        TeamScore.team_key == team.team_key,
                        FRCEvent.year == fTeamFirst.league.year,
                    )
                )
                result = await session.execute(stmt)
                teamEvents = result.scalars().all()
                weeks = ["---" for k in range(6)]
                for event in teamEvents:
                    stmt = select(FRCEvent).where(FRCEvent.event_key == event.event_key)
                    result = await session.execute(stmt)
                    frcEvent = result.scalars().first()
                    if int(frcEvent.week) < STATESWEEK:
                        if weeks[int(frcEvent.week) - 1] == "---":
                            weeks[int(frcEvent.week) - 1] = event.event_key
                        else:
                            weeks[int(frcEvent.week) - 1] = "2 Events"
                teamBoardEmbed.description += f"{team.team_key:>4s}{'':1s}{weeks[0]:^9s}{'':1s}{weeks[1]:^9s}{'':1s}{weeks[2]:^9s}{'':1s}{weeks[3]:^9s}{'':1s}{weeks[4]:^9}\n"
            teamBoardEmbed.description += "```"
            await message.edit(embed=teamBoardEmbed, content="")

    async def getFantasyTeamIdFromInteraction(self, interaction: discord.Interaction):
        async with self.bot.async_session() as session:
            stmt = select(League).where(
                League.discord_channel == str(interaction.channel_id)
            )
            result = await session.execute(stmt)
            league = result.scalars().first()

            if league is None:
                stmt = select(Draft).where(
                    Draft.discord_channel == str(interaction.channel_id)
                )
                result = await session.execute(stmt)
                draft = result.scalars().first()
                if draft:
                    stmt = select(League).where(League.league_id == draft.league_id)
                    result = await session.execute(stmt)
                    league = result.scalars().first()

            if league is None:
                return None

            stmt = (
                select(FantasyTeam)
                .join(
                    PlayerAuthorized,
                    FantasyTeam.fantasy_team_id == PlayerAuthorized.fantasy_team_id,
                )
                .join(League, FantasyTeam.league_id == League.league_id)
                .where(PlayerAuthorized.player_id == str(interaction.user.id))
                .where(League.league_id == league.league_id)
            )
            result = await session.execute(stmt)
            team = result.scalars().first()
            if team:
                return team.fantasy_team_id
            else:
                return None

    async def startTeamTask(
        self, interaction: discord.Interaction, frcteam: str, week: int, fantasyId: int
    ):
        deferred = await interaction.original_response()
        async with self.bot.async_session() as session:
            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            fantasyteam: FantasyTeam = result.scalars().first()

            stmt = select(League).where(League.league_id == fantasyteam.league_id)
            result = await session.execute(stmt)
            league: League = result.scalars().first()
            # is this a fim season long league?
            if not league.is_fim:
                await deferred.edit(content="This league does not support starts/sits.")
                return

            # Check if lineups are locked for the given week in this league
            stmt = select(WeekStatus).where(
                WeekStatus.year == league.year, WeekStatus.week == week
            )
            result = await session.execute(stmt)
            week_status = result.scalars().first()

            if week_status and week_status.lineups_locked:
                await deferred.edit(
                    content="Lineups are locked for this week, you cannot modify your lineup at this time."
                )
                return
            # do you own the team?
            stmt = select(TeamOwned).where(
                TeamOwned.team_key == frcteam,
                TeamOwned.league_id == league.league_id,
                TeamOwned.fantasy_team_id == fantasyId,
            )
            result = await session.execute(stmt)
            teamowned = result.scalars().first()
            if teamowned is None:
                await deferred.edit(content="You do not own this team.")
                return

            stmt = select(TeamStarted).where(
                TeamStarted.fantasy_team_id == fantasyId, TeamStarted.week == week
            )
            result = await session.execute(stmt)
            teamsStartedRecords = result.scalars().all()
            teamsStartedCount = len(teamsStartedRecords)

            if (league.team_starts <= teamsStartedCount and week < STATESWEEK) or (
                league.team_starts + STATESEXTRA <= teamsStartedCount
                and week == STATESWEEK
            ):
                await deferred.edit(
                    content="Already starting max number of teams this week."
                )
            else:
                # get frc events in fim this week
                stmt = select(FRCEvent).where(
                    FRCEvent.year == league.year,
                    FRCEvent.week == week,
                    FRCEvent.is_fim == True,
                )
                result = await session.execute(stmt)
                frcevents = result.scalars().all()
                eventList = [event.event_key for event in frcevents]
                # does team compete in fim this week?
                stmt = select(TeamScore).where(
                    TeamScore.team_key == frcteam, TeamScore.event_key.in_(eventList)
                )
                result = await session.execute(stmt)
                teamcompeting = result.scalars().all()
                # is your team already starting?
                alreadyStarting = sum(
                    1 for r in teamsStartedRecords if r.team_number == frcteam
                )
                # has your team been started twice this year already?
                stmt = (
                    select(func.count())
                    .select_from(TeamStarted)
                    .where(
                        TeamStarted.league_id == league.league_id,
                        TeamStarted.team_number == frcteam,
                        TeamStarted.week < STATESWEEK,
                    )
                )
                result = await session.execute(stmt)
                teamStartedCount = result.scalar()

                if len(teamcompeting) == 0:
                    await deferred.edit(content="This team is not competing this week!")
                elif len(teamcompeting) > 1:
                    await deferred.edit(
                        content="Please contact a fantasy admin to start your team. They are competing at multiple FiM events this week which is a special case."
                    )
                elif alreadyStarting > 0:
                    await deferred.edit(
                        content="This team is already starting this week!"
                    )
                elif not week == STATESWEEK and teamStartedCount >= MAXSTARTS:
                    await deferred.edit(
                        content=f"This team may not be started again until States, they have reached the maximum of {MAXSTARTS}"
                    )
                else:
                    eventkey = teamcompeting[0].event_key
                    stmt = select(FRCEvent).where(FRCEvent.event_key == eventkey)
                    result = await session.execute(stmt)
                    frcevent: FRCEvent = result.scalars().first()
                    teamStartedToAdd = TeamStarted(
                        fantasy_team_id=fantasyId,
                        team_number=frcteam,
                        league_id=league.league_id,
                        event_key=eventkey,
                        week=week,
                    )
                    session.add(teamStartedToAdd)
                    await session.commit()
                    await deferred.edit(
                        content=f"{fantasyteam.fantasy_team_name} is starting team {frcteam} competing at {frcevent.event_name} in week {week}!"
                    )

    async def sitTeamTask(
        self, interaction: discord.Interaction, frcteam: str, week: int, fantasyId: int
    ):
        deferred = await interaction.original_response()
        async with self.bot.async_session() as session:
            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            fantasyteam: FantasyTeam = result.scalars().first()

            stmt = select(League).where(League.league_id == fantasyteam.league_id)
            result = await session.execute(stmt)
            league: League = result.scalars().first()
            # is this a fim season long league?
            if not league.is_fim:
                await deferred.edit(content="This league does not support starts/sits.")
                return

            # Check if lineups are locked for the given week in this league
            stmt = select(WeekStatus).where(
                WeekStatus.year == league.year, WeekStatus.week == week
            )
            result = await session.execute(stmt)
            week_status = result.scalars().first()

            if week_status and week_status.lineups_locked:
                await deferred.edit(
                    content="Lineups are locked for this week, you cannot modify your lineup at this time."
                )
                return

            # is this team actually starting for you?
            stmt = select(TeamStarted).where(
                TeamStarted.team_number == frcteam,
                TeamStarted.league_id == league.league_id,
                TeamStarted.fantasy_team_id == fantasyId,
                TeamStarted.week == week,
            )
            result = await session.execute(stmt)
            teamstarted = result.scalars().all()
            if len(teamstarted) == 0:
                await deferred.edit(content="You are not currently starting this team.")
            elif len(teamstarted) > 1:
                await deferred.edit(
                    content="Please contact a fantasy admin to sit your team. You are starting them at multiple FiM events this week which is a special case."
                )
            else:
                event: FRCEvent = teamstarted[0].event
                stmt = delete(TeamStarted).where(
                    TeamStarted.team_number == frcteam,
                    TeamStarted.league_id == league.league_id,
                    TeamStarted.fantasy_team_id == fantasyId,
                    TeamStarted.week == week,
                )
                await session.execute(stmt)
                await session.commit()
                await deferred.edit(
                    content=f"{fantasyteam.fantasy_team_name} is sitting team {frcteam} competing at {event.event_name} in week {week}."
                )

    async def setLineupTask(
        self,
        interaction: discord.Interaction,
        week: int,
        teams: list[str],
        fantasyId: int,
    ):
        deferred = await interaction.original_response()
        async with self.bot.async_session() as session:
            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            fantasyteam: FantasyTeam = result.scalars().first()

            stmt = select(League).where(League.league_id == fantasyteam.league_id)
            result = await session.execute(stmt)
            league: League = result.scalars().first()
            # is this a fim season long league?
            if not league.is_fim:
                await deferred.edit(content="This league does not support starts/sits.")
                return

            # Check if lineups are locked for the given week in this league
            stmt = select(WeekStatus).where(
                WeekStatus.year == league.year, WeekStatus.week == week
            )
            result = await session.execute(stmt)
            week_status = result.scalars().first()

            if week_status and week_status.lineups_locked:
                await deferred.edit(
                    content="Lineups are locked for this week, you cannot modify your lineup at this time."
                )
                return

            # remove all existing starts for this week
            stmt = delete(TeamStarted).where(
                TeamStarted.league_id == league.league_id,
                TeamStarted.fantasy_team_id == fantasyId,
                TeamStarted.week == week,
            )
            await session.execute(stmt)
            await session.commit()

        # start each team provided
        for team in teams:
            await self.startTeamTask(
                interaction, frcteam=team, week=week, fantasyId=fantasyId
            )

    async def renameTeamTask(
        self, interaction: discord.Interaction, newname: str, fantasyId: int
    ):
        deferred = await interaction.original_response()
        async with self.bot.async_session() as session:
            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            fantasyteam: FantasyTeam = result.scalars().first()
            oldname = fantasyteam.fantasy_team_name
            fantasyteam.fantasy_team_name = newname
            await session.commit()
            await deferred.edit(
                content=f"Team **{oldname}** renamed to **{newname}** (Team id {fantasyteam.fantasy_team_id})"
            )

    async def viewStartsTask(self, interaction: discord.Interaction, fantasyId: int):
        async with self.bot.async_session() as session:
            # retrieve league starts data
            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            fantasyteam: FantasyTeam = result.scalars().first()
            league: League = fantasyteam.league
            teamsToStart = league.team_starts
            # retrieve teamstarted for team
            stmt = select(TeamStarted).where(TeamStarted.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            teamsStarted = result.scalars().all()
            # for every week
            embed = Embed(
                title=f"**{fantasyteam.fantasy_team_name} Starting Lineups**",
                description=f"```{'':^8s}",
            )
            for team in range(1, teamsToStart + STATESEXTRA + 1):
                if team > league.team_starts:
                    embed.description += f"{f'Team {team}':^7s}\n"
                else:
                    embed.description += f"{f'Team {team}':^7s}{'':2s}"
            for week in range(1, STATESWEEK + 1):
                # grab every started team and fill in embed
                weekTeamsStarted = [t for t in teamsStarted if t.week == week]
                lineToAdd = ["-----" for _ in range(teamsToStart)]
                for _ in range(STATESEXTRA):
                    if not week == STATESWEEK:
                        lineToAdd.append("")
                    else:
                        lineToAdd.append("-----")
                count = 0
                for start in weekTeamsStarted:
                    lineToAdd[count] = start.team.team_number
                    count += 1
                embed.description += f"{f'Week {week}':^8s}"
                for k in range(teamsToStart + STATESEXTRA):
                    if k + 1 > teamsToStart:
                        embed.description += f"{lineToAdd[k]:^7s}\n"
                    else:
                        embed.description += f"{lineToAdd[k]:^7s}{'':2s}"
            # send embed
            response = await interaction.original_response()
            embed.description += "```"
            await response.edit(embed=embed, content="")

    async def viewMyClaimsTask(self, interaction: discord.Interaction, fantasyId: int):
        async with self.bot.async_session() as session:
            # retrieve waiver claim data
            response = await interaction.original_response()
            stmt = (
                select(WaiverClaim)
                .where(WaiverClaim.fantasy_team_id == fantasyId)
                .order_by(WaiverClaim.priority.asc())
            )
            result = await session.execute(stmt)
            waiverClaims = result.scalars().all()
            if len(waiverClaims) == 0:
                await response.edit(content="You currently have no active claims.")
                return
            stmt = select(WaiverPriority).where(
                WaiverPriority.fantasy_team_id == fantasyId
            )
            result = await session.execute(stmt)
            waiverPriority: WaiverPriority = result.scalars().first()
            embed = Embed(
                title=f"**Waiver Claims - Team Priority: {waiverPriority.priority}**",
                description=f"```{'Priority':^12s}{'Claimed Team':^16s}{'Team to drop':^16s}\n",
            )
            for claim in waiverClaims:
                embed.description += f"{claim.priority:^12d}{claim.team_claimed:^16s}{claim.team_to_drop:^16s}\n"
            embed.description += "```"
            await response.edit(embed=embed, content="")

    async def addDropTeamTask(
        self,
        interaction: discord.Interaction,
        addTeam: str,
        dropTeam: str,
        fantasyId: int,
        force: bool = False,
        toWaivers: bool = True,
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            currentWeek = await self.bot.getCurrentWeek()
            if currentWeek.lineups_locked == True:
                await message.edit(
                    content="Cannot make transaction with locked lineups."
                )
                return
            # check if own dropTeam
            stmt = select(TeamOwned).where(
                TeamOwned.team_key == str(dropTeam),
                TeamOwned.fantasy_team_id == fantasyId,
            )
            result = await session.execute(stmt)
            teamDropOwned = result.scalars().first()

            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            fantasyTeam: FantasyTeam = result.scalars().first()

            stmt = select(TeamOnWaivers).where(
                TeamOnWaivers.team_number == str(addTeam),
                TeamOnWaivers.league_id == fantasyTeam.league_id,
            )
            result = await session.execute(stmt)
            teamsOnWaivers = result.scalars().first()

            stmt = select(TeamOwned).where(
                TeamOwned.league_id == fantasyTeam.league_id,
                TeamOwned.team_key == str(addTeam),
            )
            result = await session.execute(stmt)
            teamAddOwnedByOther = result.scalars().first()

            stmt = select(Team).where(
                Team.team_number == str(addTeam), Team.is_fim == True
            )
            result = await session.execute(stmt)
            teamInFiM = result.scalars().first()

            if teamDropOwned is None:
                await message.edit(
                    content="You do not own the team you are attempting to drop!"
                )
            elif teamsOnWaivers is not None and not force:
                await message.edit(
                    content="Team is on waivers. Please submit a claim instead."
                )
            elif teamAddOwnedByOther is not None:
                await message.edit(content="This team is already owned.")
            elif teamInFiM is None:
                await message.edit(content="This team is not in FiM.")
            else:
                if toWaivers:
                    newWaiver = TeamOnWaivers(
                        league_id=fantasyTeam.league_id, team_number=dropTeam
                    )
                    session.add(newWaiver)
                if force:
                    stmt = delete(TeamOnWaivers).where(
                        TeamOnWaivers.team_number == str(addTeam),
                        TeamOnWaivers.league_id == fantasyTeam.league_id,
                    )
                    await session.execute(stmt)
                    await session.flush()
                stmt = delete(TeamStarted).where(
                    TeamStarted.league_id == fantasyTeam.league_id,
                    TeamStarted.team_number == dropTeam,
                    TeamStarted.week >= currentWeek.week,
                )
                await session.execute(stmt)
                await session.flush()
                stmt = delete(TeamOwned).where(
                    TeamOwned.league_id == fantasyTeam.league_id,
                    TeamOwned.team_key == dropTeam,
                )
                await session.execute(stmt)

                stmt = select(Draft).where(
                    Draft.league_id == fantasyTeam.league_id,
                    Draft.event_key == "2026fim",
                )
                result = await session.execute(stmt)
                draftSoNotFail: Draft = result.scalars().first()
                await session.flush()
                newTeamToAdd = TeamOwned(
                    team_key=str(addTeam),
                    fantasy_team_id=fantasyId,
                    league_id=fantasyTeam.league_id,
                    draft_id=draftSoNotFail.draft_id,
                )
                session.add(newTeamToAdd)
                await session.flush()
                await message.channel.send(
                    content=f"{fantasyTeam.fantasy_team_name} successfully added team {addTeam} and dropped {dropTeam}!"
                )
                await session.commit()

    async def makeWaiverClaimTask(
        self,
        interaction: discord.Interaction,
        fantasyId: int,
        addTeam: str,
        dropTeam: str,
    ):
        async with self.bot.async_session() as session:
            # get original message to edit
            originalMessage = await interaction.original_response()
            # check if addTeam is on waivers
            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            fantasyTeam: FantasyTeam = result.scalars().first()

            stmt = select(TeamOnWaivers).where(
                TeamOnWaivers.team_number == addTeam,
                TeamOnWaivers.league_id == fantasyTeam.league_id,
            )
            result = await session.execute(stmt)
            teamsOnWaivers = result.scalars().first()

            stmt = select(TeamOwned).where(
                TeamOwned.team_key == dropTeam, TeamOwned.fantasy_team_id == fantasyId
            )
            result = await session.execute(stmt)
            teamowned = result.scalars().first()

            stmt = select(WaiverClaim).where(
                WaiverClaim.fantasy_team_id == fantasyId,
                WaiverClaim.team_claimed == addTeam,
                WaiverClaim.team_to_drop == dropTeam,
            )
            result = await session.execute(stmt)
            waiverClaimAlreadyMade = result.scalars().first()

            if teamsOnWaivers is None:
                await originalMessage.edit(content=f"Team {addTeam} is not on waivers!")
            # check if own dropTeam
            elif teamowned is None:
                await originalMessage.edit(content=f"You do not own team {dropTeam}.")
            # check if already made exact waiver claim
            elif waiverClaimAlreadyMade is not None:
                await originalMessage.edit(content=f"You have already made this claim!")
            # create waiver claim
            else:
                newPriority = await self.getWaiverClaimPriority(fantasyId)
                waiverClaim = WaiverClaim(
                    fantasy_team_id=fantasyId,
                    league_id=fantasyTeam.league_id,
                    team_claimed=addTeam,
                    team_to_drop=dropTeam,
                    priority=newPriority,
                )
                session.add(waiverClaim)
                await originalMessage.edit(
                    content=f"Successfully created claim for {addTeam}!"
                )
                await session.commit()

    async def cancelClaimTask(
        self, interaction: discord.Interaction, fantasyId: int, priority: int
    ):
        async with self.bot.async_session() as session:
            # get original message to edit
            originalMessage = await interaction.original_response()
            # check if claim id exists
            stmt = select(WaiverClaim).where(
                WaiverClaim.fantasy_team_id == fantasyId,
                WaiverClaim.priority >= priority,
            )
            result = await session.execute(stmt)
            waiverClaimExists = result.scalars().all()

            claimToCancel = next(
                (c for c in waiverClaimExists if c.priority == priority), None
            )
            if claimToCancel is None:
                await originalMessage.edit(
                    content=f"You do not have a claim with this priority!"
                )
            # create waiver claim
            else:
                addTeam = claimToCancel.team_claimed
                dropTeam = claimToCancel.team_to_drop
                stmt = delete(WaiverClaim).where(
                    WaiverClaim.fantasy_team_id == fantasyId,
                    WaiverClaim.priority == priority,
                )
                await session.execute(stmt)
                claimsToShift = [c for c in waiverClaimExists if c.priority > priority]
                for claim in claimsToShift:
                    claim.priority -= 1
                await originalMessage.edit(
                    content=f"Successfully canceled claim for {addTeam} which was dropping {dropTeam}"
                )
                await session.commit()

    async def createTradeProposalTask(
        self,
        interaction: discord.Interaction,
        fantasyId: int,
        otherFantasyId: int,
        teamsOffered: str,
        teamsRequested: str,
        force: bool = False,
    ) -> TradeProposal:
        async with self.bot.async_session() as session:
            originalMessage = await interaction.original_response()
            # Check if lineups are locked for the given week in this league
            week_status = await self.bot.getCurrentWeek()

            if week_status and week_status.lineups_locked:
                await originalMessage.edit(
                    content="Lineups are locked for this week, you cannot modify your lineup at this time."
                )
                return

            stmt = select(FantasyTeam).where(FantasyTeam.fantasy_team_id == fantasyId)
            result = await session.execute(stmt)
            proposer_team: FantasyTeam = result.scalars().first()

            stmt = select(FantasyTeam).where(
                FantasyTeam.fantasy_team_id == otherFantasyId,
                FantasyTeam.league_id == proposer_team.league_id,
            )
            result = await session.execute(stmt)
            proposed_to_team: FantasyTeam = result.scalars().first()

            if not proposer_team and not proposed_to_team:
                await originalMessage.edit(content=f"Invalid fantasy team ID provided.")
                return
            expiration_time = datetime.now() + timedelta(hours=1)

            new_trade = TradeProposal(
                league_id=proposer_team.league_id,
                proposer_team_id=fantasyId,
                proposed_to_team_id=otherFantasyId,
                expiration=expiration_time,
            )
            session.add(new_trade)
            await session.flush()
            offeredTeamsList = [team.strip() for team in teamsOffered.split(",")]
            requestedTeamsList = [team.strip() for team in teamsRequested.split(",")]

            if not len(offeredTeamsList) == len(requestedTeamsList):
                await originalMessage.edit(
                    content="Must offer the exact same amount of teams."
                )
                return

            tradeProposalEmbed = Embed(
                title="**Trade Proposal Alert!**", description=""
            )
            offerText = f"**{proposer_team.fantasy_team_name} is offering the following teams:**\n"
            teamsInTradeCount = len(offeredTeamsList)
            i = 1
            # Validate that the proposer owns the offered teams
            for team_key in offeredTeamsList:
                stmt = select(TeamOwned).where(
                    TeamOwned.team_key == team_key,
                    TeamOwned.fantasy_team_id == fantasyId,
                )
                result = await session.execute(stmt)
                ownership = result.scalars().first()
                if not ownership:
                    await originalMessage.edit(
                        content=f"Team {team_key} is not owned by the proposer."
                    )
                    return
                new_trade_team = TradeTeams(
                    trade_id=new_trade.trade_id, team_key=team_key, is_offered=True
                )
                offerText += f"{team_key}"
                if i < teamsInTradeCount:
                    offerText += ", "
                else:
                    offerText += "\n"
                session.add(new_trade_team)
                i += 1
            requestTeamText = f"**{proposed_to_team.fantasy_team_name} would send in return the following teams:**\n"
            # Validate that the proposed-to team owns the requested teams
            i = 1
            for team_key in requestedTeamsList:
                stmt = select(TeamOwned).where(
                    TeamOwned.team_key == team_key,
                    TeamOwned.fantasy_team_id == otherFantasyId,
                )
                result = await session.execute(stmt)
                ownership = result.scalars().first()
                if not ownership:
                    await originalMessage.edit(
                        content=f"Team {team_key} is not owned by the proposed-to team."
                    )
                    return
                new_trade_team = TradeTeams(
                    trade_id=new_trade.trade_id, team_key=team_key, is_offered=False
                )
                requestTeamText += f"{team_key}"
                if i < teamsInTradeCount:
                    requestTeamText += ", "
                else:
                    requestTeamText += "\n"
                session.add(new_trade_team)
                i += 1
            acceptText = f"**If you wish to accept, use command `/accept {new_trade.trade_id}` within 1 hour.**\n"
            declineText = f"*If you wish to decline, use command `/decline {new_trade.trade_id}`.*\n"
            tradeProposalEmbed.description += (
                offerText + requestTeamText + acceptText + declineText
            )
            # add notifs for other team
            stmt = select(PlayerAuthorized).where(
                PlayerAuthorized.fantasy_team_id == otherFantasyId
            )
            result = await session.execute(stmt)
            playersToNotif = result.scalars().all()
            notifText = ""
            for player in playersToNotif:
                notifText += f"<@{player.player_id}> "
            if not force:
                await interaction.channel.send(
                    embed=tradeProposalEmbed, content=notifText
                )
            # Commit all the teams involved in the trade
            await session.commit()

            stmt = select(TradeProposal).where(
                TradeProposal.trade_id == new_trade.trade_id
            )
            result = await session.execute(stmt)
            tradeProp = result.scalars().first()
            if force:
                return tradeProp

    async def declineTradeTask(
        self, interaction: discord.Interaction, fantasyId: int, tradeId: int
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            stmt = select(TradeProposal).where(
                TradeProposal.proposed_to_team_id == fantasyId,
                TradeProposal.trade_id == tradeId,
            )
            result = await session.execute(stmt)
            tradeProposal = result.scalars().first()
            if tradeProposal is not None:
                stmt = delete(TradeTeams).where(TradeTeams.trade_id == tradeId)
                await session.execute(stmt)
                await session.flush()
                stmt = delete(TradeProposal).where(
                    TradeProposal.proposed_to_team_id == fantasyId,
                    TradeProposal.trade_id == tradeId,
                )
                await session.execute(stmt)
                await session.commit()
                await interaction.channel.send(f"Trade proposal {tradeId} declined.")
            else:
                await message.edit(
                    content=f"You did not have a pending proposal with id {tradeId}."
                )

    async def acceptTradeTask(
        self,
        interaction: discord.Interaction,
        fantasyId: int,
        tradeId: int,
        force: bool = False,
    ):
        async with self.bot.async_session() as session:
            message = await interaction.original_response()
            stmt = select(TradeProposal).where(
                TradeProposal.proposed_to_team_id == fantasyId,
                TradeProposal.trade_id == tradeId,
            )
            result = await session.execute(stmt)
            proposalObj = result.scalars().first()
            currentWeek = await self.bot.getCurrentWeek()
            if currentWeek.lineups_locked == True and not force:
                await message.edit("Cannot accept a trade while lineups are locked!")
                return
            if force or proposalObj is not None:
                stmt = select(TradeTeams).where(
                    TradeTeams.trade_id == tradeId, TradeTeams.is_offered == True
                )
                result = await session.execute(stmt)
                offeredTeamsList = result.scalars().all()

                stmt = select(TradeTeams).where(
                    TradeTeams.trade_id == tradeId, TradeTeams.is_offered == False
                )
                result = await session.execute(stmt)
                requestedTeamsList = result.scalars().all()
                # add trade transaction logic
                # Validate that the proposer owns the offered teams
                tradeConfirmedEmbed = Embed(title="**Trade Alert!**", description="")
                offerText = f"**{proposalObj.proposer_team.fantasy_team_name} is sending the following teams:**\n"
                teamsInTradeCount = len(offeredTeamsList)
                i = 1
                for tradeTeam in offeredTeamsList:
                    stmt = select(TeamOwned).where(
                        TeamOwned.team_key == tradeTeam.team_key,
                        TeamOwned.fantasy_team_id == proposalObj.proposer_team_id,
                    )
                    result = await session.execute(stmt)
                    ownership = result.scalars().first()
                    if not ownership:
                        await message.edit(
                            content=f"Team {tradeTeam.team_key} is no longer owned by the proposer."
                        )
                        return
                    ownership.fantasy_team_id = proposalObj.proposed_to_team_id
                    await session.flush()
                    stmt = delete(TeamStarted).where(
                        TeamStarted.week >= currentWeek.week,
                        TeamStarted.fantasy_team_id == proposalObj.proposer_team_id,
                        TeamStarted.team_number == ownership.team_key,
                    )
                    await session.execute(stmt)
                    offerText += f"{tradeTeam.team_key}"
                    if i < teamsInTradeCount:
                        offerText += ", "
                    else:
                        offerText += "\n"
                    i += 1
                requestTeamText = f"**{proposalObj.proposed_to_team.fantasy_team_name} is sending the following teams in return:**\n"
                # Validate that the proposed-to team owns the requested teams
                i = 1
                for tradeTeam in requestedTeamsList:
                    stmt = select(TeamOwned).where(
                        TeamOwned.team_key == tradeTeam.team_key,
                        TeamOwned.fantasy_team_id == fantasyId,
                    )
                    result = await session.execute(stmt)
                    ownership = result.scalars().first()
                    if not ownership:
                        await message.edit(
                            content=f"Team {tradeTeam.team_key} is no longer owned by the proposed-to team."
                        )
                        return
                    ownership.fantasy_team_id = proposalObj.proposer_team_id
                    await session.flush()
                    stmt = delete(TeamStarted).where(
                        TeamStarted.week >= currentWeek.week,
                        TeamStarted.fantasy_team_id == proposalObj.proposed_to_team_id,
                        TeamStarted.team_number == ownership.team_key,
                    )
                    await session.execute(stmt)
                    requestTeamText += f"{tradeTeam.team_key}"
                    if i < teamsInTradeCount:
                        requestTeamText += ", "
                    else:
                        requestTeamText += "\n"
                    i += 1
                stmt = delete(TradeTeams).where(TradeTeams.trade_id == tradeId)
                await session.execute(stmt)
                await session.flush()
                stmt = delete(TradeProposal).where(
                    TradeProposal.proposed_to_team_id == fantasyId,
                    TradeProposal.trade_id == tradeId,
                )
                await session.execute(stmt)
                await session.commit()
                tradeConfirmedEmbed.description += offerText + requestTeamText
                await interaction.channel.send(embed=tradeConfirmedEmbed)
            else:
                await message.edit(
                    content=f"You did not have a pending proposal with id {tradeId}."
                )

    @app_commands.command(
        name="viewteam",
        description="View a fantasy team and when their FRC teams compete",
    )
    async def viewATeam(self, interaction: discord.Interaction, fantasyteam: int):
        await interaction.response.send_message("Collecting fantasy team board")
        await self.postTeamBoard(interaction, fantasyteam)

    @app_commands.command(
        name="myteam",
        description="View your fantasy team and when their FRC teams compete",
    )
    async def viewMyTeam(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Collecting fantasy team board", ephemeral=True
        )
        teamId = await self.getFantasyTeamIdFromInteraction(interaction=interaction)
        if not teamId == None:
            await self.postTeamBoard(interaction, teamId)
        else:
            message = await interaction.original_response()
            await message.edit(content="You are not part of any team in this league!")

    @app_commands.command(
        name="start", description="Put team in starting lineup for week"
    )
    async def startTeam(
        self, interaction: discord.Interaction, week: int, frcteam: str
    ):
        await interaction.response.send_message(
            f"Attempting to place {frcteam} in starting lineup.", ephemeral=True
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.startTeamTask(
                interaction=interaction, week=week, frcteam=frcteam, fantasyId=teamId
            )

    @app_commands.command(
        name="sit", description="Remove team from starting lineup for week"
    )
    async def sitTeam(self, interaction: discord.Interaction, week: int, frcteam: str):
        await interaction.response.send_message(
            f"Attempting to remove {frcteam} from starting lineup.", ephemeral=True
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.sitTeamTask(
                interaction=interaction, week=week, frcteam=frcteam, fantasyId=teamId
            )

    @app_commands.command(
        name="setlineup", description="Set entire lineup with comma-separated team list"
    )
    async def setLineup(self, interaction: discord.Interaction, week: int, lineup: str):
        await interaction.response.send_message("Setting lineup...", ephemeral=True)
        team_id = await self.getFantasyTeamIdFromInteraction(interaction)
        if team_id is None:
            msg = await interaction.original_response()
            await msg.edit(content="You are not in this league!")
            return
        team_list = [t.strip() for t in lineup.split(",") if t.strip()]
        await self.setLineupTask(interaction, week, team_list, team_id)

    @app_commands.command(
        name="addusertoteam", description="Add an authorized user to your fantasy team"
    )
    async def authorizeUser(self, interaction: discord.Interaction, user: discord.User):
        if await self.bot.verifyTeamMember(interaction, interaction.user):
            async with self.bot.async_session() as session:
                stmt = select(Player).where(Player.user_id == str(user.id))
                result = await session.execute(stmt)
                player = result.scalars().first()
                if player is None:
                    session.add(Player(user_id=user.id, is_admin=False))
                    await session.commit()
                if await self.bot.verifyTeamMember(interaction, user):
                    await interaction.response.send_message(
                        "You can't add someone already on your team!"
                    )
                elif not await self.bot.verifyNotInLeague(interaction, user):
                    await interaction.response.send_message(
                        "You can't add someone who is already in another team in the league!"
                    )
                else:
                    fantasyteamid = await self.getFantasyTeamIdFromInteraction(
                        interaction
                    )
                    if fantasyteamid is None:
                        await interaction.response.send_message(
                            "Could not find your fantasy team."
                        )
                        return
                    authorizeToAdd = PlayerAuthorized(
                        fantasy_team_id=fantasyteamid, player_id=user.id
                    )
                    session.add(authorizeToAdd)
                    await session.commit()
                    stmt = select(FantasyTeam).where(
                        FantasyTeam.fantasy_team_id == fantasyteamid
                    )
                    result = await session.execute(stmt)
                    fantasyTeam = result.scalars().first()
                    await interaction.response.send_message(
                        f"Successfully added <@{user.id}> to {fantasyTeam.fantasy_team_name}!"
                    )
        else:
            await interaction.response.send_message(
                "You are not part of any team in this league!"
            )

    @app_commands.command(name="rename", description="Rename your fantasy team!")
    async def renameTeam(self, interaction: discord.Interaction, newname: str):
        await interaction.response.send_message(
            f"Attempting to rename team to {newname}"
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        elif self.isEnglish(newname):
            await self.renameTeamTask(interaction, newname, teamId)
        else:
            await originalResponse.edit(content="Invalid team name.")
            return

    @app_commands.command(
        name="adddrop", description="Add/drop a team to/from your roster!"
    )
    async def addDrop(
        self, interaction: discord.Interaction, addteam: str, dropteam: str
    ):
        await interaction.response.send_message(
            f"Attempting to drop {dropteam} to add {addteam}", ephemeral=True
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.addDropTeamTask(
                interaction, addTeam=addteam, dropTeam=dropteam, fantasyId=teamId
            )

    @app_commands.command(name="lineup", description="View your starting lineups")
    async def startingLineups(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Retrieving starting lineups...", ephemeral=True
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.viewStartsTask(interaction, teamId)

    @app_commands.command(
        name="claim", description="Make a waiver claim (only shown to you)"
    )
    async def makeWaiverClaim(
        self, interaction: discord.Interaction, teamtoclaim: str, teamtodrop: str
    ):
        await interaction.response.send_message(
            f"Attempting to make a claim for team {teamtoclaim}, dropping {teamtodrop}",
            ephemeral=True,
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.makeWaiverClaimTask(interaction, teamId, teamtoclaim, teamtodrop)

    @app_commands.command(
        name="myclaims", description="View your waiver claims (only shown to you)"
    )
    async def viewMyClaims(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Retrieving your claims", ephemeral=True
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.viewMyClaimsTask(interaction, teamId)

    @app_commands.command(
        name="cancelclaim", description="Cancel an active claim (only shown to you)"
    )
    async def cancelClaim(self, interaction: discord.Interaction, priority: int):
        await interaction.response.send_message(
            f"Attempting to cancel claim with priority {priority}", ephemeral=True
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.cancelClaimTask(interaction, teamId, priority)

    @app_commands.command(
        name="proposetrade", description="Propose a trade to another team (use team id)"
    )
    async def proposeTrade(
        self,
        interaction: discord.Interaction,
        otherfantasyid: int,
        offered_teams: str,
        requested_teams: str,
    ):
        await interaction.response.send_message(
            "Building trade proposal...", ephemeral=True
        )
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.createTradeProposalTask(
                interaction, teamId, otherfantasyid, offered_teams, requested_teams
            )

    @app_commands.command(name="decline", description="Decline a trade")
    async def declineTrade(self, interaction: discord.Interaction, tradeid: int):
        await interaction.response.send_message("Declining trade...", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.declineTradeTask(interaction, teamId, tradeid)

    @app_commands.command(name="accept", description="Accept a trade proposal")
    async def acceptTrade(self, interaction: discord.Interaction, tradeid: int):
        await interaction.response.send_message("Accepting trade...", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.acceptTradeTask(interaction, teamId, tradeid)


async def setup(bot: commands.Bot) -> None:
    cog = ManageTeam(bot)
    guild = await bot.fetch_guild(int(os.getenv("GUILD_ID")))
    assert guild is not None

    await bot.add_cog(cog, guilds=[guild])
