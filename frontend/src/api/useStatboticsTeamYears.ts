import { useQueries } from "@tanstack/react-query";

const fetchTeamYearEPA = async (team: number | string, year: number) => {
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
};

export const useStatboticsTeamYears = (
  teams: (number | string)[],
  year: number | undefined,
) =>
  useQueries({
    queries: teams.map((team) => ({
      queryKey: ["statbotics-team-year", team, year],
      enabled: !!team && !!year,
      queryFn: () => fetchTeamYearEPA(team, year as number),
      staleTime: 1000 * 60 * 60 * 24,
      gcTime: 1000 * 60 * 60 * 24,
    })),
  });
