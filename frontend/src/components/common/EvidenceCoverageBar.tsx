import type { EvidenceSummary } from '../../api/types'
import { formatEvidenceType } from '../../utils/format'

/**
 * Reusable evidence-coverage visualization, built from real EvidenceSummary
 * fields only -- every percentage is computed here, never received
 * pre-computed from the API. Intentionally standalone (no Panel wrapper) so
 * Phase 4's Evidence Gap Analyzer can drop it into a different layout.
 */
export function EvidenceCoverageBar({ summary }: { summary: EvidenceSummary }) {
  const coveragePct = summary.total > 0 ? Math.round((summary.available / summary.total) * 100) : 0
  const highRelevancePct =
    summary.high_relevance_total > 0 ? Math.round((summary.high_relevance_available / summary.high_relevance_total) * 100) : 0

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-400">Evidence Coverage</span>
        <span className="tabular text-sm font-semibold text-ink-100">{coveragePct}%</span>
      </div>
      <div
        className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-ink-800"
        role="progressbar"
        aria-valuenow={coveragePct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Evidence coverage"
      >
        <div
          className={`h-full rounded-full transition-all ${coveragePct >= 80 ? 'bg-contest-500' : coveragePct >= 50 ? 'bg-review-500' : 'bg-avoid-500'}`}
          style={{ width: `${coveragePct}%` }}
        />
      </div>
      <p className="tabular mt-1.5 text-xs text-ink-500">
        {summary.available} / {summary.total} available &middot; {summary.strong} strong &middot;{' '}
        {summary.high_relevance_available} / {summary.high_relevance_total} high-relevance ({highRelevancePct}%)
      </p>

      {summary.missing_key_types.length > 0 && (
        <div className="mt-3 rounded border border-review-500/30 bg-review-50/5 px-3 py-2">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-review-600">
            <span aria-hidden="true">⚠</span> Missing high-relevance evidence
          </p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {summary.missing_key_types.map((type) => (
              <li key={type} className="rounded bg-review-50/10 px-1.5 py-0.5 text-xs text-review-600">
                {formatEvidenceType(type)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
