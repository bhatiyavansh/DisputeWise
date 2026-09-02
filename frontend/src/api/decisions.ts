/**
 * The /decision adapter.
 *
 * ALWAYS tries the real Phase 3 /cases/{id}/decision endpoint first -- it is
 * live and this is the source of truth. The dev-only mock
 * (src/api/devDecisionMock.ts) is used ONLY as a fallback, and ONLY when:
 *
 *   1. `import.meta.env.DEV` is true (impossible in a production build), AND
 *   2. `VITE_ENABLE_DECISION_MOCK=true` is explicitly set, AND
 *   3. the real endpoint failed with 'unavailable' (503) or 'network'
 *      (backend unreachable) -- never on 404 (case genuinely doesn't exist)
 *      or 422 (the case's own data is invalid); a mock can't meaningfully
 *      stand in for either of those.
 *
 * The returned `source` field is never hidden from the UI -- see
 * DecisionSourceBadge, which renders a visible "DEV MOCK" indicator whenever
 * source === 'mock', so a mock decision can never be silently mistaken for a
 * real one.
 */

import { apiRequest, ApiError } from './client'
import { mockDecideCase } from './devDecisionMock'
import type { DecisionResponse, ScoreResponse } from './types'

export interface DecisionResult {
  data: DecisionResponse
  source: 'real' | 'mock'
}

function mockFallbackEnabled(): boolean {
  return import.meta.env.DEV === true && import.meta.env.VITE_ENABLE_DECISION_MOCK === 'true'
}

function isMockEligibleFailure(error: unknown): boolean {
  return error instanceof ApiError && (error.kind === 'unavailable' || error.kind === 'network')
}

/**
 * Fetch the decision for a case. `score` (already fetched for the case
 * detail page) and `disputeAmount` are only used if the mock fallback fires
 * -- the real endpoint needs neither.
 */
export async function decideCase(
  caseId: string,
  context: { score?: ScoreResponse; disputeAmount?: number },
  signal?: AbortSignal,
): Promise<DecisionResult> {
  try {
    const data = await apiRequest<DecisionResponse>(`/cases/${encodeURIComponent(caseId)}/decision`, {
      method: 'POST',
      signal,
    })
    return { data, source: 'real' }
  } catch (error) {
    if (mockFallbackEnabled() && isMockEligibleFailure(error) && context.score) {
      // eslint-disable-next-line no-console
      console.warn(
        `[DisputeWise DEV MOCK] Real /decision endpoint unavailable for ${caseId}; falling back to ` +
          'the local placeholder in src/api/devDecisionMock.ts. This must never happen in production.',
      )
      const data = await mockDecideCase(caseId, context.score, context.disputeAmount)
      return { data, source: 'mock' }
    }
    throw error
  }
}
