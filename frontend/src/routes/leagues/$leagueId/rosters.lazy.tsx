import { createLazyFileRoute } from "@tanstack/react-router";
import RosterWeeks from "@/components/RosterWeeks";

export const RostersPage = () => {
  const { leagueId } = Route.useParams();
  return <RosterWeeks leagueId={leagueId} />;
};

export const Route = createLazyFileRoute("/leagues/$leagueId/rosters")({
  component: RostersPage,
});
