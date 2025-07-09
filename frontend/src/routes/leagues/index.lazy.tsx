import { createLazyFileRoute, Link } from '@tanstack/react-router'
import { useLeagues } from '@/api/useLeagues'

export const LeaguesPage = () => {
  const leagues = useLeagues()

  if (leagues.isLoading) {
    return <div>Loading...</div>
  }

  const fimLeagues = leagues.data?.filter((l) => l.is_fim) ?? []

  return (
    <div className="space-y-2">
      <h1 className="text-3xl font-bold mb-4">Leagues</h1>
      <ul className="list-disc ml-4">
        {fimLeagues.map((league) => (
          <li key={league.league_id}>
            <Link
              to="/leagues/$leagueId"
              params={{ leagueId: league.league_id.toString() }}
              className="hover:underline"
            >
              {league.league_name}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

export const Route = createLazyFileRoute('/leagues/')({
  component: LeaguesPage,
})
