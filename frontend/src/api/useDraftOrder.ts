import { useQuery } from "@tanstack/react-query"
import { DraftOrderPlayer } from "../types/DraftSlot"

export const useDraftOrder = (draftId: string) => {
    return useQuery<DraftOrderPlayer[]>({
        queryFn: () => fetch(`/api/drafts/${draftId}/draftOrder`).then((res) => res.json()),
        queryKey: ['draftOrder', draftId],
    })
}