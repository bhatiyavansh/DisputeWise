import type { CaseListItem } from '../../api/types'
import type { RowEconomics } from '../../hooks/usePageEconomics'
import { EmptyState } from '../common/EmptyState'
import { SkeletonTableRows } from '../common/LoadingStates'
import { DisputeRow } from './DisputeRow'

const COLUMNS = ['Case ID', 'Reason', 'Status', 'Amount', 'P(win)', 'Expected EV', 'Decision', 'Evidence']

export function DisputeTable({
  items,
  economics,
  loading,
}: {
  items: CaseListItem[]
  economics: Map<string, RowEconomics>
  loading: boolean
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-ink-800 bg-ink-900">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">Dispute inbox: case list with winnability and decision economics</caption>
        <thead>
          <tr className="border-b border-ink-800 bg-ink-850 text-xs font-medium uppercase tracking-wide text-ink-500">
            {COLUMNS.map((col, i) => (
              <th key={col} scope="col" className={`px-4 py-2.5 ${i >= 3 && i <= 5 ? 'text-right' : ''}`}>
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <SkeletonTableRows rows={10} columns={COLUMNS.length} />
          ) : (
            items.map((item) => <DisputeRow key={item.dispute_id} item={item} economics={economics.get(item.dispute_id)} />)
          )}
        </tbody>
      </table>
      {!loading && items.length === 0 && (
        <EmptyState title="No disputes match these filters" hint="Try clearing the reason code or status filter." />
      )}
    </div>
  )
}
