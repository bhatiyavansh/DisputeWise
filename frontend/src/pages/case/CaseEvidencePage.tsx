import { useOutletContext } from 'react-router-dom'
import { EvidenceGapPanel } from '../../components/case/EvidenceGapPanel'
import { EvidenceScenarioPanel } from '../../components/case/EvidenceScenarioPanel'
import { EvidenceInventory } from '../../components/case/EvidenceInventory'
import { EvidencePacketViewer } from '../../components/case/EvidencePacketViewer'
import { ErrorState } from '../../components/common/ErrorState'
import { SkeletonCard } from '../../components/common/LoadingStates'
import { useEvidence, useEvidenceGap, useEvidencePacket } from '../../hooks/useCaseWorkspace'
import type { CaseOutletContext } from './CaseLayout'

export function CaseEvidencePage() {
  const { caseId, scoreQuery } = useOutletContext<CaseOutletContext>()
  const evidenceQuery = useEvidence(caseId)
  const gapQuery = useEvidenceGap(caseId)
  const packetQuery = useEvidencePacket(caseId)

  return (
    <div className="flex flex-col gap-5">
      {gapQuery.status === 'loading' && <SkeletonCard />}
      {gapQuery.status === 'error' && (
        <ErrorState error={gapQuery.error} title="Evidence gap analysis unavailable" onRetry={gapQuery.refetch} compact />
      )}
      {gapQuery.status === 'success' && gapQuery.data && (
        <>
          <EvidenceGapPanel gap={gapQuery.data} />
          <EvidenceScenarioPanel caseId={caseId} gap={gapQuery.data} />
        </>
      )}

      {evidenceQuery.status === 'loading' && <SkeletonCard />}
      {evidenceQuery.status === 'error' && (
        <ErrorState error={evidenceQuery.error} title="Evidence unavailable" onRetry={evidenceQuery.refetch} compact />
      )}
      {evidenceQuery.status === 'success' && evidenceQuery.data && scoreQuery.data && (
        <EvidenceInventory evidence={evidenceQuery.data} summary={scoreQuery.data.evidence_summary} />
      )}

      {packetQuery.status === 'loading' && <SkeletonCard />}
      {packetQuery.status === 'error' && (
        <ErrorState error={packetQuery.error} title="Evidence packet unavailable" onRetry={packetQuery.refetch} compact />
      )}
      {packetQuery.status === 'success' && packetQuery.data && <EvidencePacketViewer packet={packetQuery.data} />}
    </div>
  )
}
