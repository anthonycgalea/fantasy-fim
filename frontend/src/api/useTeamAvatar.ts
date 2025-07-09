import { useQuery } from "@tanstack/react-query"

export const useTeamAvatar = (teamId: string | undefined, year: number | undefined) => {
    return useQuery({
        queryKey: ["team-avatar", teamId, year],
        queryFn: () => fetch(`/api/team-avatar/${teamId}/year/${year}`).then(res => res.json()),
        staleTime: 60 * 60 * 24 * 1000,

        enabled: !!teamId && !!year,
    })
}