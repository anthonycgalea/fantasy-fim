import { createLazyFileRoute } from "@tanstack/react-router";
import { useLineups } from "@/api/useLineups";
import { FantasyTeamLineup } from "@/types/FantasyTeamLineup";
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
  TableCell,
  TableFooter,
  TableHeader,
  TableRow,
} from "../../../components/ui/table";
import { useLineupScore, useTeamScore } from "../../../api/useScore";

export const ScoresPage = () => {
  const { leagueId } = Route.useParams();
  const lineups = useLineups(leagueId);

  const [selectedWeek, setSelectedWeek] = React.useState(1);

  const maxTeamCount =
    lineups.data
      ?.find((lineup) => lineup.week === selectedWeek)
      ?.fantasy_teams.reduce(
        (acc, lineup) => Math.max(acc, lineup.teams.length),
        0
      ) ?? 0;

  return (
    <div>
      <Select
        value={selectedWeek.toString()}
        onValueChange={(val) => setSelectedWeek(parseInt(val))}
      >
        <SelectTrigger>
          <SelectValue placeholder="Select Week" />
        </SelectTrigger>
        <SelectContent>
          {Array.from({ length: lineups.data?.length ?? 0 }).map((_, index) => (
            <SelectItem key={index} value={(index + 1).toString()}>
              Week {index + 1}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="grid grid-cols-2 gap-4 py-4">
        {lineups.data
          ?.find((lineup) => lineup.week === selectedWeek)
          ?.fantasy_teams.map((lineup) => {
            return (
              <LineupCard
                key={lineup.fantasy_team_id}
                fantasyTeam={lineup}
                selectedWeek={selectedWeek}
                leagueId={leagueId}
                maxTeamCount={maxTeamCount}
              />
            );
          })}
      </div>
    </div>
  );
};

const LineupCard = ({
  fantasyTeam,
  selectedWeek,
  leagueId,
  maxTeamCount,
}: {
  fantasyTeam: FantasyTeamLineup;
  selectedWeek: number;
  leagueId: string;
  maxTeamCount: number;
}) => {
  const lineupScore = useLineupScore(
    leagueId,
    selectedWeek,
    fantasyTeam.fantasy_team_id
  );

  const paddedTeams: (string | null)[] = [
    ...fantasyTeam.teams.map((team) => team.team_number),
    ...Array(maxTeamCount - fantasyTeam.teams.length).fill(null),
  ];

  return (
    <Card>
      <CardHeader>{fantasyTeam.fantasy_team_name}</CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableCell>Team #</TableCell>
              <TableCell>Score</TableCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paddedTeams.map((team) => (
              <TeamScoreRow
                team={team}
                week={selectedWeek}
                leagueId={leagueId}
              />
            ))}
          </TableBody>
          {lineupScore && (
            <TableFooter>
              <TableRow>
                <TableCell>Total</TableCell>
                <TableCell>{lineupScore?.weekly_score}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>RP</TableCell>
                <TableCell>{lineupScore?.rank_points}</TableCell>
              </TableRow>
            </TableFooter>
          )}
        </Table>
      </CardContent>
    </Card>
  );
};

const TeamScoreRow = ({
  team,
  week,
  leagueId,
}: {
  team: string | null;
  week: number;
  leagueId: string;
}) => {
  const teamScore = useTeamScore(leagueId, week, team);

  return (
    <TableRow>
      <TableCell>{team ?? "N/A"}</TableCell>
      <TableCell>{teamScore?.weekly_score}</TableCell>
    </TableRow>
  );
};

export const Route = createLazyFileRoute("/leagues/$leagueId/scores")({
  component: ScoresPage,
});
