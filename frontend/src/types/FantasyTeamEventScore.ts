import { ScoreBreakdown } from "./FantasyTeamScore";

export type FantasyTeamEventScore = {
  fantasy_team_id: number;
  fantasy_team_name: string;
  event_score: number;
  rank_points: number;
  week: number;
  teams: {
    team_number: string;
    event_score: number;
    breakdown: ScoreBreakdown;
  }[];
};
