from sqlalchemy import Boolean, ForeignKey, String, Integer, Double
from sqlalchemy.orm import Mapped, mapped_column, relationship
import json
import math
from scipy.special import erfinv
from .base import Base


class Team(Base):
  __tablename__ = "teams"

  team_number: Mapped[str] = mapped_column(primary_key=True)
  name: Mapped[str] = mapped_column(String(255), nullable=False)
  is_fim: Mapped[Boolean] = mapped_column(Boolean(), nullable=False, default=False)
  rookie_year: Mapped[int] = mapped_column(Integer(), nullable=True)

  def __str__(self):
    return str(self.teamnumber) + " " + self.name

class FRCEvent(Base):
  __tablename__ = "frcevent"

  event_key: Mapped[str] = mapped_column(primary_key=True)
  event_name: Mapped[str] = mapped_column(String(255), nullable=False)
  year: Mapped[int] = mapped_column(Integer(), nullable=False)
  week: Mapped[int] = mapped_column(Integer(), nullable=False)
  is_fim: Mapped[bool] = mapped_column(Boolean(), nullable=False)

  def __str__(self):
    return self.eventname

class TeamScore(Base):
  __tablename__ = "teamscore"
  team_key: Mapped[str] = mapped_column(ForeignKey("teams.team_number"), primary_key=True)
  event_key: Mapped[str] = mapped_column(ForeignKey("frcevent.event_key"), primary_key=True)
  qual_points: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
  alliance_points: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
  elim_points: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
  award_points: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
  rookie_points: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
  stat_correction: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
  event_finished: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

  team = relationship("Team")
  event = relationship("FRCEvent")

  def score_team(self):
    return self.qual_points+self.alliance_points+self.elim_points+\
    self.award_points+self.rookie_points+self.stat_correction
  
  def __str__(self):
    return str(self.team_key) +" Competing at " + str(self.event_key) +\
    " has scored " + str(self.score_team()) + " points"
  
  def json(self):
    json_data = {}
    json_data["team_key"] = self.team_key
    json_data["event_key"] = self.event_key
    json_data["qual_points"] = self.qual_points
    json_data["alliance_points"] = self.alliance_points
    json_data["elim_points"] = self.elim_points
    json_data["award_points"] = self.award_points
    json_data["rookie_bonus"] = self.rookie_bonus
    json_data["stat_correction"] = self.stat_correction
    json_data["totalScore"] = self.score_team()
    return json.dumps(json_data)
  
  def update_qualification_points(self, rank, numTeams, alpha = 1.07):
    # First, calculate the inner part of the equation
    term1 = (numTeams - 2*rank + 2) / (alpha * numTeams)
    term2 = 10 / erfinv(1 / alpha)
    
    # Combine the terms and calculate the result
    result = (erfinv(term1) * (term2)) + 12
    
    self.qual_points=round(result)
  
  def update_alliance_points(self, pick: int=17): #17 if unpicked
    if pick == None:
      self.alliance_points=0
    else:
      self.alliance_points=17-pick

  def update_elim_points(self, lost_match_12=False,lost_match_13=False, lost_finals: bool = False, won_finals: bool = False):
    points = 0
    if lost_match_12:
      points=7
    elif lost_match_13:
      points=13
    elif lost_finals:
      points=20
    elif won_finals:
      points=30
    self.elim_points=points

class League(Base):
  __tablename__ = "league"
  league_id: Mapped[int] = mapped_column(primary_key=True)
  league_name: Mapped[str] = mapped_column(String(255), nullable=False)
  offseason: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
  team_limit: Mapped[int] = mapped_column(Integer(), nullable=False, default=8)
  team_starts: Mapped[int] = mapped_column(Integer(), nullable=False, default=3)
  is_fim: Mapped[bool] = mapped_column(Boolean(), default=False)
  year: Mapped[int] = mapped_column(Integer(), nullable=False)
  active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
  discord_channel: Mapped[str] = mapped_column(String(30), nullable=False)
  team_size_limit: Mapped[int] = mapped_column(Integer(), nullable=False)

  def __str__(self):
    return self.league_name

class FantasyTeam(Base):
  __tablename__ = "fantasyteam"
  fantasy_team_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
  fantasy_team_name: Mapped[str] = mapped_column(String(255), nullable=False)
  league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"), nullable=False)

  waiver_priority = relationship("WaiverPriority", back_populates="fantasy_team", uselist=False)

  league = relationship("League")

class TeamOwned(Base):
  __tablename__ = "teamowned"
  team_key: Mapped[str] = mapped_column(ForeignKey("teams.team_number"), primary_key=True)
  fantasy_team_id: Mapped[int] = mapped_column(ForeignKey("fantasyteam.fantasy_team_id"),\
                                               primary_key=True)
  league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"),primary_key=True)
  draft_id: Mapped[int] = mapped_column(ForeignKey("draft.draft_id"), primary_key=True)
  
  team = relationship("Team")
  fantasyTeam = relationship("FantasyTeam")
  league = relationship("League")
  draft = relationship("Draft")

  def __str__(self):
    return str(self.team_key) + " is owned by " + str(self.fantasy_team_id) + " in " +\
                                str(self.league_id)

class TeamStarted(Base):
  __tablename__ = "teamstarted"
  fantasy_team_id: Mapped[int] = mapped_column(ForeignKey("fantasyteam.fantasy_team_id"),\
                                            primary_key=True)
  team_number: Mapped[str] = mapped_column(ForeignKey("teams.team_number"), primary_key=True)
  league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"), primary_key=True)
  event_key: Mapped[str] = mapped_column(ForeignKey("frcevent.event_key"), primary_key=True)
  week: Mapped[int] = mapped_column(Integer(), nullable=False, default=0, primary_key=True)

  fantasyTeam = relationship("FantasyTeam")
  team = relationship("Team")
  league = relationship("League")
  event = relationship("FRCEvent")


class PlayerAuthorized(Base):
  __tablename__ = "playerauthorized"
  player_id: Mapped[str] = mapped_column(ForeignKey("players.user_id"),
                                        primary_key=True)
  fantasy_team_id: Mapped[int] = mapped_column(ForeignKey("fantasyteam.fantasy_team_id"), primary_key=True)

  fantasyTeam = relationship("FantasyTeam")

class WeekStatus(Base):
  __tablename__ = "weekstatus"
  year: Mapped[int] = mapped_column(Integer(), primary_key=True)
  week: Mapped[int] = mapped_column(Integer(), primary_key=True)
  lineups_locked: Mapped[bool] = mapped_column(Boolean())
  scores_finalized: Mapped[bool] = mapped_column(Boolean())
  active: Mapped[bool] = mapped_column(Boolean())

class FantasyScores(Base):
  __tablename__ = "fantasyscores"
  league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"), primary_key=True)
  fantasy_team_id: Mapped[int] = mapped_column(ForeignKey("fantasyteam.fantasy_team_id"), primary_key=True)
  week: Mapped[int] = mapped_column(Integer(), primary_key=True)
  event_key: Mapped[int] = mapped_column(String(25), primary_key=True)
  rank_points: Mapped[int] = mapped_column(Double())
  weekly_score: Mapped[int] = mapped_column(Integer())
  
  league = relationship("League")
  fantasyTeam = relationship("FantasyTeam")