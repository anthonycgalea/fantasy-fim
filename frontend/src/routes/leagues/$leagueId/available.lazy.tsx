import { createLazyFileRoute } from "@tanstack/react-router";
import { useLeague } from "@/api/useLeague";
import { useLeagueAvailableTeams } from "@/api/useLeagueAvailableTeams";
import { useStatboticsTeamYears } from "@/api/useStatboticsTeamYears";
import React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components/ui/table";

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
  const teamEventsByWeek =
    availableTeams.data
      ?.map((team, idx) => {
        const events = weeks.map((w) => {
          const ev = team.events.find((e) => e.week === w);
          return ev ? ev.event_key : "";
        });
        return {
          teamNumber: team.team_number,
          teamName: team.name,
          events,
          epa: teamEpas[idx]?.data ?? null,
        };
      })
      .sort((a, b) => (b.epa ?? -Infinity) - (a.epa ?? -Infinity)) ?? [];

  const filteredTeams = league.data?.is_fim
    ? teamEventsByWeek.filter(({ events }) =>
        selectedWeeks.some((week) => events[week - 1] !== ""),
      )
    : teamEventsByWeek;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead rowSpan={2}>Team #</TableHead>
          <TableHead rowSpan={2}>Team Name</TableHead>
          {league.data?.is_fim && <TableHead colSpan={5}>Week</TableHead>}
          <TableHead rowSpan={2}>{league.data?.is_fim ? prevYear : league.data?.year} EPA</TableHead>
        </TableRow>
        {league.data?.is_fim && (
          <TableRow>
            {weeks.map((week) => (
              <TableHead key={week} className="text-center">
                <label className="flex items-center justify-between gap-2">
                  <span>{week}</span>
                  <input
                    type="checkbox"
                    checked={selectedWeeks.includes(week)}
                    onChange={() => toggleWeekSelection(week)}
                  />
                </label>
              </TableHead>
            ))}
          </TableRow>
        )}
      </TableHeader>
      <TableBody>
        {filteredTeams.map(({ teamNumber, teamName, events, epa }) => (
          <TableRow key={teamNumber}>
            <TableCell>{teamNumber}</TableCell>
            <TableCell>{teamName}</TableCell>
            {league.data?.is_fim &&
              events.map((ev, idx) => <TableCell key={idx}>{ev}</TableCell>)}
            <TableCell>{epa ?? "N/A"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};

export const Route = createLazyFileRoute("/leagues/$leagueId/available")({
  component: AvailableTeamsPage,
});
