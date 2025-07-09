import { useQuery } from "@tanstack/react-query"
import { DraftOrderPlayer } from "../types/DraftSlot"

export const useDraftOrder = (draftId: string) => {
    return useQuery<DraftOrderPlayer[]>({
        queryFn: async () => {
            const res = await fetch(`/api/drafts/${draftId}/draftOrder`)
            if (!res.ok) {
                throw new Error('Failed to fetch draft order')
            }
            return res.json() as Promise<DraftOrderPlayer[]>
        },
        queryKey: ['draftOrder', draftId],
        enabled: !!draftId,
    })}