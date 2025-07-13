import { createLazyFileRoute } from "@tanstack/react-router";
import { useLineups } from "@/api/useLineups";
import { FantasyTeamLineup } from "@/types/FantasyTeamLineup";
import React from "react";
import { useLeague } from "@/api/useLeague";
import { useCurrentWeek } from "@/api/useCurrentWeek";
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
  const league = useLeague(leagueId);
  const currentWeek = useCurrentWeek();

  const [selectedWeek, setSelectedWeek] = React.useState(1);

  React.useEffect(() => {
    if (
      currentWeek.data &&
      league.data &&
      league.data.year === currentWeek.data.year &&
      selectedWeek === 1
    ) {
      setSelectedWeek(currentWeek.data.week);
    }
  }, [currentWeek.data, league.data]);

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

  const [open, setOpen] = React.useState(false);

  if (!teamScore) {
    return (
      <TableRow>
        <TableCell>{team ?? "N/A"}</TableCell>
        <TableCell></TableCell>
      </TableRow>
    );
  }

  return (
    <>
      <TableRow
        className="cursor-pointer"
        onClick={() => setOpen((o) => !o)}
      >
        <TableCell>{team ?? "N/A"}</TableCell>
        <TableCell>{teamScore.weekly_score}</TableCell>
      </TableRow>
      {open && (
        <TableRow>
          <TableCell colSpan={2}>
            <div className="pl-4 space-y-1 text-sm">
              <div>Qual: {teamScore.breakdown.qual_points}</div>
              <div>Alliance: {teamScore.breakdown.alliance_points}</div>
              <div>Elim: {teamScore.breakdown.elim_points}</div>
              <div>Award: {teamScore.breakdown.award_points}</div>
              <div>Rookie: {teamScore.breakdown.rookie_points}</div>
              <div>Stat Corr: {teamScore.breakdown.stat_correction}</div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
};

export const Route = createLazyFileRoute("/leagues/$leagueId/scores")({
  component: ScoresPage,
});
