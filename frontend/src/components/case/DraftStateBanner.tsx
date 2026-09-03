import { classifyDraftResponse, type DraftOutcomeInput, type DraftOutcomeKind } from './draftOutcome'

const KIND_CLASSES: Record<DraftOutcomeKind, string> = {
  ready: 'border-contest-500/30 bg-contest-50/5 text-contest-700',
  flagged: 'border-review-500/30 bg-review-50/5 text-review-700',
  verifier_blocked: 'border-avoid-500/30 bg-avoid-50/5 text-avoid-700',
  provider_unavailable: 'border-review-500/30 bg-review-50/5 text-review-700',
  generation_failed: 'border-review-500/30 bg-review-50/5 text-review-700',
  generation_unavailable: 'border-ink-700 bg-ink-800 text-ink-300',
  // Transport failures never reach this component -- no response exists to
  // render -- but the map must be total.
  network: 'border-avoid-500/30 bg-avoid-50/5 text-avoid-700',
  backend_error: 'border-avoid-500/30 bg-avoid-50/5 text-avoid-700',
}

/**
 * The outcome of a /draft response, classified from the response contract
 * (`response_state` + `generation_error_kind`) rather than from HTTP status.
 *
 * A blocked or unavailable state is never softened, hidden or re-labeled as
 * ready. Equally, an AI-provider outage is never presented as a verifier
 * rejection: the backend reports both as DRAFT_BLOCKED, but when no draft
 * was ever written there was nothing to verify.
 *
 * The backend's own `response_state_reason` is always shown verbatim beneath
 * the summary, so the precise machine reason is never lost.
 */
export function DraftStateBanner({ draft }: { draft: DraftOutcomeInput }) {
  const outcome = classifyDraftResponse(draft)

  return (
    <div className={`flex flex-col gap-1 rounded-lg border px-4 py-3 ${KIND_CLASSES[outcome.kind]}`} role="status">
      <p className="text-sm font-semibold">{outcome.title}</p>
      <p className="text-sm opacity-90">{outcome.message}</p>

      {draft.response_state_reason && (
        <p className="mt-1 text-xs opacity-75">{draft.response_state_reason}</p>
      )}

      {(outcome.kind === 'provider_unavailable' || outcome.kind === 'generation_failed') && (
        <p className="mt-1 text-xs opacity-80">
          No draft was produced, so nothing was verified. Scoring, the decision, evidence gaps and retrieved
          requirements for this case are unaffected.
        </p>
      )}
    </div>
  )
}
