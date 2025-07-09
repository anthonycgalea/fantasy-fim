import { useQuery } from "@tanstack/react-query"
import { DraftPick } from "../types/DraftPick"

export const usePicks = (draftId: string, autoRefreshInterval?: number | false) => {
    return useQuery<DraftPick[]>({
        queryFn: () => fetch(`/api/drafts/${draftId}/picks`).then((res) => res.json()),
        queryKey: ['draftPicks', draftId],
        refetchInterval: autoRefreshInterval
    })
}