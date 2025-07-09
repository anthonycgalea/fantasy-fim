import { createLazyFileRoute } from "@tanstack/react-router";
import { useRosterWeeks } from "@/api/useRosterWeeks";
import { useRosters } from "@/api/useRosters";
import { useFantasyTeams } from "@/api/useFantasyTeams";
import { useLeague } from "@/api/useLeague";
import { useTeamAvatar } from "@/api/useTeamAvatar";
import React from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
  TableCell,
} from "@/components/ui/table";

export const RostersPage = () => {
  const { leagueId } = Route.useParams();
  const rosterWeeks = useRosterWeeks(leagueId);
  const rosters = useRosters(leagueId);
  const fantasyTeams = useFantasyTeams(leagueId);
  const league = useLeague(leagueId);
  const [selectedTeam, setSelectedTeam] = React.useState(0);

  if (
    rosterWeeks.isLoading ||
    rosters.isLoading ||
    fantasyTeams.isLoading ||
    league.isLoading
  ) {
    return <div>Loading...</div>;
  }

  const handleChange = (val: string) => setSelectedTeam(parseInt(val));

  const selectedRoster = rosterWeeks.data?.find(
    (team) => team.fantasy_team_id === selectedTeam,
  );

  return (
    <div className="space-y-4">
      <Select value={selectedTeam.toString()} onValueChange={handleChange}>
        <SelectTrigger>
          <SelectValue placeholder="Select Team" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="0">All Teams</SelectItem>
          {fantasyTeams.data?.map((team) => (
            <SelectItem
              key={team.fantasy_team_id}
              value={team.fantasy_team_id.toString()}
            >
              {team.team_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selectedTeam === 0 ? (
        <RostersGrid rosters={rosters.data ?? []} year={league.data?.year} />
      ) : (
        <RosterWeeksTable rosterWeek={selectedRoster} />
      )}
    </div>
  );
};

const RostersGrid = ({
  rosters,
  year,
}: {
  rosters: { fantasy_team_id: number; fantasy_team_name: string; roster: string[] }[];
  year: number | undefined;
}) => {
  return (
    <div className="grid grid-cols-2 gap-4">
      {rosters.map((team) => (
        <Card key={team.fantasy_team_id}>
          <CardHeader>{team.fantasy_team_name}</CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-2">
              {team.roster.map((r) => (
                <RosterTeamCard key={r} teamKey={r} year={year} />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};

const RosterTeamCard = ({
  teamKey,
  year,
}: {
  teamKey: string;
  year: number | undefined;
}) => {
  const teamNumber = teamKey.replace("frc", "");
  const teamAvatar = useTeamAvatar(teamKey, year);

  return (
    <a
      href={`https://www.thebluealliance.com/team/${teamNumber}/${year}`}
      target="_blank"
      className="p-2 border rounded-xl h-16 flex flex-col relative bg-slate-700 hover:bg-slate-800 cursor-pointer text-start"
    >
      <p className="text-xl font-bold">{teamNumber}</p>
      {teamAvatar.data?.image && (
        <img
          src={`data:image/png;base64,${teamAvatar.data.image}`}
          className="aspect-square h-1/2 absolute bottom-0 right-0 rounded"
        />
      )}
    </a>
  );
};

const RosterWeeksTable = ({
  rosterWeek,
}: {
  rosterWeek:
    | {
        fantasy_team_id: number;
        fantasy_team_name: string;
        roster: {
          team_key: string;
          events: { event_key: string; event_name: string; week: number }[];
        }[];
      }
    | undefined;
}) => {
  if (!rosterWeek) return null;

  const weeks = [1, 2, 3, 4, 5];

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Team #</TableHead>
          {weeks.map((w) => (
            <TableHead key={w}>Week {w}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rosterWeek.roster.map((team) => {
          const weeklyEvents = Array(5).fill("-");
          team.events.forEach((event) => {
            if (event.week >= 1 && event.week <= 5) {
              weeklyEvents[event.week - 1] = event.event_key;
            }
          });
          return (
            <TableRow key={team.team_key}>
              <TableCell>{team.team_key}</TableCell>
              {weeklyEvents.map((ev, i) => (
                <TableCell key={i}>{ev}</TableCell>
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
};

export const Route = createLazyFileRoute("/leagues/$leagueId/rosters")({
  component: RostersPage,
});
