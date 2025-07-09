import { useQuery } from "@tanstack/react-query";
import { FantasyTeamRosterWeek } from "@/types/FantasyTeamRosterWeek";

export const useRosterWeeks = (leagueId: string | undefined) =>
  useQuery<FantasyTeamRosterWeek[]>({
    queryFn: () =>
      fetch(`/api/leagues/${leagueId}/rosterWeeks`).then((res) => res.json()),
    queryKey: ["rosterWeeks", leagueId],
    enabled: !!leagueId,
  });
