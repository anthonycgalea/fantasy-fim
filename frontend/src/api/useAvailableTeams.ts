import { useQuery } from "@tanstack/react-query";
import { AvailableTeam } from "@/types/AvailableTeam";

export const useAvailableTeams = (draftId: string | undefined) =>
  useQuery<AvailableTeam[]>({
    queryFn: () =>
      fetch(`/api/drafts/${draftId}/availableTeams`).then((res) => res.json()),
    queryKey: ["availableTeams", draftId],
    enabled: !!draftId,
  });
