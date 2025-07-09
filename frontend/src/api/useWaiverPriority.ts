import { useQuery } from "@tanstack/react-query";
import { WaiverPriority } from "@/types/WaiverPriority";

export const useWaiverPriority = (leagueId: string | undefined) =>
  useQuery<WaiverPriority[]>({
    queryFn: () =>
      fetch(`/api/leagues/${leagueId}/waiverPriority`).then((res) => res.json()),
    queryKey: ["waiverPriority", leagueId],
    enabled: !!leagueId,
  });
