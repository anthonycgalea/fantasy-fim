import { FantasyTeamLineup } from "./FantasyTeamLineup";

export type WeeklyLineups = {
    fantasy_teams: FantasyTeamLineup[];
    week: number;
}