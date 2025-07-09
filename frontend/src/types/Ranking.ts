export type Ranking = {
    fantasy_team_id: number;
    fantasy_team_name: string;
    tiebreaker: number;
    total_ranking_points: number;
    weekly_scores: {
        ranking_points: number;
        week: number;
        weekly_score: number;
    }[]
}