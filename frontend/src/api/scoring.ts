import { apiRequest } from './client'
import type { ScoreResponse } from './types'

/** Always the real Phase 2 /score endpoint -- no mock exists or is needed here. */
export function scoreCase(caseId: string, signal?: AbortSignal): Promise<ScoreResponse> {
  return apiRequest<ScoreResponse>(`/cases/${encodeURIComponent(caseId)}/score`, {
    method: 'POST',
    signal,
  })
}
