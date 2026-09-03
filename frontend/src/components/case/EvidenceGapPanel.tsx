import type { EvidenceGapItem, EvidenceGapResponse } from '../../api/types'
import { formatEvidenceType, formatPercent } from '../../utils/format'
import { Panel } from '../common/Panel'

const PRIORITY_CLASSES: Record<string, string> = {
  CRITICAL: 'bg-avoid-50 text-avoid-700 border-avoid-500/30',
  IMPORTANT: 'bg-review-50 text-review-700 border-review-500/30',
  OPTIONAL: 'bg-ink-800 text-ink-400 border-ink-700',
  NONE: 'bg-ink-800 text-ink-500 border-ink-700',
}

/**
 * Reason-code-driven gap analysis from POST /evidence-gap. Distinct from
 * EvidenceInventory (which lists every evidence record on file): this shows
 * only what the backend's evidence schema says is REQUIRED for this specific
 * reason code, and whether it's on file -- the coverage numbers and every
 * item's priority/relevance/reason are rendered exactly as returned.
 */
export function EvidenceGapPanel({ gap }: { gap: EvidenceGapResponse }) {
  const critical = gap.items.filter((item) => item.priority === 'CRITICAL' && item.status === 'MISSING')
  const important = gap.items.filter((item) => item.priority === 'IMPORTANT' && item.status === 'MISSING')
  const available = gap.items.filter((item) => item.status === 'AVAILABLE')

  return (
    <Panel
      title="Evidence Gap Analysis"
      subtitle={`required evidence for ${gap.reason_code.replace(/_/g, ' ')} -- evidence schema ${gap.schema_version}`}
    >
      <div className="flex flex-wrap items-center gap-6">
        <div>
          <p className="tabular text-3xl font-bold text-ink-50">{formatPercent(gap.coverage_ratio, 0)}</p>
          <p className="mt-1 text-xs text-ink-500">coverage</p>
        </div>
        <dl className="flex gap-6 text-sm">
          <div>
            <dt className="text-xs text-ink-500">Required</dt>
            <dd className="tabular font-medium text-ink-100">{gap.coverage.required}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-500">Available</dt>
            <dd className="tabular font-medium text-contest-600">{gap.coverage.available}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-500">Missing</dt>
            <dd className="tabular font-medium text-avoid-600">{gap.coverage.missing}</dd>
          </div>
        </dl>
      </div>

      {critical.length > 0 && (
        <div className="mt-5 border-t border-ink-800 pt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-avoid-600">
            Critical -- missing ({critical.length})
          </h3>
          <GapList items={critical} />
        </div>
      )}

      {important.length > 0 && (
        <div className="mt-5 border-t border-ink-800 pt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-review-600">
            Important -- missing ({important.length})
          </h3>
          <GapList items={important} />
        </div>
      )}

      {available.length > 0 && (
        <div className="mt-5 border-t border-ink-800 pt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">
            On file ({available.length})
          </h3>
          <GapList items={available} />
        </div>
      )}
    </Panel>
  )
}

function GapList({ items }: { items: EvidenceGapItem[] }) {
  return (
    <ul className="flex flex-col divide-y divide-ink-800 overflow-hidden rounded border border-ink-800">
      {items.map((item) => (
        <li key={`${item.evidence_type}-${item.source_id}`} className="flex items-start justify-between gap-3 px-3 py-2.5">
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink-100">{formatEvidenceType(item.evidence_type)}</p>
            <p className="mt-0.5 text-xs text-ink-500">{item.reason}</p>
          </div>
          <span
            className={`shrink-0 rounded border px-1.5 py-0.5 text-[11px] font-medium uppercase ${PRIORITY_CLASSES[item.priority]}`}
          >
            {item.priority}
          </span>
        </li>
      ))}
    </ul>
  )
}
