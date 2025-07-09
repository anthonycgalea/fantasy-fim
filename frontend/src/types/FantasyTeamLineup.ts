export type FantasyTeamLineup = {
    fantasy_team_id: number;
    fantasy_team_name: string;
    teams: {
        team_number: string;
    }[]
}