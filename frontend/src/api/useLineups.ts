import { useQuery } from "@tanstack/react-query";
import { WeeklyLineups } from "../types/WeeklyLineups";

export const useLineups = (leagueId: string) => useQuery<WeeklyLineups[]>({
    queryFn: () => fetch(`/api/leagues/${leagueId}/lineups`).then((res) => res.json()),
    queryKey: ["leagueLineups", leagueId],
});