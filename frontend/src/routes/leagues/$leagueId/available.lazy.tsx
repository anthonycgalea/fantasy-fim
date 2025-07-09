import { createLazyFileRoute } from "@tanstack/react-router";
import { useLeague } from "@/api/useLeague";
import { useLeagueAvailableTeams } from "@/api/useLeagueAvailableTeams";
import { useStatboticsTeamYears } from "@/api/useStatboticsTeamYears";
import React from "react";
import { useTeamAvatar } from "@/api/useTeamAvatar";

const AvailableTeamCard = ({
  team,
  year,
}: {
  team: { teamNumber: number; teamName: string; events: { week: number }[]; epa: number | null };
  year: number;
}) => {
  const teamAvatar = useTeamAvatar(team.teamNumber.toString(), year);
  const weeks = team.events
    .filter((e) => e.week !== 99)
    .sort((a, b) => a.week - b.week)
    .map((e) => e.week)
    .join(', ');

  return (
    <a
      href={`https://www.thebluealliance.com/team/${team.teamNumber}/${year}`}
      target="_blank"
      className="p-2 border rounded-xl h-20 w-48 flex flex-col relative bg-slate-700 hover:bg-slate-800 cursor-pointer text-start"
    >
      <p className="text-xl font-bold">{team.teamNumber}</p>
      {weeks && <p className="text-sm">{weeks}</p>}
      <p className="text-sm">EPA: {team.epa ?? 'N/A'}</p>
      {teamAvatar.data?.image && (
        <img
          src={`data:image/png;base64,${teamAvatar.data.image}`}
          className="aspect-square h-50% absolute bottom-0 right-0 rounded"
        />
      )}
    </a>
  );
};

export const AvailableTeamsPage = () => {
  const { leagueId } = Route.useParams();
  const league = useLeague(leagueId);
  const availableTeams = useLeagueAvailableTeams(leagueId);
  const prevYear = (league.data?.year ?? 0) - 1;
  const epaYear = league.data?.offseason ? league.data?.year : prevYear;
  const teamNumbers = availableTeams.data?.map((t) => t.team_number) ?? [];
  const teamEpas = useStatboticsTeamYears(teamNumbers, epaYear);
  const [selectedWeeks, setSelectedWeeks] = React.useState<number[]>([1, 2, 3, 4, 5]);

  const toggleWeekSelection = (week: number) =>
    setSelectedWeeks((prev) =>
      prev.includes(week) ? prev.filter((w) => w !== week) : [...prev, week],
    );

  if (league.isLoading || availableTeams.isLoading) return <div>Loading...</div>;

  const weeks = [1, 2, 3, 4, 5];
  const teams =
    availableTeams.data
      ?.map((team, idx) => ({
        teamNumber: team.team_number,
        teamName: team.name,
        events: team.events,
        epa: teamEpas[idx]?.data ?? null,
      }))
      .sort((a, b) => (b.epa ?? -Infinity) - (a.epa ?? -Infinity)) ?? [];

  const filteredTeams = league.data?.is_fim
    ? teams.filter(({ events }) => events.some((e) => selectedWeeks.includes(e.week)))
    : teams;

  return (
    <div className="my-4">
      {league.data?.is_fim && (
        <div className="flex gap-2 mb-2">
          {weeks.map((week) => (
            <label key={week} className="flex items-center gap-2">
              <span>{week}</span>
              <input
                type="checkbox"
                checked={selectedWeeks.includes(week)}
                onChange={() => toggleWeekSelection(week)}
              />
            </label>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {filteredTeams.map((team) => (
          <AvailableTeamCard key={team.teamNumber} team={team} year={epaYear} />
        ))}
      </div>
    </div>
  );
};

export const Route = createLazyFileRoute("/leagues/$leagueId/available")({
  component: AvailableTeamsPage,
});
