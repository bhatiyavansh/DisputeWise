import type { GenerationErrorKind, ResponseState } from '../../api/types'

const STATE_COPY: Record<ResponseState, { label: string; classes: string }> = {
  DRAFT_READY: { label: 'Draft ready', classes: 'border-contest-500/30 bg-contest-50/5 text-contest-700' },
  DRAFT_FLAGGED: { label: 'Draft flagged for review', classes: 'border-review-500/30 bg-review-50/5 text-review-700' },
  DRAFT_BLOCKED: { label: 'Draft blocked by verifier', classes: 'border-avoid-500/30 bg-avoid-50/5 text-avoid-700' },
  GENERATION_UNAVAILABLE: { label: 'AI generation unavailable', classes: 'border-ink-700 bg-ink-800 text-ink-300' },
}

/**
 * The backend's own response_state, never softened, hidden or re-labeled as
 * ready -- that is the whole point of having a verifier in the loop.
 *
 * One refinement over rendering response_state alone: the backend reports
 * DRAFT_BLOCKED for every generation failure, including one where the model
 * was never reachable and no draft was ever written. Calling that "blocked by
 * verifier" would be wrong -- there was nothing to verify. When the backend
 * says the failure was a provider problem (generation_error_kind), this is
 * presented as an AI-availability problem instead. The state itself is still
 * shown verbatim, and neither presentation implies a usable draft exists.
 */
export function DraftStateBanner({
  state,
  reason,
  errorKind = null,
}: {
  state: ResponseState
  reason: string
  errorKind?: GenerationErrorKind
}) {
  const isProviderProblem = errorKind === 'provider_unavailable' || errorKind === 'invalid_output'

  const copy = isProviderProblem
    ? {
        label:
          errorKind === 'provider_unavailable'
            ? 'AI generation temporarily unavailable'
            : 'AI generation returned unusable output',
        classes: 'border-review-500/30 bg-review-50/5 text-review-700',
      }
    : STATE_COPY[state]

  return (
    <div className={`flex flex-col gap-1 rounded-lg border px-4 py-3 ${copy.classes}`} role="status">
      <p className="text-sm font-semibold">{copy.label}</p>
      <p className="text-sm opacity-90">{reason}</p>
      {isProviderProblem && (
        <p className="mt-1 text-xs opacity-80">
          No draft was produced, so nothing was verified. Everything else on this case — scoring, the decision,
          evidence gaps and retrieved requirements — is unaffected. You can try generating again.
        </p>
      )}
    </div>
  )
}
