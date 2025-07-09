import { useQuery } from "@tanstack/react-query";

export const useStatboticsTeamYears = (
  teams: (number | string)[],
  year: number | undefined,
) =>
  useQuery<Record<string, number | null>>({
    queryKey: ["statbotics-team-years", teams, year],
    enabled: teams.length > 0 && !!year,
    queryFn: async () => {
      const response = await fetch(
        `/api/epa?teams=${teams.join(",")}&year=${year}`,
      );
      if (!response.ok) return {};
      try {
        const data = await response.json();
        return data as Record<string, number | null>;
      } catch {
        return {};
      }
    },
    staleTime: 1000 * 60 * 60 * 24,
    gcTime: 1000 * 60 * 60 * 24,
  });
