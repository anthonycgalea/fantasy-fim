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
import { useStatboticsTeamYear } from "@/api/useStatboticsTeamYear"
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

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
  const location = useLocation()

  const [selectedWeeks, setSelectedWeeks] = useState<number[]>([1, 2, 3, 4, 5])
  const [tab, setTab] = useState<'draft' | 'leagueWeeks'>('draft')

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
    const epaYear = league.data.offseason ? league.data.year : prevYear

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
          {filteredTeams.map(({ teamNumber, teamName, events }) => (
            <tr key={teamNumber}>
              <td className="border px-2 py-1">{teamNumber}</td>
              <td className="border px-2 py-1">{teamName}</td>
              {league.data?.is_fim &&
                events.map((event, index) => (
                  <td key={index} className="border px-2 py-1">
                    {event}
                  </td>
                ))}
              <td className="border px-2 py-1"><TeamEPA teamNumber={teamNumber} year={epaYear} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  return (
    <div className="w-full min-w-[1000px] overflow-x-scroll overflow-y-scroll">
      <div className="flex flex-col items-center">
        <h1 className="text-3xl font-bold text-center">{league.data?.league_name}</h1>
        {league.data && !league.data.offseason && (
          <div className="flex gap-2 mt-2">
            <Button
              variant={tab === 'draft' ? 'default' : 'outline'}
              onClick={() => setTab('draft')}
            >
              Draft
            </Button>
            <Button
              variant={tab === 'leagueWeeks' ? 'default' : 'outline'}
              onClick={() => setTab('leagueWeeks')}
            >
              League Weeks
            </Button>
            <Link to="/leagues/$leagueId" params={{ leagueId: league.data.league_id.toString() }}>
              <Button variant="outline">Back to League</Button>
            </Link>
          </div>
        )}
      </div>
      {league.data.offseason && (
        <div className="text-center my-4">
          <Link to="/drafts/$draftId/scores" params={{ draftId }}>
            <Button>View Draft Scores</Button>
          </Link>
        </div>
      )}

      {tab === 'draft' && (
        <>
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
                    key={
                      rowIndex * (draftOrder.data?.length ?? 1) + colIndex + 1
                    }
                    pick={{ round: rowIndex + 1, pick: colIndex + 1 }}
                    team={pick}
                    year={league.data?.year}
                  />
                ),
              )}
            </div>
          ))}
          {renderAvailableTeams()}
        </>
      )}

      {tab === 'leagueWeeks' && <LeagueWeeksTab />}
    </div>
  )
}

const TeamEPA = ({
  teamNumber,
  year,
}: {
  teamNumber: number
  year: number
}) => {
  const { data } = useStatboticsTeamYear(teamNumber, year)
  return <>{data ?? 'N/A'}</>
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

const LeagueWeeksTab = () => {
  const { draftId } = Route.useParams()
  const draft = useDraft(draftId)
  const league = useLeague(draft.data?.league_id.toString())
  const draftPicks = usePicks(draftId)
  const fantasyTeams = useFantasyTeams(league.data?.league_id.toString())

  if (
    draft.isLoading ||
    league.isLoading ||
    draftPicks.isLoading ||
    fantasyTeams.isLoading
  ) {
    return <div>Loading...</div>
  }

  const fantasyTeamWeekCounts: Record<number, number[]> = {}
  fantasyTeams.data?.forEach((team) => {
    fantasyTeamWeekCounts[team.fantasy_team_id] = [0, 0, 0, 0, 0]
  })

  draftPicks.data?.forEach((pick) => {
    pick.events.forEach((event) => {
      if (event.week >= 1 && event.week <= 5) {
        fantasyTeamWeekCounts[pick.fantasy_team_id][event.week - 1] += 1
      }
    })
  })

  const weeks = [1, 2, 3, 4, 5]

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Fantasy Team</TableHead>
          {weeks.map((w) => (
            <TableHead key={w}>Week {w}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {fantasyTeams.data?.map((team) => (
          <TableRow key={team.fantasy_team_id}>
            <TableCell className="font-bold">{team.team_name}</TableCell>
            {fantasyTeamWeekCounts[team.fantasy_team_id].map((count, index) => {
              let className = ''
              if (league.data && count >= league.data.weekly_starts) {
                className = 'bg-green-300'
              } else if (
                league.data &&
                count === league.data.weekly_starts - 1
              ) {
                className = 'bg-yellow-300'
              } else {
                className = 'bg-red-300'
              }
              return (
                <TableCell key={index} className={className}>
                  {count}
                </TableCell>
              )
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
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
