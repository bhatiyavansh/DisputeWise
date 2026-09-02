/**
 * Renders ONLY when a decision came from the dev-only mock adapter
 * (src/api/devDecisionMock.ts), so a mock decision can never be mistaken for
 * a real backend response. See src/api/decisions.ts for when this can fire
 * (dev builds only, explicit opt-in, real endpoint unavailable).
 */
export function DecisionSourceBadge({ source }: { source: 'real' | 'mock' }) {
  if (source !== 'mock') return null
  return (
    <span
      className="inline-flex items-center gap-1 rounded border border-review-500/50 bg-review-50 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-review-700"
      title="The real /decision endpoint was unavailable; this is a local development placeholder, not the real decision engine."
    >
      ⚠ Dev Mock
    </span>
  )
}
