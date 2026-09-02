import { Link } from 'react-router-dom'
import type { CaseListItem } from '../../api/types'
import type { RowEconomics } from '../../hooks/usePageEconomics'
import { formatCurrency, formatPercent, formatReasonCode, formatSignedCurrency, formatStatus } from '../../utils/format'
import { DecisionBadge } from '../common/DecisionBadge'
import { DecisionSourceBadge } from '../common/DecisionSourceBadge'
import { InlineSpinner } from '../common/LoadingStates'

export function DisputeRow({ item, economics }: { item: CaseListItem; economics: RowEconomics | undefined }) {
  const scoreStatus = economics?.scoreStatus ?? 'loading'
  const decisionStatus = economics?.decisionStatus ?? 'loading'

  return (
    <tr className="border-b border-ink-800 transition-colors hover:bg-ink-850">
      <td className="px-4 py-3">
        <Link
          to={`/case/${item.dispute_id}`}
          className="font-mono text-sm font-medium text-accent-500 hover:text-accent-400 hover:underline"
        >
          {item.dispute_id}
        </Link>
      </td>
      <td className="px-4 py-3 text-sm text-ink-200">{formatReasonCode(item.reason_code)}</td>
      <td className="px-4 py-3 text-sm text-ink-400">{formatStatus(item.status)}</td>
      <td className="tabular px-4 py-3 text-right text-sm text-ink-100">{formatCurrency(item.dispute_amount)}</td>
      <td className="tabular px-4 py-3 text-right text-sm">
        {scoreStatus === 'loading' && <InlineSpinner label="scoring…" />}
        {scoreStatus === 'error' && <span className="text-avoid-500">unavailable</span>}
        {scoreStatus === 'success' && economics?.score && (
          <span className="font-medium text-ink-100">{formatPercent(economics.score.calibrated_probability)}</span>
        )}
      </td>
      <td className="tabular px-4 py-3 text-right text-sm">
        {decisionStatus === 'loading' && <InlineSpinner label="…" />}
        {decisionStatus === 'error' && <span className="text-avoid-500">unavailable</span>}
        {decisionStatus === 'success' && economics?.decision && (
          <span className={economics.decision.expected_net_value >= 0 ? 'text-contest-600' : 'text-avoid-600'}>
            {formatSignedCurrency(economics.decision.expected_net_value)}
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          {decisionStatus === 'loading' && <InlineSpinner label="deciding…" />}
          {decisionStatus === 'error' && <span className="text-xs text-avoid-500">unavailable</span>}
          {decisionStatus === 'success' && economics?.decision && (
            <>
              <DecisionBadge decision={economics.decision.decision} size="sm" />
              {economics.decisionSource === 'mock' && <DecisionSourceBadge source="mock" />}
            </>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-ink-400">
        {scoreStatus === 'success' && economics?.score ? (
          <span className="tabular">
            {economics.score.evidence_summary.available}/{economics.score.evidence_summary.total}
          </span>
        ) : (
          <span className="text-ink-600">—</span>
        )}
      </td>
    </tr>
  )
}
