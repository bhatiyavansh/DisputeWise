import { useOutletContext } from 'react-router-dom'
import { DecisionExplanation } from '../../components/case/DecisionExplanation'
import { EconomicDecisionPanel } from '../../components/case/EconomicDecisionPanel'
import { ErrorState } from '../../components/common/ErrorState'
import { SkeletonCard } from '../../components/common/LoadingStates'
import type { CaseOutletContext } from './CaseLayout'

export function CaseDecisionPage() {
  const { decisionQuery } = useOutletContext<CaseOutletContext>()

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

  return (
    <div className="flex flex-col gap-5">
      <EconomicDecisionPanel decision={decisionQuery.data.data} source={decisionQuery.data.source} />
      <DecisionExplanation decision={decisionQuery.data.data} />
    </div>
  )
}
