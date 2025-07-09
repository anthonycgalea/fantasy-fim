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
        `/api/epa?teams=${team}&year=${year}`,
      );
      if (!response.ok) return null;
      try {
        const data = await response.json();
        const value = data?.[team as string];
        return typeof value === "number" ? value : null;
      } catch {
        return null;
      }
    },
    staleTime: 1000 * 60 * 60 * 24,
    gcTime: 1000 * 60 * 60 * 24 * 7,
  });
};
