import { Outlet, useParams } from 'react-router-dom'
import { CaseHeader } from '../../components/case/CaseHeader'
import { CaseTabs } from '../../components/case/CaseTabs'
import { ErrorState } from '../../components/common/ErrorState'
import { SkeletonCard } from '../../components/common/LoadingStates'
import { useCase, useDecision, useScore } from '../../hooks/useCaseWorkspace'
import type { CaseDetail, DecisionResponse, ScoreResponse } from '../../api/types'
import type { AsyncState } from '../../hooks/useAsyncResource'

export interface CaseOutletContext {
  caseId: string
  caseDetail: CaseDetail
  scoreQuery: AsyncState<ScoreResponse> & { refetch: () => void }
  decisionQuery: AsyncState<{ data: DecisionResponse; source: 'real' | 'mock' }> & { refetch: () => void }
}

/**
 * Fetches case + score + decision once (score/decision hit the shared
 * useAsyncResource cache, so re-mounting a sub-page for the same case is
 * free) and renders the header + case-local tabs that persist across every
 * /case/:caseId/* route. Sub-pages read this data via useOutletContext
 * instead of re-declaring the same hooks.
 */
export function CaseLayout() {
  const { caseId } = useParams<{ caseId: string }>()
  const id = caseId ?? ''

  const caseQuery = useCase(id)
  const scoreQuery = useScore(id)
  const decisionQuery = useDecision(id, caseQuery.data?.dispute_amount ?? null, scoreQuery)

  if (caseQuery.status === 'error') {
    return (
      <ErrorState
        error={caseQuery.error}
        title={caseQuery.error?.kind === 'not_found' ? `Case "${id}" not found` : undefined}
        onRetry={caseQuery.refetch}
      />
    )
  }

  if (caseQuery.status !== 'success' || !caseQuery.data) {
    return (
      <div className="flex flex-col gap-5">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  const context: CaseOutletContext = {
    caseId: id,
    caseDetail: caseQuery.data,
    scoreQuery,
    decisionQuery,
  }

  return (
    <div className="flex flex-col gap-5">
      <CaseHeader
        caseDetail={caseQuery.data}
        score={scoreQuery.data}
        decision={decisionQuery.data?.data ?? null}
        evidenceSummary={scoreQuery.data?.evidence_summary ?? null}
      />
      <CaseTabs caseId={id} />
      <Outlet context={context} />
    </div>
  )
}
