import { createLazyFileRoute } from "@tanstack/react-router";
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useRankings } from "@/api/useRankings";
import { Skeleton } from "../../../components/ui/skeleton";

export const Rankings = () => {
  return (
    <div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableCell>Rank</TableCell>
            <TableCell>Team Name</TableCell>
            <TableCell>Ranking Points</TableCell>
            <TableCell>Tiebreaker</TableCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          <RankingsTableData />
        </TableBody>
      </Table>
    </div>
  );
};

const FallbackTableData = () =>
  Array(3)
    .fill(null)
    .map((_, rank) => (
      <TableRow>
        <TableCell>{rank + 1}</TableCell>
        <TableCell>
          <Skeleton className="w-full h-4" />
        </TableCell>
        <TableCell>
          <Skeleton className="w-8 h-4" />
        </TableCell>
        <TableCell>
          <Skeleton className="w-8 h-4" />
        </TableCell>
      </TableRow>
    ));

const RankingsTableData = () => {
  const { leagueId } = Route.useParams();
  const rankings = useRankings(leagueId);

  if (rankings.isLoading) return <FallbackTableData />;

  return rankings.data?.map((ranking, index) => (
    <TableRow key={index}>
      <TableCell>{index + 1}</TableCell>
      <TableCell>{ranking.fantasy_team_name}</TableCell>
      <TableCell>{ranking.total_ranking_points}</TableCell>
      <TableCell>{ranking.tiebreaker}</TableCell>
    </TableRow>
  ));
};

export const Route = createLazyFileRoute("/leagues/$leagueId/rankings")({
  component: Rankings,
});
