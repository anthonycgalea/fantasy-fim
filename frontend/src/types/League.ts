export type League = {
    is_fim: boolean;
    league_id: number;
    league_name: string;
    weekly_starts: number;
    year: number;
    offseason?: boolean;
    team_limit: number;
    team_starts: number;
    team_size_limit: number;
};