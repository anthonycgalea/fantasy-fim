export type FantasyTeamScore = {
    fantasy_team_id: number;
    fantasy_team_name: string;
    rank_points: number;
    teams: TeamScore[];
    week: number;
    weekly_score: number;
}

export type TeamScore = {
    breakdown: ScoreBreakdown;
    team_number: string;
    weekly_score: number;
}

export type ScoreBreakdown = {
    alliance_points: number;
    award_points: number;
    elim_points: number;
    qual_points: number;
    rookie_points: number;
    stat_correction: number
}