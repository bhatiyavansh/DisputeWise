import type { EvidenceItem, EvidenceSummary } from '../../api/types'
import { EVIDENCE_CATEGORIES } from '../../utils/evidenceCategories'
import { formatEvidenceType, formatEvidenceValue } from '../../utils/format'
import { EvidenceCoverageBar } from '../common/EvidenceCoverageBar'
import { Panel } from '../common/Panel'

const RELEVANCE_CLASSES: Record<string, string> = {
  high: 'bg-avoid-50 text-avoid-700',
  medium: 'bg-review-50 text-review-700',
  low: 'bg-ink-800 text-ink-400',
}

export function EvidenceInventory({ evidence, summary }: { evidence: EvidenceItem[]; summary: EvidenceSummary }) {
  return (
    <Panel title="Evidence Inventory" subtitle={`${summary.total} evidence records on file for this case`}>
      <div className="mb-6">
        <EvidenceCoverageBar summary={summary} />
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {EVIDENCE_CATEGORIES.map((category) => {
          const rows = evidence.filter((item) => category.types.includes(item.evidence_type))
          if (rows.length === 0) return null
          return (
            <div key={category.key}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">{category.label}</h3>
              <ul className="flex flex-col divide-y divide-ink-800 overflow-hidden rounded border border-ink-800">
                {rows.map((item) => (
                  <li
                    key={item.evidence_id}
                    className={`px-3 py-2.5 ${item.available ? '' : 'bg-avoid-50/5'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-sm font-medium text-ink-100">
                        <span
                          className={item.available ? 'text-contest-500' : 'text-avoid-500'}
                          aria-hidden="true"
                        >
                          {item.available ? '✓' : '✕'}
                        </span>
                        {formatEvidenceType(item.evidence_type)}
                      </span>
                      <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium uppercase ${RELEVANCE_CLASSES[item.relevance]}`}>
                        {item.relevance}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-2 text-xs text-ink-500">
                      <span>{item.available ? formatEvidenceValue(item.value) : 'Not on file'}</span>
                      <span className="tabular shrink-0" title="Evidence strength (0-1)">
                        {item.available ? `strength ${item.strength.toFixed(2)}` : ''}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
