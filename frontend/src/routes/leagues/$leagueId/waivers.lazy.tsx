import { createLazyFileRoute } from "@tanstack/react-router";
import { useLeague } from "@/api/useLeague";
import { useWaiverTeams } from "@/api/useWaiverTeams";
import { useWaiverPriority } from "@/api/useWaiverPriority";
import { WaiverPriority } from "@/types/WaiverPriority";
import React, { useState } from "react";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";

export const WaiversPage = () => {
  const { leagueId } = Route.useParams();
  const league = useLeague(leagueId);
  const waiverTeams = useWaiverTeams(leagueId);
  const waiverPriority = useWaiverPriority(leagueId);

  const [activeTab, setActiveTab] = useState<'teams' | 'priority'>('teams');
  const [selectedWeeks, setSelectedWeeks] = useState<number[]>([1, 2, 3, 4, 5]);

  const toggleWeekSelection = (week: number) => {
    setSelectedWeeks((prev) =>
      prev.includes(week) ? prev.filter((w) => w !== week) : [...prev, week]
    );
  };

  if (
    league.isLoading ||
    waiverTeams.isLoading ||
    waiverPriority.isLoading
  ) {
    return <div>Loading...</div>;
  }

  const renderWaiverTeams = () => {
    if (!league.data || !waiverTeams.data) return null;

    const weeks = [1, 2, 3, 4, 5];
    const teams = waiverTeams.data.map((team): {
      teamNumber: number;
      teamName: string;
      events: string[];
      yearEndEpa?: number;
    } => {
      const events = weeks.map((w) => {
        const ev = team.events.find((e) => e.week === w);
        return ev ? ev.event_key : "";
      });
      return {
        teamNumber: team.team_number,
        teamName: team.name,
        events,
        yearEndEpa: team.year_end_epa,
      };
    });

    const filtered = league.data.is_fim
      ? teams.filter(({ events }) =>
          selectedWeeks.some((w) => events[w - 1] !== "")
        )
      : teams;

    const prevYear = league.data.year - 1;

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead rowSpan={league.data.is_fim ? 2 : 1}>Team #</TableHead>
            <TableHead rowSpan={league.data.is_fim ? 2 : 1}>Team Name</TableHead>
            {league.data.is_fim && <TableHead colSpan={5}>Week</TableHead>}
            <TableHead rowSpan={league.data.is_fim ? 2 : 1}>
              {league.data.is_fim ? prevYear : league.data.year} EPA
            </TableHead>
          </TableRow>
          {league.data.is_fim && (
            <TableRow>
              {weeks.map((week) => (
                <TableHead key={week}>
                  <label className="flex items-center gap-2">
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
          {filtered.map((team) => (
            <TableRow key={team.teamNumber}>
              <TableCell>{team.teamNumber}</TableCell>
              <TableCell>{team.teamName}</TableCell>
              {league.data.is_fim &&
                team.events.map((ev: string, i: number) => (
                  <TableCell key={i}>{ev}</TableCell>
                ))}
              <TableCell>{team.yearEndEpa ?? ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  };

  const renderWaiverPriority = () => {
    if (!waiverPriority.data) return null;
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Priority</TableHead>
            <TableHead>Fantasy Team</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {waiverPriority.data.map((w: WaiverPriority) => (
            <TableRow key={w.fantasy_team_id}>
              <TableCell>{w.priority}</TableCell>
              <TableCell>{w.fantasy_team_name}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Button
          variant={activeTab === 'teams' ? 'default' : 'outline'}
          onClick={() => setActiveTab('teams')}
        >
          Teams on Waivers
        </Button>
        <Button
          variant={activeTab === 'priority' ? 'default' : 'outline'}
          onClick={() => setActiveTab('priority')}
        >
          Waiver Priority
        </Button>
      </div>
      {activeTab === 'teams' ? renderWaiverTeams() : renderWaiverPriority()}
    </div>
  );
};

export const Route = createLazyFileRoute('/leagues/$leagueId/waivers')({
  component: WaiversPage,
});
