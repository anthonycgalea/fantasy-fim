import { useQuery } from "@tanstack/react-query"

export const useTeamAvatar = (teamId: string | undefined, year: number | undefined) => {
    const teamKey = teamId?.startsWith("frc") ? teamId : `frc${teamId}`
    const avatarUrl =
        teamKey && year ? `https://www.thebluealliance.com/avatar/${year}/${teamKey}.png` : undefined

    return useQuery({
        queryKey: ["team-avatar", teamId, year],
        queryFn: async () => ({ imageUrl: avatarUrl }),
        staleTime: 60 * 60 * 24 * 1000,

        enabled: !!teamId && !!year,
    })
}