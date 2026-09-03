import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { DecisionExplanation } from '../../components/case/DecisionExplanation'
import { EconomicDecisionPanel } from '../../components/case/EconomicDecisionPanel'
import { EvidenceScenarioPanel } from '../../components/case/EvidenceScenarioPanel'
import { ErrorState } from '../../components/common/ErrorState'
import { InlineSpinner, SkeletonCard } from '../../components/common/LoadingStates'
import { useEvidenceGap } from '../../hooks/useCaseWorkspace'
import type { CaseOutletContext } from './CaseLayout'

export function CaseDecisionPage() {
  const { caseId, decisionQuery } = useOutletContext<CaseOutletContext>()

  if (decisionQuery.status === 'loading') {
    return (
      <div className="flex flex-col gap-5">
        <SkeletonCard />
      </div>
    )
  }

  if (decisionQuery.status === 'error') {
    return <ErrorState error={decisionQuery.error} title="Decision engine unavailable" onRetry={decisionQuery.refetch} />
  }

  if (decisionQuery.status !== 'success' || !decisionQuery.data) return null

  const decision = decisionQuery.data.data

  return (
    <div className="flex flex-col gap-5">
      <EconomicDecisionPanel decision={decision} source={decisionQuery.data.source} />
      <DecisionExplanation decision={decision} />
      <ScenarioLauncher caseId={caseId} gapDowngraded={decision.evidence_gap_downgrade} />
    </div>
  )
}

/**
 * Makes evidence scenario analysis reachable from the decision context --
 * the point at which "what would change if I had that evidence?" actually
 * arises. Renders the SAME EvidenceScenarioPanel the Evidence tab uses (same
 * component, same backend endpoint, same types) -- a discovery affordance,
 * not a second implementation. The gap it needs is cached by
 * useAsyncResource, so opening it here reuses the Evidence tab's fetch (or
 * vice versa) rather than issuing a second request.
 */
function ScenarioLauncher({ caseId, gapDowngraded }: { caseId: string; gapDowngraded: boolean }) {
  const [open, setOpen] = useState(false)
  const gapQuery = useEvidenceGap(caseId, open)

  if (!open) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-800 bg-ink-900 px-5 py-4">
        <p className="max-w-xl text-sm text-ink-400">
          {gapDowngraded
            ? 'This case was routed to human review because evidence required for its reason code is missing. What would change if it were on file?'
            : 'See how this decision would change if evidence were added or removed.'}
        </p>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="shrink-0 rounded bg-accent-600 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500"
        >
          Explore evidence scenario
        </button>
      </div>
    )
  }

  if (gapQuery.status === 'loading' || gapQuery.status === 'idle') {
    return (
      <div className="rounded-lg border border-ink-800 bg-ink-900 px-5 py-6">
        <InlineSpinner label="Loading evidence requirements…" />
      </div>
    )
  }

  if (gapQuery.status === 'error') {
    return (
      <ErrorState
        error={gapQuery.error}
        title="Evidence gap analysis unavailable"
        onRetry={gapQuery.refetch}
        compact
      />
    )
  }

  if (!gapQuery.data) return null
  return <EvidenceScenarioPanel caseId={caseId} gap={gapQuery.data} />
}
