import { Link } from "@tanstack/react-router";
import { useLeagues } from "@/api/useLeagues";
import { useLeagueDrafts } from "@/api/useLeagueDrafts";
import { League } from "@/types/League";

const OffseasonDraftLinks = ({ league }: { league: League }) => {
  const drafts = useLeagueDrafts(league.league_id.toString());
  if (!drafts.data?.length) return null;

  return (
    <>
      {drafts.data.map((draft) => (
        <li key={draft.draft_id} className="whitespace-nowrap">
          <Link
            to="/drafts/$draftId"
            params={{ draftId: draft.draft_id.toString() }}
            className="block px-2 py-1 hover:underline"
          >
            {league.league_name}: {draft.event_key}
          </Link>
        </li>
      ))}
    </>
  );
};

export const Navbar = () => {
  const leagues = useLeagues();
  const fimLeagues = leagues.data?.filter((l) => l.is_fim) ?? [];
  const offseasonLeagues = leagues.data?.filter((l) => l.offseason) ?? [];

  return (
    <nav className="w-full py-4 mb-4 border-b">
      <ul className="flex gap-4">
        <li>
          <Link to="/" className="hover:underline">
            Home
          </Link>
        </li>
        <li className="relative group">
          <span className="hover:underline cursor-pointer">Leagues</span>
          {fimLeagues.length > 0 && (
            <ul className="absolute left-0 z-10 hidden w-max space-y-1 rounded-md border bg-background p-2 group-hover:block">
              {fimLeagues.map((league) => (
                <li key={league.league_id} className="whitespace-nowrap">
                  <Link
                    to="/leagues/$leagueId"
                    params={{ leagueId: league.league_id.toString() }}
                    className="block px-2 py-1 hover:underline"
                  >
                    {league.league_name}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </li>
        <li className="relative group">
          <span className="hover:underline cursor-pointer">Offseason Drafts</span>
          {offseasonLeagues.length > 0 && (
            <ul className="absolute left-0 z-10 hidden w-max space-y-1 rounded-md border bg-background p-2 group-hover:block">
              {offseasonLeagues.map((league) => (
                <OffseasonDraftLinks key={league.league_id} league={league} />
              ))}
            </ul>
          )}
        </li>
        <li>
          <a href="/apidocs" className="hover:underline">
            API
          </a>
        </li>
        <li>
          <Link to="/eventData" className="hover:underline">
            Events
          </Link>
        </li>
        <li>
          <a
            href="https://github.com/anthonycgalea/fantasy-fim"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            GitHub
          </a>
        </li>
      </ul>
    </nav>
  );
};
export default Navbar;
