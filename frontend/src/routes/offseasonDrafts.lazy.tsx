import { createLazyFileRoute, Link } from "@tanstack/react-router";
import { useLeagues } from "@/api/useLeagues";
import { useLeagueDrafts } from "@/api/useLeagueDrafts";
import { League } from "@/types/League";

const OffseasonLeague = ({ league }: { league: League }) => {
  const drafts = useLeagueDrafts(league.league_id.toString());

  if (drafts.isLoading) {
    return <div>Loading drafts...</div>;
  }

  if (!drafts.data?.length) return null;

  return (
    <div className="mb-4">
      <h2 className="text-2xl font-semibold">{league.league_name}</h2>
      <ul className="list-disc ml-4">
        {drafts.data.map((draft) => (
          <li key={draft.draft_id}>
            <Link
              to="/drafts/$draftId"
              params={{ draftId: draft.draft_id.toString() }}
              className="hover:underline"
            >
              {draft.event_key}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
};

export const OffseasonDraftsPage = () => {
  const leagues = useLeagues();

  if (leagues.isLoading) {
    return <div>Loading...</div>;
  }

  const offseasonLeagues = leagues.data?.filter((l) => l.offseason) ?? [];

  return (
    <div>
      <h1 className="text-3xl font-bold mb-4">Offseason Drafts</h1>
      {offseasonLeagues.map((league) => (
        <OffseasonLeague key={league.league_id} league={league} />
      ))}
    </div>
  );
};

export const Route = createLazyFileRoute("/offseasonDrafts")({
  component: OffseasonDraftsPage,
});
