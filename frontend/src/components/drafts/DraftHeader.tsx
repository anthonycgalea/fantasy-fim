import { Link } from '@tanstack/react-router'
import { useDraft } from '@/api/useDraft'
import { useLeague } from '@/api/useLeague'
import { Button } from '@/components/ui/button'
import { useEffect } from 'react'

type DraftHeaderProps = {
  draftId: string
  tab: 'draft' | 'leagueWeeks'
  onTabChange: (tab: 'draft' | 'leagueWeeks') => void
}

const DraftHeader = ({ draftId, tab, onTabChange }: DraftHeaderProps) => {
  const draft = useDraft(draftId)
  const leagueId = draft.data?.league_id?.toString()
  const league = useLeague(leagueId)

  useEffect(() => {
    if (league.data?.offseason) {
      onTabChange('draft')
    }
  }, [league.data?.offseason, onTabChange])

  if (draft.isLoading || league.isLoading || !league.data) {
    return <div className="flex flex-col items-center">Loading draft...</div>
  }

  return (
    <div className="flex flex-col items-center">
      <h1 className="text-3xl font-bold text-center">{league.data.league_name}</h1>
      {!league.data.offseason && (
        <div className="flex gap-2 mt-2">
          <Button
            variant={tab === 'draft' ? 'default' : 'outline'}
            onClick={() => onTabChange('draft')}
          >
            Draft
          </Button>
          <Button
            variant={tab === 'leagueWeeks' ? 'default' : 'outline'}
            onClick={() => onTabChange('leagueWeeks')}
          >
            League Weeks
          </Button>
          <Link
            to="/leagues/$leagueId"
            params={{ leagueId: league.data.league_id.toString() }}
          >
            <Button variant="outline">Back to League</Button>
          </Link>
        </div>
      )}
      {league.data.offseason && (
        <div className="text-center my-4">
          <Link to="/drafts/$draftId/scores" params={{ draftId }}>
            <Button>View Draft Scores</Button>
          </Link>
        </div>
      )}
    </div>
  )
}

export default DraftHeader
