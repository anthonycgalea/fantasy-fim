import { useMemo } from "react";
import { useDraft } from "@/api/useDraft";
import { useLeague } from "@/api/useLeague";
import { usePicks } from "@/api/usePicks";
import { useDraftOrder } from "@/api/useDraftOrder";
import { useFantasyTeams } from "@/api/useFantasyTeams";
import { DraftPick } from "@/types/DraftPick";
import { useStatboticsTeamYear } from "@/api/useStatboticsTeamYear";
import { useCurrentWeek } from "@/api/useCurrentWeek";

type DraftBoardContentProps = {
	draftId: string;
	autoRefreshInterval: number | false;
};

const DraftBoardContent = ({ draftId, autoRefreshInterval }: DraftBoardContentProps) => {
	const draft = useDraft(draftId);
	const leagueId = draft.data?.league_id?.toString();
	const league = useLeague(leagueId);
	const picks = usePicks(draftId, autoRefreshInterval);
	const draftOrder = useDraftOrder(draftId);
	const fantasyTeams = useFantasyTeams(leagueId);
	const currentWeek = useCurrentWeek();

	const draftOrderPlayers = useMemo(
		() =>
			Array.isArray(draftOrder.data)
				? draftOrder.data.map((order) => ({
						...order,
						team: fantasyTeams.data?.find((t) => t.fantasy_team_id === order.fantasy_team_id),
					}))
				: [],
		[draftOrder.data, fantasyTeams.data]
	);

	const draftOrderData = draftOrder.data;

	if (!draft.data || !league.data || !picks.data || !draftOrderData) {
		return <div>Loading draft board...</div>;
	}

	const prevYear = (league.data.year ?? 0) - 1;
	let epaYear = league.data.offseason ? league.data.year : prevYear;

	if (!league.data.offseason && currentWeek.data && currentWeek.data.year === league.data.year) {
		epaYear = currentWeek.data.week === 1 ? prevYear : league.data.year;
	}

	const totalPicks = draftOrderData.length * (draft.data.rounds ?? 1);

	const picksArray = Array.isArray(picks.data) ? picks.data : [];
	const draftPicks = [...picksArray, ...(Array(totalPicks - picksArray.length).fill(null) as null[])];

	const picksInRound: (DraftPick | null)[][] = [];
	for (let i = 0; i < draftPicks.length; i += draftOrderData.length) {
		picksInRound.push(draftPicks.slice(i, i + draftOrderData.length));
	}

	return (
		<div className="space-y-4">
			<div className="grid" style={{ gridTemplateColumns: `repeat(${draftOrderData.length}, 1fr)` }}>
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
						gridTemplateColumns: `repeat(${draftOrderData.length}, 1fr)`,
					}}>
					{(rowIndex % 2 === 0 ? row : [...row].reverse()).map((pick, colIndex) => (
						<DraftBoardCard
							key={rowIndex * draftOrderData.length + colIndex + 1}
							pick={{ round: rowIndex + 1, pick: colIndex + 1 }}
							team={pick}
							displayYear={league.data.year}
							epaYear={epaYear}
						/>
					))}
				</div>
			))}
		</div>
	);
};

type DraftBoardCardProps = {
	pick: { round: number; pick: number };
	team: DraftPick | null;
	displayYear: number;
	epaYear: number;
};

const DraftBoardCard = ({ pick, team, displayYear, epaYear }: DraftBoardCardProps) => {
	const { data: epa } = useStatboticsTeamYear(team?.team_picked ? Number(team.team_picked) : undefined, epaYear);

	return (
		<a
			data-round={pick.round}
			data-pick={pick.pick}
			href={team?.team_picked !== "-1" ? `https://www.thebluealliance.com/team/${team?.team_picked}/${displayYear}` : "#"}
			target={team?.team_picked !== "-1" ? "_blank" : "_self"}
			className="p-2 border rounded-xl h-20 flex flex-col relative bg-slate-700 hover:bg-slate-800 cursor-pointer text-start">
			<p className="text-xl font-bold">{team?.team_picked !== "-1" ? team?.team_picked : ""}</p>
			<p className="text-sm">
				{Array.isArray(team?.events)
					? team.events
							.filter((event) => event.week !== 99)
							.sort((a, b) => a.week - b.week)
							.map((event) => event.week)
							.join(", ")
					: ""}
			</p>
			<p className="text-sm">EPA: {String(epa ?? "N/A")}</p>
			{team?.team_picked && team?.team_picked !== "-1" && (
				<img
					src={`https://www.thebluealliance.com/avatar/${displayYear}/frc${team?.team_picked}.png`}
					className="aspect-square h-50% absolute bottom-0 right-0 rounded"
					onError={(e) => {
						(e.currentTarget as HTMLImageElement).style.display = "none";
					}}
				/>
			)}
		</a>
	);
};

export default DraftBoardContent;
