import { createLazyFileRoute } from "@tanstack/react-router";
import { useLeague } from "@/api/useLeague";
import { useWaiverTeams } from "@/api/useWaiverTeams";
import { useWaiverPriority } from "@/api/useWaiverPriority";
import { WaiverPriority } from "@/types/WaiverPriority";
import { useState } from "react";
import { useTeamAvatar } from "@/api/useTeamAvatar";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";

const WaiverTeamCard = ({
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
    const prevYear = (league.data.year ?? 0) - 1;
    const epaYear = league.data.offseason ? league.data.year : prevYear;

    const teams =
      waiverTeams.data
        .map((team) => ({
          teamNumber: team.team_number,
          teamName: team.name,
          events: team.events,
          epa: team.year_end_epa ?? null,
        }))
        .sort((a, b) => (b.epa ?? -Infinity) - (a.epa ?? -Infinity));

    const filteredTeams = league.data.is_fim
      ? teams.filter(({ events }) => events.some((e) => selectedWeeks.includes(e.week)))
      : teams;

    return (
      <div className="my-4">
        {league.data.is_fim && (
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
            <WaiverTeamCard key={team.teamNumber} team={team} year={epaYear} />
          ))}
        </div>
      </div>
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
