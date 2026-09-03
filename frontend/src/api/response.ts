import { apiRequest } from './client'
import type { DraftResponse, VerifyResponse } from './types'

/**
 * Phase 4 Part E-I -- the full grounded-generation pipeline for one case:
 * decision + evidence gap + retrieved guidance + (if a provider is
 * configured) a structured, claim-level-verified response draft.
 *
 * Always the real /draft endpoint. There is nothing to mock here: when the
 * backend has no LLM provider configured it still returns 200 with
 * `response_state: "GENERATION_UNAVAILABLE"` and full decision/evidence-gap/
 * retrieval data (see docs/phase4.md) -- the frontend renders that state
 * honestly rather than inventing a draft.
 */
export function generateDraft(caseId: string, signal?: AbortSignal): Promise<DraftResponse> {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.log('[draft] request', caseId)
  }

  return apiRequest<DraftResponse>(`/cases/${encodeURIComponent(caseId)}/draft`, {
    method: 'POST',
    signal,
  }).then((response) => {
    if (import.meta.env.DEV) {
      // Dev-only, structure-only -- no secrets in this response to begin
      // with, but still not the full response_body text on every request.
      // eslint-disable-next-line no-console
      console.log('[draft] response', {
        case_id: response.case_id,
        response_state: response.response_state,
        response_state_reason: response.response_state_reason,
        generation_available: response.generation_available,
        claim_count: response.claims.length,
        claim_statuses: response.trace.claim_statuses,
        generated_at: response.trace.generated_at,
      })
    }
    return response
  })
}

export interface VerifyRequestClaim {
  claim_id: string
  text: string
  claim_type: string
  evidence_ids?: string[]
  source_ids?: string[]
}

/**
 * Phase 4 Part F/I -- independently re-verify a set of claims against the
 * case's own evidence packet, decoupled from generation. Not wired to any
 * editing flow yet (the app never lets an analyst edit a draft's claims),
 * but exposed as a typed client function so that flow has a real endpoint
 * to call whenever it's built, rather than inventing one client-side.
 */
export function verifyClaims(caseId: string, claims: VerifyRequestClaim[], signal?: AbortSignal): Promise<VerifyResponse> {
  return apiRequest<VerifyResponse>(`/cases/${encodeURIComponent(caseId)}/verify`, {
    method: 'POST',
    body: { claims },
    signal,
  })
}
