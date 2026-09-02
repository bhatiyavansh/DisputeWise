import { useMemo, useState } from 'react'
import type { CaseListItem, Decision, DisputeStatus, ReasonCode } from '../api/types'
import { DisputeTable } from '../components/inbox/DisputeTable'
import { FilterBar } from '../components/inbox/FilterBar'
import { Pagination } from '../components/inbox/Pagination'
import { SummaryStats } from '../components/inbox/SummaryStats'
import { ErrorState } from '../components/common/ErrorState'
import { useCases } from '../hooks/useCases'
import { usePageEconomics } from '../hooks/usePageEconomics'

const PAGE_SIZE = 20
const EMPTY_ITEMS: CaseListItem[] = []

const DECISION_FILTERS: { value: Decision | ''; label: string }[] = [
  { value: '', label: 'Any decision' },
  { value: 'CONTEST', label: 'Contest' },
  { value: 'HUMAN_REVIEW', label: 'Human Review' },
  { value: 'DO_NOT_CONTEST', label: "Don't Contest" },
]

export function DisputeInboxPage() {
  const [page, setPage] = useState(1)
  const [reasonCode, setReasonCode] = useState<ReasonCode | ''>('')
  const [status, setStatus] = useState<DisputeStatus | ''>('')
  const [decisionFilter, setDecisionFilter] = useState<Decision | ''>('')

  const { status: listStatus, page: casePage, error, refetch } = useCases({
    page,
    page_size: PAGE_SIZE,
    reason_code: reasonCode || undefined,
    status: status || undefined,
  })

  const items = casePage?.items ?? EMPTY_ITEMS
  const economics = usePageEconomics(items)

  const visibleItems = useMemo(() => {
    if (!decisionFilter) return items
    return items.filter((item) => economics.get(item.dispute_id)?.decision?.decision === decisionFilter)
  }, [items, economics, decisionFilter])

  function updateFilter<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink-50">Dispute Inbox</h1>
        <p className="mt-0.5 text-sm text-ink-500">
          Live chargeback disputes, scored by the Phase 2 winnability model and evaluated by the Phase 3 decision
          engine.
        </p>
      </div>

      {listStatus === 'error' ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <>
          <SummaryStats total={casePage?.total ?? 0} items={items} economics={economics} />

          <div className="flex flex-wrap items-end justify-between gap-3">
            <FilterBar
              reasonCode={reasonCode}
              status={status}
              onReasonCodeChange={updateFilter(setReasonCode)}
              onStatusChange={updateFilter(setStatus)}
            />
            <div>
              <label htmlFor="decision-filter" className="mb-1 block text-xs font-medium text-ink-500">
                Decision (this page)
              </label>
              <select
                id="decision-filter"
                value={decisionFilter}
                onChange={(e) => setDecisionFilter(e.target.value as Decision | '')}
                className="rounded border border-ink-700 bg-ink-900 px-3 py-1.5 text-sm text-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
                title="Filters only the cases already loaded on this page -- there is no backend endpoint to filter by decision across the full dataset."
              >
                {DECISION_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <DisputeTable items={visibleItems} economics={economics} loading={listStatus === 'loading'} />

          {casePage && casePage.total > 0 && (
            <Pagination page={page} pageSize={PAGE_SIZE} total={casePage.total} onPageChange={setPage} />
          )}
        </>
      )}
    </div>
  )
}
