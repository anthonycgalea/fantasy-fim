import { useQuery } from "@tanstack/react-query";
import { League } from "../types/League";

export const useLeague = (leagueId: string | undefined) => useQuery<League>({
    queryFn: () => fetch(`/api/leagues/${leagueId}`).then((res) => res.json()),
    queryKey: ["leagueData", leagueId],
    enabled: !!leagueId,
});