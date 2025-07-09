import { useQuery } from "@tanstack/react-query";
import { Draft } from "@/types/Draft";

export const useLeagueDrafts = (leagueId: string | undefined) =>
  useQuery<Draft[]>({
    queryFn: () =>
      fetch(`/api/leagues/${leagueId}/drafts`).then((res) => res.json()),
    queryKey: ["leagueDrafts", leagueId],
    enabled: !!leagueId,
  });
