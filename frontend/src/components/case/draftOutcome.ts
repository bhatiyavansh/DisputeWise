import type { ApiError } from '../../api/client'
import type { GenerationErrorKind, ResponseState } from '../../api/types'

/**
 * Classifies what actually happened to a /draft request.
 *
 * The distinction that matters: a request that never produced a response
 * (transport failure) is NOT the same as a response that says the AI
 * provider was unavailable. The backend answering "the LLM is overloaded"
 * is a successful HTTP exchange carrying an application state, and must
 * never be reported as an unreachable backend.
 *
 * Classification therefore uses the real Phase 8 response contract --
 * `response_state` and `generation_error_kind` -- whenever a response
 * exists, and only falls back to transport-level classification when one
 * does not.
 */

export type DraftOutcomeKind =
  | 'network' // A -- no response at all
  | 'backend_error' // A -- backend responded, but with an HTTP error
  | 'provider_unavailable' // B -- response says the LLM provider was unusable
  | 'generation_failed' // C -- response says generation failed for another reason
  | 'verifier_blocked' // D -- a draft was generated, verification rejected it
  | 'generation_unavailable' // E -- no provider configured
  | 'ready' // F -- usable, verified draft
  | 'flagged' // F -- draft returned for review

export interface DraftOutcome {
  kind: DraftOutcomeKind
  title: string
  message: string
  /** True when the failure is about the AI layer only, so the rest of the
   * case analysis is still valid and worth saying so. */
  analysisStillAvailable: boolean
}

/**
 * The minimal response shape needed to classify an outcome. Structural
 * rather than tied to DraftResponse, so the simulation endpoint's generation
 * block (same fields, different envelope) classifies through the same code.
 */
export interface DraftOutcomeInput {
  response_state: ResponseState
  response_state_reason: string
  generation_error_kind?: GenerationErrorKind
}

/** A response exists: classify from the response contract, never from status. */
export function classifyDraftResponse(draft: DraftOutcomeInput): DraftOutcome {
  // The provider could not be used at all -- no draft was written, so
  // nothing was verified. Reported before response_state because the
  // backend represents this as DRAFT_BLOCKED (Phase 4 contract) and calling
  // it "blocked by the verifier" would be wrong.
  if (draft.generation_error_kind === 'provider_unavailable') {
    return {
      kind: 'provider_unavailable',
      title: 'AI generation temporarily unavailable',
      message:
        'The risk analysis is available, but the configured AI provider is temporarily unavailable. Retry later.',
      analysisStillAvailable: true,
    }
  }

  if (draft.generation_error_kind === 'invalid_output') {
    return {
      kind: 'generation_failed',
      title: 'AI generation failed',
      message:
        'The AI provider responded, but its output did not match the required response schema, so it was rejected. No draft was produced.',
      analysisStillAvailable: true,
    }
  }

  if (draft.response_state === 'GENERATION_UNAVAILABLE') {
    return {
      kind: 'generation_unavailable',
      title: 'AI generation unavailable',
      message:
        'The risk and evidence analysis are still available; response generation is not configured.',
      analysisStillAvailable: true,
    }
  }

  if (draft.response_state === 'DRAFT_BLOCKED') {
    return {
      kind: 'verifier_blocked',
      title: 'AI response blocked',
      message: 'One or more generated claims could not be verified against the case evidence.',
      analysisStillAvailable: true,
    }
  }

  if (draft.response_state === 'DRAFT_FLAGGED') {
    return {
      kind: 'flagged',
      title: 'Draft flagged for review',
      message: 'The draft was generated and verified, but at least one claim needs a human look.',
      analysisStillAvailable: true,
    }
  }

  return {
    kind: 'ready',
    title: 'Draft ready',
    message: 'Every material claim is supported by this case’s evidence and retrieved guidance.',
    analysisStillAvailable: true,
  }
}

/** No response exists: classify the transport/backend failure. */
export function classifyDraftError(error: ApiError | null | undefined): DraftOutcome {
  if (!error || error.kind === 'network') {
    return {
      kind: 'network',
      title: 'Backend unreachable',
      message: 'The request could not reach the backend. Check that it is running, then try again.',
      analysisStillAvailable: false,
    }
  }

  if (error.kind === 'unavailable') {
    return {
      kind: 'backend_error',
      title: 'Response generation unavailable',
      message: error.message || 'The backend reported that this capability is not currently available.',
      analysisStillAvailable: false,
    }
  }

  if (error.kind === 'not_found') {
    return {
      kind: 'backend_error',
      title: 'Case not found',
      message: error.message || 'This case ID does not exist in the current dataset.',
      analysisStillAvailable: false,
    }
  }

  return {
    kind: 'backend_error',
    title: 'Response generation failed',
    message: error.message || 'The backend returned an unexpected error while generating the response.',
    analysisStillAvailable: false,
  }
}
