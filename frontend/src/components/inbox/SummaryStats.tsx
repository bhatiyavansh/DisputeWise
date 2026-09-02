import type { CaseListItem, Decision } from '../../api/types'
import type { RowEconomics } from '../../hooks/usePageEconomics'
import { formatCurrency } from '../../utils/format'

function StatCard({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: 'contest' | 'review' | 'avoid' }) {
  const toneClass = tone === 'contest' ? 'text-contest-600' : tone === 'review' ? 'text-review-600' : tone === 'avoid' ? 'text-avoid-600' : 'text-ink-50'
  return (
    <div className="rounded-lg border border-ink-800 bg-ink-900 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className={`tabular mt-1.5 text-2xl font-semibold ${toneClass}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  )
}

/**
 * Two kinds of numbers here, deliberately labeled differently:
 *   - "Total disputes (filtered)" comes from the API's own pagination
 *     `total`, which is a true dataset-wide count under the active filters.
 *   - Amount/decision breakdowns are computed from whatever is currently
 *     loaded on THIS PAGE, because there is no bulk-scoring backend
 *     endpoint. This is stated explicitly rather than presented as a
 *     dataset-wide figure it is not.
 */
export function SummaryStats({
  total,
  items,
  economics,
}: {
  total: number
  items: CaseListItem[]
  economics: Map<string, RowEconomics>
}) {
  const loadedAmount = items.reduce((sum, item) => sum + (Number.parseFloat(item.dispute_amount) || 0), 0)

  let recoverable = 0
  let resolvedDecisions = 0
  const counts: Record<Decision, number> = { CONTEST: 0, HUMAN_REVIEW: 0, DO_NOT_CONTEST: 0 }
  for (const item of items) {
    const row = economics.get(item.dispute_id)
    if (row?.decisionStatus === 'success' && row.decision) {
      resolvedDecisions += 1
      counts[row.decision.decision] += 1
      if (row.decision.decision === 'CONTEST') {
        recoverable += row.decision.recoverable_amount
      }
    }
  }
  const pending = items.length - resolvedDecisions

  return (
    <div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <StatCard label="Total Disputes (filtered)" value={total.toLocaleString('en-IN')} hint="dataset-wide, via /cases" />
        <StatCard label="Disputed Amount" value={formatCurrency(loadedAmount)} hint={`this page (${items.length} cases)`} />
        <StatCard
          label="Recoverable (CONTEST)"
          value={formatCurrency(recoverable)}
          hint={pending > 0 ? `this page · ${pending} still scoring` : 'this page'}
        />
        <StatCard label="Contest" value={String(counts.CONTEST)} tone="contest" hint="this page" />
        <StatCard label="Human Review" value={String(counts.HUMAN_REVIEW)} tone="review" hint="this page" />
        <StatCard label="Don't Contest" value={String(counts.DO_NOT_CONTEST)} tone="avoid" hint="this page" />
      </div>
    </div>
  )
}
