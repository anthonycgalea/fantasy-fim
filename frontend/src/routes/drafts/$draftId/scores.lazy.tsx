import { createLazyFileRoute, Link } from "@tanstack/react-router";
import { useDraft } from "@/api/useDraft";
import { useDraftScores } from "@/api/useDraftScores";
import { useLeague } from "@/api/useLeague";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHeader,
  TableHead,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import React from "react";

export const DraftScoresPage = () => {
  const { draftId } = Route.useParams();
  const draft = useDraft(draftId);
  const scores = useDraftScores(draftId);
  const league = useLeague(draft.data?.league_id.toString());

  if (draft.isLoading || scores.isLoading || league.isLoading) {
    return <div>Loading...</div>;
  }

  const weeklyStarts = league.data?.weekly_starts ?? 0;

  return (
    <div className="w-full min-w-[1000px] overflow-x-scroll overflow-y-scroll">
      <div className="flex flex-col items-center">
        <h1 className="text-3xl font-bold text-center">
          {league.data?.league_name}
        </h1>
      </div>
      <div className="text-center my-4">
        <Link to="/drafts/$draftId" params={{ draftId }}>
          <Button>View Draft</Button>
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {scores.data?.map((team) => (
          <Card key={team.fantasy_team_id}>
            <CardHeader>{team.fantasy_team_name}</CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Team #</TableHead>
                  <TableHead>Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Array.from({ length: weeklyStarts }).map((_, idx) => {
                  const teamStarted = team.teams[idx];
                  return (
                    <TableRow key={idx}>
                      <TableCell>{teamStarted?.team_number ?? ""}</TableCell>
                      <TableCell>{teamStarted?.event_score ?? 0}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
              <TableFooter>
                <TableRow>
                  <TableCell>Total</TableCell>
                  <TableCell>{team.event_score}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>RP</TableCell>
                  <TableCell>{team.rank_points}</TableCell>
                </TableRow>
              </TableFooter>
            </Table>
          </CardContent>
        </Card>
        ))}
      </div>
    </div>
  );
};

export const Route = createLazyFileRoute("/drafts/$draftId/scores")({
  component: DraftScoresPage,
});
