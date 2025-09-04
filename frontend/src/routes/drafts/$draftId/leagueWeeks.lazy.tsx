import { createLazyFileRoute } from "@tanstack/react-router";
import { useDraft } from "@/api/useDraft";
import { useLeague } from "@/api/useLeague";
import { useFantasyTeams } from "@/api/useFantasyTeams";
import { usePicks } from "@/api/usePicks";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const DraftLeagueWeeksPage = () => {
  const { draftId } = Route.useParams();
  const draft = useDraft(draftId);
  const league = useLeague(draft.data?.league_id.toString());
  const draftPicks = usePicks(draftId);
  const fantasyTeams = useFantasyTeams(league.data?.league_id.toString());

  if (
    draft.isLoading ||
    league.isLoading ||
    draftPicks.isLoading ||
    fantasyTeams.isLoading
  ) {
    return <div>Loading...</div>;
  }

  const fantasyTeamWeekCounts: Record<number, number[]> = {};
  fantasyTeams.data?.forEach((team) => {
    fantasyTeamWeekCounts[team.fantasy_team_id] = [0, 0, 0, 0, 0];
  });

  draftPicks.data?.forEach((pick) => {
    pick.events.forEach((event) => {
      if (event.week >= 1 && event.week <= 6) {
        fantasyTeamWeekCounts[pick.fantasy_team_id][event.week - 1] += 1;
      }
    });
  });

  const weeks = [1, 2, 3, 4, 6];

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Fantasy Team</TableHead>
          {weeks.map((w) => (
            <TableHead key={w} className="text-center">
              Week {w}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {fantasyTeams.data?.map((team) => (
          <TableRow key={team.fantasy_team_id}>
            <TableCell className="font-bold">{team.team_name}</TableCell>
            {fantasyTeamWeekCounts[team.fantasy_team_id].map((count, index) => {
              let className = "";
              if (league.data && count >= league.data.weekly_starts) {
                className = "bg-green-300";
              } else if (league.data && count === league.data.weekly_starts - 1) {
                className = "bg-yellow-300";
              } else {
                className = "bg-red-300";
              }
              return (
                <TableCell
                  key={index}
                  className={cn(className, "text-black text-center")}
                >
                  {count}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};

export const Route = createLazyFileRoute("/drafts/$draftId/leagueWeeks")({
  component: DraftLeagueWeeksPage,
});
