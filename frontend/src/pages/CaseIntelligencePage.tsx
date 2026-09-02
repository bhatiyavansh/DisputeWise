import { useParams } from 'react-router-dom'
import { CaseHeader } from '../components/case/CaseHeader'
import { CaseRawDetail } from '../components/case/CaseRawDetail'
import { DecisionExplanation } from '../components/case/DecisionExplanation'
import { EconomicDecisionPanel } from '../components/case/EconomicDecisionPanel'
import { EvidenceInventory } from '../components/case/EvidenceInventory'
import { EvidenceResponsePlaceholder } from '../components/case/EvidenceResponsePlaceholder'
import { ShapPanel } from '../components/case/ShapPanel'
import { WinnabilityCard } from '../components/case/WinnabilityCard'
import { ErrorState } from '../components/common/ErrorState'
import { SkeletonCard } from '../components/common/LoadingStates'
import { useCase, useDecision, useEvidence, useScore } from '../hooks/useCaseWorkspace'

export function CaseIntelligencePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const id = caseId ?? ''

  const caseQuery = useCase(id)
  const evidenceQuery = useEvidence(id)
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
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    )
  }

  const caseDetail = caseQuery.data
  const score = scoreQuery.data
  const decisionResult = decisionQuery.data

  return (
    <div className="flex flex-col gap-5">
      <CaseHeader
        caseDetail={caseDetail}
        score={score}
        decision={decisionResult?.data ?? null}
        evidenceSummary={score?.evidence_summary ?? null}
      />

      {/* Winnability -- #3 in the visual hierarchy */}
      {scoreQuery.status === 'loading' && <SkeletonCard />}
      {scoreQuery.status === 'error' && (
        <ErrorState error={scoreQuery.error} title="Risk scoring unavailable" onRetry={scoreQuery.refetch} compact />
      )}
      {scoreQuery.status === 'success' && score && <WinnabilityCard score={score} />}

      {/* Why the model thinks this -- #5 */}
      {scoreQuery.status === 'success' && score && (
        <ShapPanel positive={score.top_positive_factors} negative={score.top_negative_factors} />
      )}

      {/* Evidence -- #4, detailed inventory */}
      {evidenceQuery.status === 'loading' && <SkeletonCard />}
      {evidenceQuery.status === 'error' && (
        <ErrorState error={evidenceQuery.error} title="Evidence unavailable" onRetry={evidenceQuery.refetch} compact />
      )}
      {evidenceQuery.status === 'success' && evidenceQuery.data && score && (
        <EvidenceInventory evidence={evidenceQuery.data} summary={score.evidence_summary} />
      )}

      {/* Economic Decision -- #1/#2, the most important numbers on the page */}
      {decisionQuery.status === 'loading' && <SkeletonCard />}
      {decisionQuery.status === 'error' && (
        <ErrorState
          error={decisionQuery.error}
          title="Decision engine unavailable"
          onRetry={decisionQuery.refetch}
        />
      )}
      {decisionQuery.status === 'success' && decisionResult && (
        <>
          <EconomicDecisionPanel decision={decisionResult.data} source={decisionResult.source} />
          <DecisionExplanation decision={decisionResult.data} />
        </>
      )}

      <EvidenceResponsePlaceholder />

      <CaseRawDetail caseDetail={caseDetail} />
    </div>
  )
}
