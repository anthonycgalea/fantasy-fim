import { useQuery } from "@tanstack/react-query";
import { Ranking } from "../types/Ranking";

export const useRankings = (leagueId: string) => useQuery<Ranking[]>({
    queryFn: () => fetch(`/api/leagues/${leagueId}/rankings`).then((res) => res.json()),
    queryKey: ["leagueRankings", leagueId],
});