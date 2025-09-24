import { createFileRoute } from '@tanstack/react-router'
import { Suspense, lazy, useState } from 'react'

const DraftHeader = lazy(() => import('@/components/drafts/DraftHeader'))
const DraftBoardContent = lazy(() => import('@/components/drafts/DraftBoardContent'))
const AvailableTeamsSection = lazy(() => import('@/components/drafts/AvailableTeamsSection'))
const LeagueWeeksTab = lazy(() => import('@/components/drafts/LeagueWeeksTab'))

type DraftTab = 'draft' | 'leagueWeeks'

const DraftPage = () => {
  const { draftId } = Route.useParams()
  const { autoRefreshInterval } = Route.useSearch()
  const [tab, setTab] = useState<DraftTab>('draft')

  return (
    <div className="w-full min-w-[1000px] overflow-x-scroll overflow-y-scroll">
      <Suspense fallback={<div>Loading draft information...</div>}>
        <DraftHeader draftId={draftId} tab={tab} onTabChange={setTab} />
      </Suspense>
      {tab === 'draft' ? (
        <>
          <Suspense fallback={<div>Loading draft board...</div>}>
            <DraftBoardContent
              draftId={draftId}
              autoRefreshInterval={autoRefreshInterval ?? false}
            />
          </Suspense>
          <Suspense fallback={<div>Loading available teams...</div>}>
            <AvailableTeamsSection draftId={draftId} />
          </Suspense>
        </>
      ) : (
        <Suspense fallback={<div>Loading league weeks...</div>}>
          <LeagueWeeksTab draftId={draftId} />
        </Suspense>
      )}
    </div>
  )
}

export const Route = createFileRoute('/drafts//$draftId')({
  component: DraftPage,
  validateSearch: (search: Record<string, unknown>) => {
    return {
      autoRefreshInterval: search?.autoRefreshInterval
        ? Number(search.autoRefreshInterval)
        : (false as const),
    }
  },
})
