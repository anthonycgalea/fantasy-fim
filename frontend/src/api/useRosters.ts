import { useQuery } from "@tanstack/react-query";
import { FantasyTeamRoster } from "@/types/FantasyTeamRoster";

export const useRosters = (leagueId: string | undefined) =>
  useQuery<FantasyTeamRoster[]>({
    queryFn: () =>
      fetch(`/api/leagues/${leagueId}/rosters`).then((res) => res.json()),
    queryKey: ["leagueRosters", leagueId],
    enabled: !!leagueId,
  });
