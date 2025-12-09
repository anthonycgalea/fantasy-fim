import { useState, useMemo } from "react";
import { useDraft } from "@/api/useDraft";
import { useLeague } from "@/api/useLeague";
import { useAvailableTeams } from "@/api/useAvailableTeams";
import { useCurrentWeek } from "@/api/useCurrentWeek";
import { useTeamAvatar } from "@/api/useTeamAvatar";

type AvailableTeamsSectionProps = {
	draftId: string;
};

const weekOptions = [1, 2, 3, 4, 6];

const AvailableTeamsSection = ({ draftId }: AvailableTeamsSectionProps) => {
	const [selectedWeeks, setSelectedWeeks] = useState<number[]>([1, 2, 3, 4, 6]);
	const draft = useDraft(draftId);
	const leagueId = draft.data?.league_id?.toString();
	const league = useLeague(leagueId);
	const availableTeams = useAvailableTeams(draftId);
	const currentWeek = useCurrentWeek();

	const toggleWeekSelection = (week: number) => {
		setSelectedWeeks((prev) => (prev.includes(week) ? prev.filter((w) => w !== week) : [...prev, week]));
	};

	const epaYear = useMemo(() => {
		if (!league.data) {
			return 0;
		}

		const prevYear = (league.data.year ?? 0) - 1;
		let draftEpaYear = league.data.offseason ? league.data.year : prevYear;

		if (!league.data.offseason && currentWeek.data && currentWeek.data.year === league.data.year) {
			draftEpaYear = currentWeek.data.week === 1 ? prevYear : league.data.year;
		}

		return draftEpaYear;
	}, [currentWeek.data, league.data]);

	if (!league.data || !availableTeams.data) {
		return <div>Loading available teams...</div>;
	}

	const teams = availableTeams.data
		.map((team) => ({
			teamNumber: team.team_number,
			teamName: team.name,
			events: team.events,
			epa: team.year_end_epa ?? null,
		}))
		.sort((a, b) => (b.epa ?? -Infinity) - (a.epa ?? -Infinity));

	const filteredTeams = league.data.is_fim ? teams.filter(({ events }) => events.some((event) => selectedWeeks.includes(event.week))) : teams;

	return (
		<div className="my-4">
			<h1 className="text-3xl font-bold text-center">Available Teams</h1>
			{league.data.is_fim && (
				<div className="flex gap-2 mb-2 justify-center">
					{weekOptions.map((week) => (
						<label key={week} className="flex items-center gap-2">
							<span>Competes Week {week}</span>
							<input type="checkbox" checked={selectedWeeks.includes(week)} onChange={() => toggleWeekSelection(week)} />
						</label>
					))}
				</div>
			)}
			<div className="flex flex-wrap gap-2 justify-start">
				{filteredTeams.map((team) => (
					<AvailableTeamCard key={team.teamNumber} team={team} year={epaYear} />
				))}
			</div>
		</div>
	);
};

type AvailableTeamCardProps = {
	team: { teamNumber: number; teamName: string; events: { week: number }[]; epa: number | null };
	year: number;
};

const AvailableTeamCard = ({ team, year }: AvailableTeamCardProps) => {
	const teamAvatar = useTeamAvatar(team.teamNumber.toString(), year);
	const weeks = team.events
		.filter((event) => event.week !== 99)
		.sort((a, b) => a.week - b.week)
		.map((event) => event.week)
		.join(", ");

	return (
		<a
			href={`https://www.thebluealliance.com/team/${team.teamNumber}/${year}`}
			target="_blank"
			className="p-2 border rounded-xl h-20 w-48 flex flex-col relative bg-slate-700 hover:bg-slate-800 cursor-pointer text-start">
			<p className="text-xl font-bold">{team.teamNumber}</p>
			{weeks && <p className="text-sm">{weeks}</p>}
			<p className="text-sm">EPA: {String(team.epa ?? "N/A")}</p>
			{teamAvatar.data?.imageUrl && <img src={teamAvatar.data.imageUrl} className="aspect-square h-50% absolute bottom-0 right-0 rounded" />}
		</a>
	);
};

export default AvailableTeamsSection;
