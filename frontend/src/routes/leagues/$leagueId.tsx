import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useLocation,
} from "@tanstack/react-router";
import { useLeague } from "@/api/useLeague";
import { useLeagueDrafts } from "@/api/useLeagueDrafts";
import { Button } from "@/components/ui/button";

export const LeaguePage = () => {
  const { leagueId } = Route.useParams();
  const leagueData = useLeague(leagueId);
  const drafts = useLeagueDrafts(leagueId);
  const location = useLocation();

  const firstDraftId = drafts.data?.[0]?.draft_id;
  const buttons = [
    { label: "Rankings", to: "/leagues/$leagueId/rankings" },
    { label: "Scores/Lineups", to: "/leagues/$leagueId/scores" },
    { label: "Rosters", to: "/leagues/$leagueId/rosters" },
    { label: "Available Teams", to: "/leagues/$leagueId/available" },
    { label: "Waivers", to: "/leagues/$leagueId/waivers" },
    leagueData.data?.is_fim && firstDraftId
      ? { label: "Draft", to: `/drafts/${firstDraftId}` }
      : { label: "Drafts", to: "/leagues/$leagueId/drafts" },
  ];

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold">{leagueData.data?.league_name}</h1>
      <div className="w-full flex flex-row gap-2 flex-wrap justify-stretch py-8">
        {buttons.map((button) => {
          const isActive =
            location.pathname === button.to.replace("$leagueId", leagueId);
          return (
            <Link key={button.to} to={button.to} params={{ leagueId }}>
              <Button variant={isActive ? "default" : "outline"}>
                {button.label}
              </Button>
            </Link>
          );
        })}
      </div>
      <Outlet />
    </div>
  );
};

export const Route = createFileRoute("/leagues/$leagueId")({
  component: LeaguePage,
  loader: async ({ params, location }) => {
    if (location.pathname === `/leagues/${params.leagueId}`) {
      throw redirect({ to: "/leagues/$leagueId/rankings", params });
    }
    return null;
  },
});
