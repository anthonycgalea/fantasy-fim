import discord, sqlalchemy
from discord import app_commands, Embed
from discord.ext import commands
import logging
import os
from models.scores import *
from models.users import Player
from models.transactions import WaiverClaim, TeamOnWaivers, WaiverPriority, TradeProposal, TradeTeams
from models.draft import Draft
from sqlalchemy import delete
from sqlalchemy.sql import text
from datetime import datetime, timedelta

logger = logging.getLogger('discord')
STATESWEEK = 6
STATESEXTRA = 1
MAXSTARTS = 2

class ManageTeam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    def isEnglish(self, s):
        try:
            s.encode(encoding='utf-8').decode('ascii')
        except UnicodeDecodeError:
            return False
        else:
            return True

    async def getWaiverClaimPriority(self, fantasyId):
        session = await self.bot.get_session()
        waiverprio = session.query(WaiverClaim).filter(WaiverClaim.fantasy_team_id==fantasyId).order_by(WaiverClaim.priority.desc()).first()
        if not waiverprio:
            return 1
        else:
            return waiverprio.priority + 1            

    async def postTeamBoard(self, interaction: discord.Interaction, fantasyTeam: int):
        session = await self.bot.get_session()
        message = await interaction.original_response()
        fantasyTeamResult = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyTeam)
        if (fantasyTeamResult.count() == 0):
            await message.edit(content="Invalid team id")
            return
        fTeamFirst: FantasyTeam = fantasyTeamResult.first()
        teamBoardEmbed = Embed(title=f"**{fTeamFirst.fantasy_team_name} Week-by-Week board**", description="```")
        teamBoardEmbed.description += f"{'Team':^4s}{'':1s}{'Week 1':^9s}{'':1s}{'Week 2':^9s}{'':1s}{'Week 3':^9s}{'':1s}{'Week 4':^9s}{'':1s}{'Week 5':^9}\n"
        teamsOwned = session.query(TeamOwned).filter(TeamOwned.fantasy_team_id==fantasyTeam).order_by(TeamOwned.team_key.asc())
        for team in teamsOwned.all():
            teamEvents = (
                session.query(TeamScore)
                .filter(
                    TeamScore.team_key == team.team_key,
                    TeamScore.event.has(FRCEvent.year == fTeamFirst.league.year)
                )
            )
            weeks = ["---" for k in range(5)]
            for event in teamEvents.all():
                frcEvent = session.query(FRCEvent).filter(FRCEvent.event_key==event.event_key).first()
                if int(frcEvent.week) < STATESWEEK:
                    if (weeks[int(frcEvent.week)-1] == "---"):
                        weeks[int(frcEvent.week)-1] = event.event_key
                    else:
                        weeks[int(frcEvent.week)-1] = "2 Events"
            teamBoardEmbed.description+=f"{team.team_key:>4s}{'':1s}{weeks[0]:^9s}{'':1s}{weeks[1]:^9s}{'':1s}{weeks[2]:^9s}{'':1s}{weeks[3]:^9s}{'':1s}{weeks[4]:^9}\n"
        teamBoardEmbed.description += "```"
        await message.edit(embed=teamBoardEmbed, content="")
        session.close()

    async def getFantasyTeamIdFromInteraction(self, interaction: discord.Interaction):
        session = await self.bot.get_session()
        largeQuery = session.query(FantasyTeam)\
            .join(PlayerAuthorized, FantasyTeam.fantasy_team_id == PlayerAuthorized.fantasy_team_id)\
            .join(League, FantasyTeam.league_id == League.league_id)\
            .filter(PlayerAuthorized.player_id == str(interaction.user.id))\
            .filter(League.discord_channel == str(interaction.channel_id))
        team = largeQuery.first()
        session.close()
        if team:
            return team.fantasy_team_id
        else:
            return None

    async def startTeamTask(self, interaction: discord.Interaction, frcteam: str, week: int, fantasyId: int):
        deferred = await interaction.original_response()
        session = await self.bot.get_session()
        fantasyteam: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        league: League = session.query(League).filter(League.league_id==fantasyteam.league_id).first()
        #is this a fim season long league?
        if (not league.is_fim):
            await deferred.edit(content="This league does not support starts/sits.")
            session.close()
            return
        
        # Check if lineups are locked for the given week in this league
        week_status = session.query(WeekStatus)\
            .filter(WeekStatus.year == league.year)\
            .filter(WeekStatus.week == week).first()

        if week_status and week_status.lineups_locked:
            await deferred.edit(content="Lineups are locked for this week, you cannot modify your lineup at this time.")
            session.close()
            return
        #do you own the team?
        teamowned = session.query(TeamOwned)\
                .filter(TeamOwned.team_key==frcteam)\
                .filter(TeamOwned.league_id==league.league_id)\
                .filter(TeamOwned.fantasy_team_id==fantasyId)
        if (teamowned.count() == 0):
            await deferred.edit(content="You do not own this team.")
            session.close()
            return
        teamsStartedRecords = session.query(TeamStarted).filter(TeamStarted.fantasy_team_id==fantasyId).filter(TeamStarted.week==week)
        if ((league.team_starts <= teamsStartedRecords.count() and week < STATESWEEK) or (league.team_starts + STATESEXTRA <= teamsStartedRecords.count() and week == STATESWEEK)):
            await deferred.edit(content="Already starting max number of teams this week.")
        else:
            #get frc events in fim this week
            frcevents = session.query(FRCEvent).filter(FRCEvent.year==league.year).filter(FRCEvent.week==week).filter(FRCEvent.is_fim==True)
            eventList = [event.event_key for event in frcevents.all()]
            #does team compete in fim this week?
            teamcompeting = session.query(TeamScore).filter(TeamScore.team_key==frcteam)\
                .filter(TeamScore.event_key.in_(eventList))
            #is your team already starting?
            alreadyStarting = teamsStartedRecords.filter(TeamStarted.team_number==frcteam).count()
            #has your team been started twice this year already?
            teamStartedCount = session.query(TeamStarted)\
                .filter(TeamStarted.league_id==league.league_id)\
                .filter(TeamStarted.team_number==frcteam)\
                .filter(TeamStarted.week < STATESWEEK)
            if (teamcompeting.count() == 0):
                await deferred.edit(content="This team is not competing this week!")
            elif (teamcompeting.count() > 1):
                await deferred.edit(content="Please contact a fantasy admin to start your team. They are competing at multiple FiM events this week which is a special case.")
            elif (alreadyStarting > 0):
                await deferred.edit(content="This team is already starting this week!")
            elif (not week == STATESWEEK and teamStartedCount.count() >= MAXSTARTS):
                await deferred.edit(content=f"This team may not be started again until States, they have reached the maximum of {MAXSTARTS}")
            else:
                eventkey = teamcompeting.first().event_key
                frcevent: FRCEvent = session.query(FRCEvent).filter(FRCEvent.event_key==eventkey).first()
                teamStartedToAdd = TeamStarted(fantasy_team_id=fantasyId, team_number=frcteam, league_id=league.league_id, event_key=eventkey, week=week)
                session.add(teamStartedToAdd)
                session.commit()
                await deferred.edit(content=f"{fantasyteam.fantasy_team_name} is starting team {frcteam} competing at {frcevent.event_name} in week {week}!")
        session.close()

    async def sitTeamTask(self, interaction: discord.Interaction, frcteam: str, week: int, fantasyId: int):
        deferred = await interaction.original_response()
        session = await self.bot.get_session()
        fantasyteam: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        league: League = session.query(League).filter(League.league_id==fantasyteam.league_id).first()
        #is this a fim season long league?
        if (not league.is_fim):
            await deferred.edit(content="This league does not support starts/sits.")
            session.close()
            return
        
        # Check if lineups are locked for the given week in this league
        week_status = session.query(WeekStatus)\
            .filter(WeekStatus.year == league.year)\
            .filter(WeekStatus.week == week).first()

        if week_status and week_status.lineups_locked:
            await deferred.edit(content="Lineups are locked for this week, you cannot modify your lineup at this time.")
            session.close()
            return
        
        #is this team actually starting for you?
        teamstarted = session.query(TeamStarted)\
                .filter(TeamStarted.team_number==frcteam)\
                .filter(TeamStarted.league_id==league.league_id)\
                .filter(TeamStarted.fantasy_team_id==fantasyId)\
                .filter(TeamStarted.week==week)
        if (teamstarted.count() == 0):
            await deferred.edit(content="You are not currently starting this team.")
        elif (teamstarted.count() > 1):
            await deferred.edit(content="Please contact a fantasy admin to sit your team. You are starting them at multiple FiM events this week which is a special case.")
        else:
            event: FRCEvent = teamstarted.first().event
            teamstarted.delete()
            session.commit()
            await deferred.edit(content=f"{fantasyteam.fantasy_team_name} is sitting team {frcteam} competing at {event.event_name} in week {week}.")
        session.close()

    async def setLineupTask(self, interaction: discord.Interaction, week: int, teams: list[str], fantasyId: int):
        deferred = await interaction.original_response()
        session = await self.bot.get_session()
        fantasyteam: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        league: League = session.query(League).filter(League.league_id==fantasyteam.league_id).first()
        # is this a fim season long league?
        if (not league.is_fim):
            await deferred.edit(content="This league does not support starts/sits.")
            session.close()
            return

        # Check if lineups are locked for the given week in this league
        week_status = session.query(WeekStatus)\
            .filter(WeekStatus.year == league.year)\
            .filter(WeekStatus.week == week).first()

        if week_status and week_status.lineups_locked:
            await deferred.edit(content="Lineups are locked for this week, you cannot modify your lineup at this time.")
            session.close()
            return

        # remove all existing starts for this week
        session.query(TeamStarted)\
            .filter(TeamStarted.league_id==league.league_id)\
            .filter(TeamStarted.fantasy_team_id==fantasyId)\
            .filter(TeamStarted.week==week).delete()
        session.commit()

        # start each team provided
        for team in teams:
            await self.startTeamTask(interaction, frcteam=team, week=week, fantasyId=fantasyId)

        session.close()

    async def renameTeamTask(self, interaction: discord.Interaction, newname: str, fantasyId: int):
        deferred = await interaction.original_response()
        session = await self.bot.get_session()
        fantasyteam: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        oldname = fantasyteam.fantasy_team_name
        fantasyteam.fantasy_team_name=newname
        session.commit()
        await deferred.edit(content=f"Team **{oldname}** renamed to **{newname}** (Team id {fantasyteam.fantasy_team_id})")
        session.close()

    async def viewStartsTask(self, interaction: discord.Interaction, fantasyId: int):
        session = await self.bot.get_session()
        # retrieve league starts data
        fantasyteam: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        league: League = fantasyteam.league
        teamsToStart = league.team_starts
        #retrieve teamstarted for team
        teamsStarted = session.query(TeamStarted).filter(TeamStarted.fantasy_team_id==fantasyId)
        # for every week
        embed = Embed(title=f"**{fantasyteam.fantasy_team_name} Starting Lineups**", description=f"```{'':^8s}")
        for team in range(1, teamsToStart+STATESEXTRA+1):
            if team>league.team_starts:
                embed.description += f"{f'Team {team}':^7s}\n"
            else:
                embed.description += f"{f'Team {team}':^7s}{'':2s}"
        for week in range(1,STATESWEEK+1):
            # grab every started team and fill in embed
            weekTeamsStarted = teamsStarted.filter(TeamStarted.week==week).all()
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
            embed.description+=f"{f'Week {week}':^8s}"
            for k in range(teamsToStart+STATESEXTRA):
                if k+1 > teamsToStart:
                    embed.description+=f"{lineToAdd[k]:^7s}\n"
                else:
                    embed.description+=f"{lineToAdd[k]:^7s}{'':2s}"
        # send embed
        response = await interaction.original_response()
        embed.description+="```"
        await response.edit(embed=embed, content="")
        session.close()

    async def viewMyClaimsTask(self, interaction: discord.Interaction, fantasyId: int):
        session = await self.bot.get_session()
        # retrieve waiver claim data
        response = await interaction.original_response()
        waiverClaims = session.query(WaiverClaim).filter(WaiverClaim.fantasy_team_id==fantasyId).order_by(WaiverClaim.priority.asc())
        if waiverClaims.count() == 0:
            await response.edit(content="You currently have no active claims.")
            return
        waiverPriority: WaiverPriority = session.query(WaiverPriority).filter(WaiverPriority.fantasy_team_id==fantasyId).first()
        embed = Embed(title=f"**Waiver Claims - Team Priority: {waiverPriority.priority}**", description=f"```{'Priority':^12s}{'Claimed Team':^16s}{'Team to drop':^16s}\n")
        for claim in waiverClaims.all():
            embed.description+=f"{claim.priority:^12d}{claim.team_claimed:^16s}{claim.team_to_drop:^16s}\n"
        embed.description+="```"
        await response.edit(embed=embed, content="")
        session.close()

    async def addDropTeamTask(self, interaction: discord.Interaction, addTeam: str, dropTeam: str, fantasyId: int, force: bool = False, toWaivers: bool = True):
        session = await self.bot.get_session()
        message = await interaction.original_response()
        currentWeek = await self.bot.getCurrentWeek()
        if currentWeek.lineups_locked == True:
            await message.edit(content="Cannot make transaction with locked lineups.")
            return
        #check if own dropTeam
        teamDropOwned = session.query(TeamOwned)\
            .filter(TeamOwned.team_key==str(dropTeam))\
            .filter(TeamOwned.fantasy_team_id==fantasyId)
        fantasyTeam: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        teamsOnWaivers = session.query(TeamOnWaivers).filter(TeamOnWaivers.team_number==str(addTeam)).filter(TeamOnWaivers.league_id==fantasyTeam.league_id) #on waivers
        teamAddOwnedByOther = session.query(TeamOwned).filter(TeamOwned.league_id==fantasyTeam.league_id).filter(TeamOwned.team_key==str(addTeam)) #on team already
        teamInFiM = session.query(Team).filter(Team.team_number==str(addTeam)).filter(Team.is_fim==True) #is in fim
        if (teamDropOwned.count() == 0):
            await message.edit(content="You do not own the team you are attempting to drop!")
        elif (teamsOnWaivers.count() > 0 and not force):
            await message.edit(content="Team is on waivers. Please submit a claim instead.")
        elif (teamAddOwnedByOther.count() > 0):
            await message.edit(content="This team is already owned.")
        elif (teamInFiM.count() == 0):
            await message.edit(content="This team is not in FiM.")
        else:
            if toWaivers:
                newWaiver = TeamOnWaivers(league_id=fantasyTeam.league_id, team_number=dropTeam)
                session.add(newWaiver)
            if force:
                session.query(TeamOnWaivers).filter(TeamOnWaivers.team_number==str(addTeam)).filter(TeamOnWaivers.league_id==fantasyTeam.league_id).delete()
                session.flush()
            session.query(TeamStarted).filter(TeamStarted.league_id==fantasyTeam.league_id)\
            .filter(TeamStarted.team_number==dropTeam).filter(TeamStarted.week >= currentWeek.week).delete()
            session.flush()
            session.query(TeamOwned).filter(TeamOwned.league_id==fantasyTeam.league_id).filter(TeamOwned.team_key==dropTeam).delete()
            draftSoNotFail: Draft = session.query(Draft).filter(Draft.league_id==fantasyTeam.league_id).filter(Draft.event_key=="2025fim").first()
            session.flush()
            newTeamToAdd = TeamOwned(
                team_key=str(addTeam),
                fantasy_team_id=fantasyId,
                league_id=fantasyTeam.league_id,
                draft_id=draftSoNotFail.draft_id
            )
            session.add(newTeamToAdd)
            session.flush()  # Try flushing to see if the error occurs here
            await message.channel.send(content=f"{fantasyTeam.fantasy_team_name} successfully added team {addTeam} and dropped {dropTeam}!")
            session.commit()
        #add addTeam
        session.close()

    async def makeWaiverClaimTask(self, interaction: discord.Interaction, fantasyId: int, addTeam: str, dropTeam: str):
        session = await self.bot.get_session()
        #get original message to edit
        originalMessage = await interaction.original_response()
        #check if addTeam is on waivers
        fantasyTeam: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        teamsOnWaivers = session.query(TeamOnWaivers).filter(TeamOnWaivers.team_number==addTeam).filter(TeamOnWaivers.league_id==fantasyTeam.league_id)
        teamowned = session.query(TeamOwned)\
                .filter(TeamOwned.team_key==dropTeam)\
                .filter(TeamOwned.fantasy_team_id==fantasyId)
        waiverClaimAlreadyMade = session.query(WaiverClaim)\
                .filter(WaiverClaim.fantasy_team_id==fantasyId)\
                .filter(WaiverClaim.team_claimed==addTeam)\
                .filter(WaiverClaim.team_to_drop==dropTeam)
        if (teamsOnWaivers.count() == 0):
            await originalMessage.edit(content=f"Team {addTeam} is not on waivers!")
        #check if own dropTeam
        elif (teamowned.count() == 0):
            await originalMessage.edit(content=f"You do not own team {dropTeam}.")
        #check if already made exact waiver claim
        elif (waiverClaimAlreadyMade.count() > 0):
            await originalMessage.edit(content=f"You have already made this claim!")
        #create waiver claim
        else:
            newPriority = await self.getWaiverClaimPriority(fantasyId)
            waiverClaim = WaiverClaim(fantasy_team_id=fantasyId,\
                                      league_id=fantasyTeam.league_id, team_claimed=addTeam,\
                                        team_to_drop=dropTeam, priority=newPriority)
            session.add(waiverClaim)
            await originalMessage.edit(content=f"Successfully created claim for {addTeam}!")
            session.commit()
        #close session
        session.close()

    async def cancelClaimTask(self, interaction: discord.Interaction, fantasyId: int, priority: int):
        session = await self.bot.get_session()
        #get original message to edit
        originalMessage = await interaction.original_response()
        #check if claim id exists
        waiverClaimExists = session.query(WaiverClaim)\
                .filter(WaiverClaim.fantasy_team_id==fantasyId)\
                .filter(WaiverClaim.priority>=priority)
        
        if (waiverClaimExists.filter(WaiverClaim.priority==priority).count() == 0):
            await originalMessage.edit(content=f"You do not have a claim with this priority!")
        #create waiver claim
        else:
            claimToCancel = waiverClaimExists.first()
            addTeam = claimToCancel.team_claimed
            dropTeam = claimToCancel.team_to_drop
            waiverClaimExists.filter(WaiverClaim.priority==priority).delete()
            claimsToShift = waiverClaimExists.filter(WaiverClaim.priority>priority).all()
            for claim in claimsToShift:
                claim.priority-=1
            await originalMessage.edit(content=f"Successfully canceled claim for {addTeam} which was dropping {dropTeam}")
            session.commit()
        #close session
        session.close()

    async def createTradeProposalTask(self, interaction: discord.Interaction, fantasyId: int, otherFantasyId: int, teamsOffered: str, teamsRequested: str, force: bool = False) -> TradeProposal:
        session = await self.bot.get_session()
        originalMessage = await interaction.original_response()
        # Check if lineups are locked for the given week in this league
        week_status = await self.bot.getCurrentWeek()

        if week_status and week_status.lineups_locked:
            await originalMessage.edit(content="Lineups are locked for this week, you cannot modify your lineup at this time.")
            session.close()
            return
        proposer_team: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==fantasyId).first()
        proposed_to_team: FantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id==otherFantasyId)\
            .filter(FantasyTeam.league_id==proposer_team.league_id).first()
        if not proposer_team and not proposed_to_team:
            await originalMessage.edit(content=f"Invalid fantasy team ID provided.")
            return
        expiration_time = datetime.now() + timedelta(hours=1)

        new_trade = TradeProposal(
            league_id=proposer_team.league_id,
            proposer_team_id=fantasyId,
            proposed_to_team_id=otherFantasyId,
            expiration=expiration_time
        )
        session.add(new_trade)
        session.flush()
        offeredTeamsList = [team.strip() for team in teamsOffered.split(',')]
        requestedTeamsList = [team.strip() for team in teamsRequested.split(',')]

        if not len(offeredTeamsList) == len(requestedTeamsList):
            await originalMessage.edit(content="Must offer the exact same amount of teams.")
            session.close()
            return

        tradeProposalEmbed = Embed(title="**Trade Proposal Alert!**", description="")
        offerText = f"**{proposer_team.fantasy_team_name} is offering the following teams:**\n"
        teamsInTradeCount = len(offeredTeamsList)
        i = 1
        # Validate that the proposer owns the offered teams
        for team_key in offeredTeamsList:
            ownership = session.query(TeamOwned).filter_by(team_key=team_key, fantasy_team_id=fantasyId).first()
            if not ownership:
                await originalMessage.edit(content=f"Team {team_key} is not owned by the proposer.")
                return
            new_trade_team = TradeTeams(
                trade_id=new_trade.trade_id,
                team_key=team_key,
                is_offered=True
            )
            offerText+=f"{team_key}"
            if (i < teamsInTradeCount):
                offerText+=", "
            else:
                offerText+="\n"
            session.add(new_trade_team)
            i+=1
        requestTeamText = f"**{proposed_to_team.fantasy_team_name} would send in return the following teams:**\n"
        # Validate that the proposed-to team owns the requested teams
        i=1
        for team_key in requestedTeamsList:
            ownership = session.query(TeamOwned).filter_by(team_key=team_key, fantasy_team_id=otherFantasyId).first()
            if not ownership:
                await originalMessage.edit(content=f"Team {team_key} is not owned by the proposed-to team.")
                return
            new_trade_team = TradeTeams(
                trade_id=new_trade.trade_id,
                team_key=team_key,
                is_offered=False
            )
            requestTeamText+=f"{team_key}"
            if (i < teamsInTradeCount):
                requestTeamText+=", "
            else:
                requestTeamText+="\n"
            session.add(new_trade_team)
            i+=1
        acceptText=f"**If you wish to accept, use command `/accept {new_trade.trade_id}` within 1 hour.**\n"
        declineText=f"*If you wish to decline, use command `/decline {new_trade.trade_id}`.*\n"
        tradeProposalEmbed.description+=offerText+requestTeamText+acceptText+declineText
        #add notifs for other team
        playersToNotif = session.query(PlayerAuthorized).filter(PlayerAuthorized.fantasy_team_id==otherFantasyId)
        notifText = ""
        for player in playersToNotif.all():
            notifText += f"<@{player.player_id}> "
        if not force:
            await interaction.channel.send(embed=tradeProposalEmbed, content=notifText)
        # Commit all the teams involved in the trade
        session.commit()
        tradeProp = session.query(TradeProposal).filter(TradeProposal.trade_id==new_trade.trade_id).first()
        session.close() 
        if force:
            return tradeProp

    async def declineTradeTask(self, interaction: discord.Interaction, fantasyId: int, tradeId: int):
        session = await self.bot.get_session()
        message = await interaction.original_response()
        tradeProposal = session.query(TradeProposal).filter(TradeProposal.proposed_to_team_id==fantasyId).filter(TradeProposal.trade_id==tradeId)
        if tradeProposal.count() > 0:
            session.query(TradeTeams).filter(TradeTeams.trade_id==tradeId).delete()
            session.flush()
            tradeProposal.delete()
            session.commit()
            await interaction.channel.send(f"Trade proposal {tradeId} declined.")
        else:
            await message.edit(content=f"You did not have a pending proposal with id {tradeId}.")
        session.close()

    async def acceptTradeTask(self, interaction: discord.Interaction, fantasyId: int, tradeId: int, force:bool = False):
        session = await self.bot.get_session()
        message = await interaction.original_response()
        tradeProposal = session.query(TradeProposal).filter(TradeProposal.proposed_to_team_id==fantasyId).filter(TradeProposal.trade_id==tradeId)
        proposalObj = tradeProposal.first()
        currentWeek = await self.bot.getCurrentWeek()
        if (currentWeek.lineups_locked == True and not force):
            await message.edit("Cannot accept a trade while lineups are locked!")
            return
        if force or tradeProposal.count() > 0:
            offeredTeamsList = session.query(TradeTeams).filter(TradeTeams.trade_id==tradeId).filter(TradeTeams.is_offered==True).all()
            requestedTeamsList = session.query(TradeTeams).filter(TradeTeams.trade_id==tradeId).filter(TradeTeams.is_offered==False).all()
            #add trade transaction logic
            # Validate that the proposer owns the offered teams
            tradeConfirmedEmbed = Embed(title="**Trade Alert!**", description="")
            offerText = f"**{proposalObj.proposer_team.fantasy_team_name} is sending the following teams:**\n"
            teamsInTradeCount = len(offeredTeamsList)
            i = 1
            for tradeTeam in offeredTeamsList:
                ownership = session.query(TeamOwned).filter(TeamOwned.team_key==tradeTeam.team_key).filter(TeamOwned.fantasy_team_id==proposalObj.proposer_team_id).first()
                if not ownership:
                    await message.edit(content=f"Team {tradeTeam.team_key} is no longer owned by the proposer.")
                    return
                ownership.fantasy_team_id=proposalObj.proposed_to_team_id
                session.flush()
                session.query(TeamStarted).filter(TeamStarted.week>=currentWeek.week)\
                    .filter(TeamStarted.fantasy_team_id==proposalObj.proposer_team_id)\
                    .filter(TeamStarted.team_number==ownership.team_key)\
                        .delete()
                offerText+=f"{tradeTeam.team_key}"
                if (i < teamsInTradeCount):
                    offerText+=", "
                else:
                    offerText+="\n"
                i+=1
            requestTeamText = f"**{proposalObj.proposed_to_team.fantasy_team_name} is sending the following teams in return:**\n"
            # Validate that the proposed-to team owns the requested teams
            i=1
            for tradeTeam in requestedTeamsList:
                ownership = session.query(TeamOwned).filter(TeamOwned.team_key==tradeTeam.team_key).filter(TeamOwned.fantasy_team_id==fantasyId).first()
                if not ownership:
                    await message.edit(content=f"Team {tradeTeam.team_key} is no longer owned by the proposed-to team.")
                    return
                ownership.fantasy_team_id=proposalObj.proposer_team_id
                session.flush()
                session.query(TeamStarted).filter(TeamStarted.week>=currentWeek.week)\
                    .filter(TeamStarted.fantasy_team_id==proposalObj.proposed_to_team_id)\
                    .filter(TeamStarted.team_number==ownership.team_key)\
                    .delete()
                requestTeamText+=f"{tradeTeam.team_key}"
                if (i < teamsInTradeCount):
                    requestTeamText+=", "
                else:
                    requestTeamText+="\n"
                i+=1
            session.query(TradeTeams).filter(TradeTeams.trade_id==tradeId).delete()
            session.flush()
            tradeProposal.delete()
            session.commit()
            tradeConfirmedEmbed.description+=offerText+requestTeamText
            await interaction.channel.send(embed=tradeConfirmedEmbed)
        else:
            await message.edit(content=f"You did not have a pending proposal with id {tradeId}.")
        session.close()

    @app_commands.command(name="viewteam", description="View a fantasy team and when their FRC teams compete")
    async def viewATeam(self, interaction: discord.Interaction, fantasyteam: int):
        await interaction.response.send_message("Collecting fantasy team board")
        await self.postTeamBoard(interaction, fantasyteam)

    @app_commands.command(name="myteam", description="View your fantasy team and when their FRC teams compete")
    async def viewMyTeam(self, interaction: discord.Interaction):
        await interaction.response.send_message("Collecting fantasy team board", ephemeral=True)
        teamId = await self.getFantasyTeamIdFromInteraction(interaction=interaction)
        if not teamId == None:
            await self.postTeamBoard(interaction, teamId)
        else:
            message = await interaction.original_response()
            await message.edit(content="You are not part of any team in this league!")

    @app_commands.command(name="start", description="Put team in starting lineup for week")
    async def startTeam(self, interaction: discord.Interaction, week: int, frcteam: str):
        await interaction.response.send_message(f"Attempting to place {frcteam} in starting lineup.", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.startTeamTask(interaction=interaction, week=week, frcteam=frcteam, fantasyId=teamId)

    @app_commands.command(name="sit", description="Remove team from starting lineup for week")
    async def sitTeam(self, interaction: discord.Interaction, week: int, frcteam: str):
        await interaction.response.send_message(f"Attempting to remove {frcteam} from starting lineup.", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.sitTeamTask(interaction=interaction, week=week, frcteam=frcteam, fantasyId=teamId)

    @app_commands.command(name="setlineup", description="Set entire lineup with comma-separated team list")
    async def setLineup(self, interaction: discord.Interaction, week: int, lineup: str):
        await interaction.response.send_message("Setting lineup...", ephemeral=True)
        team_id = await self.getFantasyTeamIdFromInteraction(interaction)
        if team_id is None:
            msg = await interaction.original_response()
            await msg.edit(content="You are not in this league!")
            return
        team_list = [t.strip() for t in lineup.split(',') if t.strip()]
        await self.setLineupTask(interaction, week, team_list, team_id)

    @app_commands.command(name="addusertoteam", description="Add an authorized user to your fantasy team")
    async def authorizeUser(self, interaction: discord.Interaction, user: discord.User):
        if await self.bot.verifyTeamMember(interaction, interaction.user):
            session = await self.bot.get_session()
            player = session.query(Player).filter(Player.user_id == str(user.id))
            if player.count() == 0:
                session.add(Player(user_id=user.id, is_admin=False))
                session.commit()
            if await self.bot.verifyTeamMember(interaction, user):
                session.close()
                await interaction.response.send_message("You can't add someone already on your team!")
            elif not await self.bot.verifyNotInLeague(interaction, user):
                session.close()
                await interaction.response.send_message("You can't add someone who is already in another team in the league!")
            else:
                fantasyteamid = await self.getFantasyTeamIdFromInteraction(interaction)
                if fantasyteamid is None:
                    session.close()
                    await interaction.response.send_message("Could not find your fantasy team.")
                    return
                authorizeToAdd = PlayerAuthorized(fantasy_team_id=fantasyteamid, player_id=user.id)
                session.add(authorizeToAdd)
                session.commit()
                fantasyTeam = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id == fantasyteamid).first()
                await interaction.response.send_message(f"Successfully added <@{user.id}> to {fantasyTeam.fantasy_team_name}!")
            session.close()
        else:
            await interaction.response.send_message("You are not part of any team in this league!")

    @app_commands.command(name="rename", description="Rename your fantasy team!")
    async def renameTeam(self, interaction:discord.Interaction, newname: str):
        await interaction.response.send_message(f"Attempting to rename team to {newname}")
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        elif (self.isEnglish(newname)):
            await self.renameTeamTask(interaction, newname, teamId)
        else:
            await originalResponse.edit(content="Invalid team name.")
            return

    @app_commands.command(name="adddrop", description="Add/drop a team to/from your roster!")
    async def addDrop(self, interaction:discord.Interaction, addteam: str, dropteam: str):
        await interaction.response.send_message(f"Attempting to drop {dropteam} to add {addteam}", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.addDropTeamTask(interaction, addTeam=addteam,dropTeam=dropteam, fantasyId=teamId)

    @app_commands.command(name="lineup", description="View your starting lineups")
    async def startingLineups(self, interaction:discord.Interaction):
        await interaction.response.send_message(f"Retrieving starting lineups...", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.viewStartsTask(interaction, teamId)

    @app_commands.command(name="claim", description="Make a waiver claim (only shown to you)")
    async def makeWaiverClaim(self, interaction:discord.Interaction, teamtoclaim: str, teamtodrop: str):
        await interaction.response.send_message(f"Attempting to make a claim for team {teamtoclaim}, dropping {teamtodrop}", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.makeWaiverClaimTask(interaction, teamId, teamtoclaim, teamtodrop)

    @app_commands.command(name="myclaims", description="View your waiver claims (only shown to you)")
    async def viewMyClaims(self, interaction:discord.Interaction):
        await interaction.response.send_message(f"Retrieving your claims", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.viewMyClaimsTask(interaction, teamId)

    @app_commands.command(name="cancelclaim", description="Cancel an active claim (only shown to you)")
    async def cancelClaim(self, interaction:discord.Interaction, priority: int):
        await interaction.response.send_message(f"Attempting to cancel claim with priority {priority}", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.cancelClaimTask(interaction, teamId, priority)

    @app_commands.command(name="proposetrade", description="Propose a trade to another team (use team id)")
    async def proposeTrade(self, interaction:discord.Interaction, otherfantasyid: int, offered_teams: str, requested_teams: str):
        await interaction.response.send_message("Building trade proposal...", ephemeral=True)
        originalResponse = await interaction.original_response()
        teamId = await self.getFantasyTeamIdFromInteraction(interaction)
        if teamId == None:
            await originalResponse.edit(content="You are not in this league!")
            return
        else:
            await self.createTradeProposalTask(interaction, teamId, otherfantasyid, offered_teams, requested_teams)

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

  await bot.add_cog(
      cog,
    guilds=[guild]
  )