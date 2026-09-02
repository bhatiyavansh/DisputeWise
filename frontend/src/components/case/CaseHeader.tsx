import type { CaseDetail, DecisionResponse, EvidenceSummary, ScoreResponse } from '../../api/types'
import { formatCurrency, formatPercent, formatReasonCode } from '../../utils/format'
import { DecisionBadge } from '../common/DecisionBadge'

/**
 * Compact summary strip: "understand the case in seconds" (spec §13). The
 * decision badge is shown here, at the very top, so it is never buried
 * beneath raw data (spec §25).
 */
export function CaseHeader({
  caseDetail,
  score,
  decision,
  evidenceSummary,
}: {
  caseDetail: CaseDetail
  score: ScoreResponse | null
  decision: DecisionResponse | null
  evidenceSummary: EvidenceSummary | null
}) {
  return (
    <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-mono text-xl font-semibold text-ink-50">{caseDetail.dispute_id}</h1>
          <p className="mt-0.5 text-sm text-ink-400">{formatReasonCode(caseDetail.reason_code)}</p>
        </div>
        {decision && <DecisionBadge decision={decision.decision} size="lg" />}
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric label="Disputed" value={formatCurrency(caseDetail.dispute_amount)} />
        <Metric label="P(win)" value={score ? formatPercent(score.calibrated_probability) : '—'} />
        <Metric
          label="Expected Net Value"
          value={decision ? formatCurrency(decision.expected_net_value, true) : '—'}
          tone={decision ? (decision.expected_net_value >= 0 ? 'positive' : 'negative') : undefined}
        />
        <Metric
          label="Evidence"
          value={evidenceSummary ? `${evidenceSummary.available} / ${evidenceSummary.total} available` : '—'}
        />
      </dl>
    </div>
  )
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'positive' | 'negative' }) {
  const toneClass = tone === 'positive' ? 'text-contest-600' : tone === 'negative' ? 'text-avoid-600' : 'text-ink-50'
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className={`tabular mt-1 text-lg font-semibold ${toneClass}`}>{value}</dd>
    </div>
  )
}
