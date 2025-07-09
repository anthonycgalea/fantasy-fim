import { useQuery } from "@tanstack/react-query";

export const useStatboticsTeamYear = (
  team: number | string | undefined,
  year: number | undefined,
) => {
  return useQuery<number | null>({
    queryKey: ["statbotics-team-year", team, year],
    enabled: !!team && !!year,
    queryFn: async () => {
      const response = await fetch(
        `https://api.statbotics.io/v3/team_year/${team}/${year}`,
      );
      if (!response.ok) return null;
      try {
        const data = await response.json();
        return typeof data?.epa?.unitless === "number" ? data.epa.unitless : null;
      } catch {
        return null;
      }
    },
    staleTime: 1000 * 60 * 60 * 24,
    gcTime: 1000 * 60 * 60 * 24 * 7,
  });
};
