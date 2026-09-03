import { useOutletContext } from 'react-router-dom'
import { CaseRawDetail } from '../../components/case/CaseRawDetail'
import { RecommendationHero } from '../../components/case/RecommendationHero'
import { ShapPanel } from '../../components/case/ShapPanel'
import { WinnabilityCard } from '../../components/case/WinnabilityCard'
import { ErrorState } from '../../components/common/ErrorState'
import { SkeletonCard } from '../../components/common/LoadingStates'
import type { CaseOutletContext } from './CaseLayout'

export function CaseOverviewPage() {
  const { caseDetail, scoreQuery, decisionQuery } = useOutletContext<CaseOutletContext>()

  return (
    <div className="flex flex-col gap-5">
      {decisionQuery.status === 'loading' && <SkeletonCard />}
      {decisionQuery.status === 'error' && (
        <ErrorState error={decisionQuery.error} title="Decision engine unavailable" onRetry={decisionQuery.refetch} compact />
      )}
      {decisionQuery.status === 'success' && decisionQuery.data && (
        <RecommendationHero decision={decisionQuery.data.data} />
      )}

      {scoreQuery.status === 'loading' && <SkeletonCard />}
      {scoreQuery.status === 'error' && (
        <ErrorState error={scoreQuery.error} title="Risk scoring unavailable" onRetry={scoreQuery.refetch} compact />
      )}
      {scoreQuery.status === 'success' && scoreQuery.data && <WinnabilityCard score={scoreQuery.data} />}

      {scoreQuery.status === 'success' && scoreQuery.data && (
        <ShapPanel positive={scoreQuery.data.top_positive_factors} negative={scoreQuery.data.top_negative_factors} />
      )}

      <CaseRawDetail caseDetail={caseDetail} />
    </div>
  )
}
