from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class WaiverClaim(Base):
    __tablename__ = "waiverclaim"
    fantasy_team_id: Mapped[int] = mapped_column(
        ForeignKey("fantasyteam.fantasy_team_id"), primary_key=True
    )
    league_id: Mapped[int] = mapped_column(ForeignKey("league.league_id"))
    team_claimed: Mapped[str] = mapped_column(ForeignKey("teams.team_number"))
    team_to_drop: Mapped[str] = mapped_column(ForeignKey("teams.team_number"))
    priority: Mapped[int] = mapped_column(Integer(), primary_key=True)

    fantasy_team = relationship("FantasyTeam")
    league = relationship("League")
    claimed_team = relationship("Team", foreign_keys=[team_claimed])
    dropped_team = relationship("Team", foreign_keys=[team_to_drop])


class WaiverPriority(Base):
    __tablename__ = "waiverpriority"
    league_id: Mapped[int] = mapped_column(
        ForeignKey("league.league_id"), primary_key=True
    )
    priority: Mapped[int] = mapped_column(Integer(), primary_key=True)
    fantasy_team_id: Mapped[int] = mapped_column(
        ForeignKey("fantasyteam.fantasy_team_id"), primary_key=True
    )

    league = relationship("League")
    fantasy_team = relationship(
        "FantasyTeam", back_populates="waiver_priority", uselist=False
    )


class TeamOnWaivers(Base):
    __tablename__ = "teamonwaivers"
    league_id: Mapped[int] = mapped_column(
        ForeignKey("league.league_id"), primary_key=True
    )
    team_number: Mapped[str] = mapped_column(
        ForeignKey("teams.team_number"), primary_key=True
    )

    league = relationship("League")
    team = relationship("Team")


class TradeProposal(Base):
    __tablename__ = "tradeproposal"

    trade_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[int] = mapped_column(
        ForeignKey("league.league_id"), nullable=False
    )
    proposer_team_id: Mapped[int] = mapped_column(
        ForeignKey("fantasyteam.fantasy_team_id"), nullable=False
    )
    proposed_to_team_id: Mapped[int] = mapped_column(
        ForeignKey("fantasyteam.fantasy_team_id"), nullable=False
    )

    expiration: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(), nullable=False
    )

    proposer_team = relationship("FantasyTeam", foreign_keys=[proposer_team_id])
    proposed_to_team = relationship("FantasyTeam", foreign_keys=[proposed_to_team_id])
    league = relationship("League")

    teams_involved = relationship("TradeTeams", back_populates="trade")

    def __str__(self):
        return f"Trade proposal between {self.proposer_team} and {self.proposed_to_team} in {self.league}"


class TradeTeams(Base):
    __tablename__ = "tradeteams"

    trade_id: Mapped[int] = mapped_column(
        ForeignKey("tradeproposal.trade_id"), primary_key=True
    )
    team_key: Mapped[str] = mapped_column(
        ForeignKey("teams.team_number"), primary_key=True
    )
    is_offered: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )  # True for teams being offered, False for requested

    trade = relationship("TradeProposal", back_populates="teams_involved")
    team = relationship("Team", foreign_keys=[team_key])

    def __str__(self):
        return f"Team {self.team_key} {'offered' if self.is_offered else 'requested'} in trade {self.trade_id}"
