import type { DecisionResponse } from '../../api/types'
import { formatEvidenceType, formatPercent } from '../../utils/format'
import { DecisionBadge } from '../common/DecisionBadge'

/**
 * The case overview's visual hero: what should I do, how confident is the
 * model, why, and what's next -- in that order, before any technical detail.
 *
 * Every value is read straight from the /decision response. "Why" is the
 * backend's own `reason` string, rendered verbatim -- never rewritten or
 * summarized. "Next action" is derived, not invented: it names the actual
 * missing evidence types from `evidence_summary.missing_key_types` when the
 * decision was gap-downgraded, or a plain statement to proceed otherwise.
 * There is no client-side logic here that decides anything -- it only
 * chooses which already-true sentence to display.
 */
export function RecommendationHero({ decision }: { decision: DecisionResponse }) {
  const missing = decision.evidence_summary.missing_key_types

  return (
    <section className="rounded-lg border border-ink-800 bg-ink-900 p-6">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">Recommendation</p>

      <div className="mt-2 flex flex-wrap items-end justify-between gap-6">
        <DecisionBadge decision={decision.decision} size="lg" />
        <div className="text-right">
          <p className="tabular text-4xl font-bold text-ink-50">{formatPercent(decision.calibrated_probability, 1)}</p>
          <p className="mt-0.5 text-xs text-ink-500">estimated chance of winning</p>
        </div>
      </div>

      <div className="mt-5 border-t border-ink-800 pt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-500">Why</p>
        <p className="mt-1 text-sm leading-relaxed text-ink-200">{decision.reason}</p>
      </div>

      <div className="mt-4 border-t border-ink-800 pt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-500">Next action</p>
        {decision.evidence_gap_downgrade && missing.length > 0 ? (
          <p className="mt-1 text-sm text-ink-200">
            Review or obtain: <span className="font-medium text-review-700">{missing.map(formatEvidenceType).join(', ')}</span>
          </p>
        ) : decision.decision === 'CONTEST' ? (
          <p className="mt-1 text-sm text-ink-200">Evidence coverage supports contesting — proceed to the response workspace.</p>
        ) : decision.decision === 'DO_NOT_CONTEST' ? (
          <p className="mt-1 text-sm text-ink-200">Economics do not support contesting this case.</p>
        ) : (
          <p className="mt-1 text-sm text-ink-200">Route to a human reviewer for a final call.</p>
        )}
      </div>
    </section>
  )
}
