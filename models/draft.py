from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Draft(Base):
    __tablename__ = "draft"
    draft_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"))
    event_key: Mapped[int] = mapped_column(ForeignKey("frcevent.event_key"))
    discord_channel: Mapped[str] = mapped_column(String(30))
    rounds: Mapped[int] = mapped_column(Integer(), nullable=False, default=3)

    league = relationship("League")
    event = relationship("FRCEvent")


class DraftOrder(Base):
    __tablename__ = "draftorder"
    fantasy_team_id: Mapped[int] = mapped_column(
        ForeignKey("fantasyteam.fantasy_team_id"), primary_key=True
    )
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("draft.draft_id"), primary_key=True
    )
    draft_slot: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, primary_key=True
    )

    fantasyTeam = relationship("FantasyTeam")
    draft = relationship("Draft")


class DraftPick(Base):
    __tablename__ = "draftpick"
    fantasy_team_id: Mapped[int] = mapped_column(
        ForeignKey("fantasyteam.fantasy_team_id"), primary_key=True
    )
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("draft.draft_id"), primary_key=True
    )
    pick_number: Mapped[int] = mapped_column(
        Integer(), nullable=False, primary_key=True
    )
    team_number: Mapped[str] = mapped_column(ForeignKey("teams.team_number"))

    fantasyTeam = relationship("FantasyTeam")
    draft = relationship("Draft")
    team = relationship("Team")


class StatboticsData(Base):
    __tablename__ = "statboticsdata"
    team_number: Mapped[str] = mapped_column(
        ForeignKey("teams.team_number"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer(), primary_key=True)
    year_end_epa: Mapped[int] = mapped_column(Integer())

    team = relationship("Team")
