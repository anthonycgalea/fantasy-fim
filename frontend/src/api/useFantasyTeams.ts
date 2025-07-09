import { useQuery } from "@tanstack/react-query"
import { FantasyTeam } from "@/types/FantasyTeam"

export const useFantasyTeams = (leagueId: string | undefined) => {
    return useQuery<FantasyTeam[]>({
        queryFn: () => fetch(`/api/leagues/${leagueId}/fantasyTeams`).then((res) => res.json()),
        queryKey: ['fantasyTeams', leagueId],
        enabled: !!leagueId,
    })
}