import { createFileRoute } from "@tanstack/react-router";
import { useDraft } from "@/api/useDraft";
import { useLeague } from "@/api/useLeague";
import { usePicks } from "@/api/usePicks";
import { useDraftOrder } from "@/api/useDraftOrder";
import { DraftPick } from "@/types/DraftPick";
import { useFantasyTeams } from "@/api/useFantasyTeams";
import { useMemo } from "react";
import { useTeamAvatar } from "@/api/useTeamAvatar";

const DraftBoard = () => {
  const { draftId } = Route.useParams();

  // Pull the auto refresh interval from the query string
  const { autoRefreshInterval } = Route.useSearch();

  const draft = useDraft(draftId);
  const league = useLeague(draft.data?.league_id.toString());
  const picks = usePicks(draftId, autoRefreshInterval);
  const draftOrder = useDraftOrder(draftId);
  const fantasyTeams = useFantasyTeams(league.data?.league_id.toString());

  const draftOrderPlayers = useMemo(
    () =>
      draftOrder.data?.map((order) => ({
        ...order,
        team: fantasyTeams.data?.find(
          (team) => team.fantasy_team_id === order.fantasy_team_id
        ),
      })),
    [draftOrder.data, fantasyTeams.data]
  );

  console.log(draftOrder.data, fantasyTeams.data, draftOrderPlayers);

  if (!draft.data || !league.data || !picks.data || !draftOrder.data) {
    return <div>Loading...</div>;
  }

  const totalPicks = (draftOrder.data?.length ?? 1) * (draft.data?.rounds ?? 1);

  const draftPicks = [
    ...(picks.data ?? ([] as DraftPick[])),
    ...(Array(totalPicks - (picks.data?.length ?? 0)).fill(null) as null[]),
  ];
  const picksInRound: (DraftPick | null)[][] = [];
  for (let i = 0; i < draftPicks.length; i += draftOrder.data?.length ?? 1) {
    picksInRound.push(draftPicks.slice(i, i + (draftOrder.data?.length ?? 1)));
  }

  return (
    <div className="w-full min-w-[1000px] overflow-x-scroll overflow-y-scroll">
      <h1 className="text-3xl font-bold">{league.data?.league_name}</h1>

      <div
        className={`grid`}
        style={{
          gridTemplateColumns: `repeat(${draftOrder.data?.length ?? 1}, 1fr)`,
        }}
      >
        {draftOrderPlayers?.map((order) => (
          <div className="text-center mb-4" key={order.fantasy_team_id}>
            {order.team?.team_name}
          </div>
        ))}
      </div>
      {picksInRound.map((row, rowIndex) => (
        <div
          key={rowIndex}
          className="grid mb-1 gap-1"
          style={{
            gridTemplateColumns: `repeat(${draftOrder.data?.length ?? 1}, 1fr)`,
          }}
        >
          {(rowIndex % 2 === 0 ? row : [...row].reverse()).map(
            (pick, colIndex) => (
              <DraftBoardCard
                key={rowIndex * (draftOrder.data?.length ?? 1) + colIndex + 1}
                pick={{ round: rowIndex + 1, pick: colIndex + 1 }}
                team={pick}
                year={league.data?.year}
              />
            )
          )}
        </div>
      ))}
    </div>
  );
};

const DraftBoardCard = ({
  pick,
  team,
  year,
}: {
  pick: { round: number; pick: number };
  team: DraftPick | null;
  year: number;
}) => {
  const teamAvatar = useTeamAvatar(team?.team_picked, year);
  return (
    <a
      href={
        team?.team_picked !== "-1"
          ? `https://www.thebluealliance.com/team/${team?.team_picked}/${year}`
          : "#"
      }
      target={team?.team_picked !== "-1" ? "_blank" : "_self"}
      className="p-2 border rounded-xl h-16 flex flex-col relative bg-slate-700 hover:bg-slate-800 cursor-pointer text-start"
    >
      <p className="text-xl font-bold">
        {team?.team_picked !== "-1" ? team?.team_picked : ""}
      </p>
      <p className="text-sm">
        {team?.events
          .filter((event) => event.week !== 99)
          .sort((a, b) => a.week - b.week)
          .map((event) => event.week)
          .join(", ")}
      </p>
      {teamAvatar.data?.image && (
        <img
          src={`data:image/png;base64,${teamAvatar.data.image}`}
          className="aspect-square h-50% absolute bottom-0 right-0 rounded"
        />
      )}
    </a>
  );
};

export const Route = createFileRoute("/drafts//$draftId")({
  component: DraftBoard,
  validateSearch: (search: Record<string, unknown>) => {
    return {
      autoRefreshInterval: search?.autoRefreshInterval
        ? Number(search.autoRefreshInterval)
        : (false as false),
    };
  },
});
