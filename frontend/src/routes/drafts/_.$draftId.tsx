import { createFileRoute, Link } from '@tanstack/react-router'
import { useDraft } from '@/api/useDraft'
import { useLeague } from '@/api/useLeague'
import { usePicks } from '@/api/usePicks'
import { useDraftOrder } from '@/api/useDraftOrder'
import { DraftPick } from '@/types/DraftPick'
import { useFantasyTeams } from '@/api/useFantasyTeams'
import { useMemo, useState } from 'react'
import { useTeamAvatar } from '@/api/useTeamAvatar'
import { useAvailableTeams } from '@/api/useAvailableTeams'
import { Button } from '@/components/ui/button'

const DraftBoard = () => {
  const { draftId } = Route.useParams()

  // Pull the auto refresh interval from the query string
  const { autoRefreshInterval } = Route.useSearch()

  const draft = useDraft(draftId)
  const league = useLeague(draft.data?.league_id.toString())
  const picks = usePicks(draftId, autoRefreshInterval)
  const draftOrder = useDraftOrder(draftId)
  const fantasyTeams = useFantasyTeams(league.data?.league_id.toString())
  const availableTeams = useAvailableTeams(draftId)

  const [selectedWeeks, setSelectedWeeks] = useState<number[]>([1, 2, 3, 4, 5])

  const toggleWeekSelection = (week: number) => {
    setSelectedWeeks((prev) =>
      prev.includes(week) ? prev.filter((w) => w !== week) : [...prev, week],
    )
  }

  const draftOrderPlayers = useMemo(
    () =>
      Array.isArray(draftOrder.data)
        ? draftOrder.data.map((order) => ({
            ...order,
            team: fantasyTeams.data?.find(
              (t) => t.fantasy_team_id === order.fantasy_team_id,
            ),
          }))
        : [],
    [draftOrder.data, fantasyTeams.data],
  )

  if (!draft.data || !league.data || !picks.data || !draftOrder.data) {
    return <div>Loading...</div>
  }

  const totalPicks = (draftOrder.data?.length ?? 1) * (draft.data?.rounds ?? 1)

  const draftPicks = [
    ...(picks.data ?? ([] as DraftPick[])),
    ...(Array(totalPicks - (picks.data?.length ?? 0)).fill(null) as null[]),
  ]
  const picksInRound: (DraftPick | null)[][] = []
  for (let i = 0; i < draftPicks.length; i += draftOrder.data?.length ?? 1) {
    picksInRound.push(draftPicks.slice(i, i + (draftOrder.data?.length ?? 1)))
  }

  const renderAvailableTeams = () => {
    if (!availableTeams.data || !league.data) return null

    const weeks = [1, 2, 3, 4, 5]

    const teamEventsByWeek = availableTeams.data.map((team) => {
      const events = weeks.map((week) => {
        const event = team.events.find((e) => e.week === week)
        return event ? event.event_key : ''
      })
      return {
        teamNumber: team.team_number,
        teamName: team.name,
        events,
        yearEndEpa: team.year_end_epa,
      }
    })

    let filteredTeams
    if (league.data.is_fim) {
      filteredTeams = teamEventsByWeek.filter(({ events }) =>
        selectedWeeks.some((week) => events[week - 1] !== ''),
      )
    } else {
      filteredTeams = teamEventsByWeek
    }

    const prevYear = league.data.year - 1

    return (
      <table className="table-auto w-full border-collapse my-4 text-sm">
        <thead>
          <tr>
            <th rowSpan={2} className="border px-2 py-1">
              Team #
            </th>
            <th rowSpan={2} className="border px-2 py-1">
              Team Name
            </th>
            {league.data.is_fim && <th colSpan={5}>Week</th>}
            <th rowSpan={2} className="border px-2 py-1">
              {league.data.is_fim ? prevYear : league.data.year} EPA
            </th>
          </tr>
          {league.data.is_fim && (
            <tr>
              {weeks.map((week) => (
                <th key={week} className="border px-2 py-1">
                  <label className="flex items-center justify-between gap-2">
                    <span>{week}</span>
                    <input
                      type="checkbox"
                      checked={selectedWeeks.includes(week)}
                      onChange={() => toggleWeekSelection(week)}
                    />
                  </label>
                </th>
              ))}
            </tr>
          )}
        </thead>
        <tbody>
          {filteredTeams.map(({ teamNumber, teamName, events, yearEndEpa }) => (
            <tr key={teamNumber}>
              <td className="border px-2 py-1">{teamNumber}</td>
              <td className="border px-2 py-1">{teamName}</td>
              {league.data?.is_fim &&
                events.map((event, index) => (
                  <td key={index} className="border px-2 py-1">
                    {event}
                  </td>
                ))}
              <td className="border px-2 py-1">{yearEndEpa}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  return (
    <div className="w-full min-w-[1000px] overflow-x-scroll overflow-y-scroll">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-center flex-1">{league.data?.league_name}</h1>
        {league.data && !league.data.offseason && (
          <Link to="/leagues/$leagueId" params={{ leagueId: league.data.league_id.toString() }}>
            <Button variant="outline">Back to League</Button>
          </Link>
        )}
      </div>
      {league.data.offseason && (
        <div className="text-center my-4">
          <Link to="/drafts/$draftId/scores" params={{ draftId }}>
            <Button>View Draft Scores</Button>
          </Link>
        </div>
      )}

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
            ),
          )}
        </div>
      ))}
      {renderAvailableTeams()}
    </div>
  )
}

const DraftBoardCard = ({
  pick,
  team,
  year,
}: {
  pick: { round: number; pick: number }
  team: DraftPick | null
  year: number
}) => {
  const teamAvatar = useTeamAvatar(team?.team_picked, year)
  return (
    <a
      data-round={pick.round}
      data-pick={pick.pick}
      href={
        team?.team_picked !== '-1'
          ? `https://www.thebluealliance.com/team/${team?.team_picked}/${year}`
          : '#'
      }
      target={team?.team_picked !== '-1' ? '_blank' : '_self'}
      className="p-2 border rounded-xl h-16 flex flex-col relative bg-slate-700 hover:bg-slate-800 cursor-pointer text-start"
    >
      <p className="text-xl font-bold">
        {team?.team_picked !== '-1' ? team?.team_picked : ''}
      </p>
      <p className="text-sm">
      {Array.isArray(team?.events)
        ? team.events
            .filter((event) => event.week !== 99)
            .sort((a, b) => a.week - b.week)
            .map((event) => event.week)
            .join(', ')
          : ''}
      </p>

      {teamAvatar.data?.image && (
        <img
          src={`data:image/png;base64,${teamAvatar.data.image}`}
          className="aspect-square h-50% absolute bottom-0 right-0 rounded"
        />
      )}
    </a>
  )
}

export const Route = createFileRoute('/drafts//$draftId')({
  component: DraftBoard,
  validateSearch: (search: Record<string, unknown>) => {
    return {
      autoRefreshInterval: search?.autoRefreshInterval
        ? Number(search.autoRefreshInterval)
        : false as const,
    }
  },
})
