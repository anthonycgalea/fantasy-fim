import { useQuery } from "@tanstack/react-query";
import { FantasyTeamEventScore } from "@/types/FantasyTeamEventScore";

export const useDraftScores = (draftId: string | undefined) =>
  useQuery<FantasyTeamEventScore[]>({
    queryFn: () =>
      fetch(`/api/drafts/${draftId}/fantasyScores`).then((res) => res.json()),
    queryKey: ["draftScores", draftId],
    enabled: !!draftId,
  });
