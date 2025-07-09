import { useQuery } from "@tanstack/react-query";
import { WaiverTeam } from "@/types/WaiverTeam";

export const useWaiverTeams = (leagueId: string | undefined) =>
  useQuery<WaiverTeam[]>({
    queryFn: () =>
      fetch(`/api/leagues/${leagueId}/teamsOnWaivers`).then((res) => res.json()),
    queryKey: ["waiverTeams", leagueId],
    enabled: !!leagueId,
  });
