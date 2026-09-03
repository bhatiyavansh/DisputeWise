import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { AuditTrailTimeline } from '../../components/case/AuditTrailTimeline'
import { Panel } from '../../components/common/Panel'
import { ErrorState } from '../../components/common/ErrorState'
import { InlineSpinner, SkeletonCard } from '../../components/common/LoadingStates'
import { useDraft, useEvidenceGap } from '../../hooks/useCaseWorkspace'
import type { CaseOutletContext } from './CaseLayout'

export function CaseAuditPage() {
  const { caseId, scoreQuery, decisionQuery } = useOutletContext<CaseOutletContext>()
  const gapQuery = useEvidenceGap(caseId)
  const [includeGeneration, setIncludeGeneration] = useState(false)
  const draftQuery = useDraft(caseId, includeGeneration)

  if (scoreQuery.status === 'loading' || decisionQuery.status === 'loading') return <SkeletonCard />

  if (scoreQuery.status === 'error') {
    return <ErrorState error={scoreQuery.error} title="Risk scoring unavailable" onRetry={scoreQuery.refetch} />
  }
  if (decisionQuery.status === 'error') {
    return <ErrorState error={decisionQuery.error} title="Decision engine unavailable" onRetry={decisionQuery.refetch} />
  }
  if (!scoreQuery.data || !decisionQuery.data) return null

  return (
    <div className="flex flex-col gap-5">
      <Panel title="Audit Trail" subtitle="model, policy, and provenance versions for this case's pipeline run">
        <AuditTrailTimeline
          score={scoreQuery.data}
          decision={decisionQuery.data.data}
          gap={gapQuery.data}
          draft={draftQuery.data}
        />

        {!includeGeneration && (
          <button
            type="button"
            onClick={() => setIncludeGeneration(true)}
            className="mt-2 rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-xs font-medium text-ink-200 transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
          >
            Include response-generation provenance
          </button>
        )}
        {includeGeneration && draftQuery.status === 'loading' && (
          <div className="mt-3">
            <InlineSpinner label="Loading generation provenance…" />
          </div>
        )}
        {includeGeneration && draftQuery.status === 'error' && (
          <p className="mt-3 text-xs text-avoid-600">Could not load response-generation provenance: {draftQuery.error?.message}</p>
        )}
      </Panel>
    </div>
  )
}
