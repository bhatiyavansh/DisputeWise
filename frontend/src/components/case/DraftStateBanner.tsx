import type { ResponseState } from '../../api/types'

const STATE_COPY: Record<ResponseState, { label: string; classes: string }> = {
  DRAFT_READY: { label: 'Draft ready', classes: 'border-contest-500/30 bg-contest-50/5 text-contest-700' },
  DRAFT_FLAGGED: { label: 'Draft flagged for review', classes: 'border-review-500/30 bg-review-50/5 text-review-700' },
  DRAFT_BLOCKED: { label: 'Draft blocked', classes: 'border-avoid-500/30 bg-avoid-50/5 text-avoid-700' },
  GENERATION_UNAVAILABLE: { label: 'Generation unavailable', classes: 'border-ink-700 bg-ink-800 text-ink-300' },
}

/**
 * Renders the backend's own response_state verbatim. A blocked or
 * unavailable state is never softened, hidden, or re-labeled as ready --
 * this is the whole point of having a verifier in the loop.
 */
export function DraftStateBanner({ state, reason }: { state: ResponseState; reason: string }) {
  const copy = STATE_COPY[state]
  return (
    <div className={`flex flex-col gap-1 rounded-lg border px-4 py-3 ${copy.classes}`} role="status">
      <p className="text-sm font-semibold">{copy.label}</p>
      <p className="text-sm opacity-90">{reason}</p>
    </div>
  )
}
