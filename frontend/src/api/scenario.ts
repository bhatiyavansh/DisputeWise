import { apiRequest } from './client'
import type { EvidenceScenarioRequest, EvidenceScenarioResponse } from './types'

/**
 * Phase 7A -- "what if this evidence were added or removed?" for a real case.
 *
 * Read-only on the backend: it evaluates the case twice (as-is and under the
 * hypothetical evidence state) and returns both sides. The stored case is
 * never modified and the scenario is never saved.
 */
export function runEvidenceScenario(
  caseId: string,
  request: EvidenceScenarioRequest,
  signal?: AbortSignal,
): Promise<EvidenceScenarioResponse> {
  return apiRequest<EvidenceScenarioResponse>(`/cases/${encodeURIComponent(caseId)}/evidence-scenario`, {
    method: 'POST',
    body: request,
    signal,
    timeoutMs: 30_000,
  })
}
