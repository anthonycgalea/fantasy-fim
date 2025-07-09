import { Draft } from "@/types/Draft"
import { useQuery } from "@tanstack/react-query"

export const useDraft = (draftId: string) => {
    return useQuery<Draft>({
        queryFn: () => fetch(`/api/drafts/${draftId}`).then((res) => res.json()),
        queryKey: ['draft', draftId],
    })
}