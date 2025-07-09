import { useQuery } from "@tanstack/react-query";
import { AvailableTeam } from "@/types/AvailableTeam";

export const useLeagueAvailableTeams = (leagueId: string | undefined) =>
  useQuery<AvailableTeam[]>({
    queryFn: () =>
      fetch(`/api/leagues/${leagueId}/availableTeams`).then((res) => res.json()),
    queryKey: ["leagueAvailableTeams", leagueId],
    enabled: !!leagueId,
  });
