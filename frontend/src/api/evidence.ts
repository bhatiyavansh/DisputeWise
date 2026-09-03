import { apiRequest } from './client'
import type { EvidenceGapResponse, EvidencePacketResponse } from './types'

/** Phase 4 Part A -- reason-code-driven evidence gap analysis. Real endpoint only. */
export function getEvidenceGap(caseId: string, signal?: AbortSignal): Promise<EvidenceGapResponse> {
  return apiRequest<EvidenceGapResponse>(`/cases/${encodeURIComponent(caseId)}/evidence-gap`, {
    method: 'POST',
    signal,
  })
}

/** Phase 4 Part B -- the full evidence packet (facts + evidence + gap + guidance). */
export function getEvidencePacket(caseId: string, signal?: AbortSignal): Promise<EvidencePacketResponse> {
  return apiRequest<EvidencePacketResponse>(`/cases/${encodeURIComponent(caseId)}/evidence-packet`, {
    method: 'POST',
    signal,
  })
}
