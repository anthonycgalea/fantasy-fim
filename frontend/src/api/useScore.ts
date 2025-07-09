import { useQuery } from "@tanstack/react-query"
import { FantasyTeamScore } from "../types/FantasyTeamScore"

export const useScore = (leagueId: string, week: number) => {
    return useQuery<FantasyTeamScore[]>({
        queryFn: () => fetch(`/api/leagues/${leagueId}/fantasyScores/${week}`).then((res) => res.json()),
        queryKey: ['scores', leagueId, week],
    })
}

export const useLineupScore = (leagueId: string, week: number, fantasyTeamId: number) => {
    const { data } = useScore(leagueId, week)
    return data?.find(score => score.fantasy_team_id === fantasyTeamId)
}

export const useTeamScore = (leagueId: string, week: number, teamNumber: string | null) => {
    const { data } = useScore(leagueId, week)
    const fantasyTeamWithTeam = data?.find(score => score.teams.find(team => team.team_number === teamNumber))
    return fantasyTeamWithTeam?.teams.find(team => team.team_number === teamNumber)
}