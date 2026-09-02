import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { DisputeStatus, ReasonCode } from '../../api/types'

const REASON_CODES: { value: ReasonCode | ''; label: string }[] = [
  { value: '', label: 'All reasons' },
  { value: 'unauthorized_transaction', label: 'Unauthorized Transaction' },
  { value: 'goods_not_received', label: 'Goods Not Received' },
  { value: 'duplicate_charge', label: 'Duplicate Charge' },
]

const STATUSES: { value: DisputeStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'open', label: 'Open' },
  { value: 'evidence_submitted', label: 'Evidence Submitted' },
  { value: 'under_review', label: 'Under Review' },
  { value: 'closed', label: 'Closed' },
]

export function FilterBar({
  reasonCode,
  status,
  onReasonCodeChange,
  onStatusChange,
}: {
  reasonCode: ReasonCode | ''
  status: DisputeStatus | ''
  onReasonCodeChange: (value: ReasonCode | '') => void
  onStatusChange: (value: DisputeStatus | '') => void
}) {
  const [searchValue, setSearchValue] = useState('')
  const navigate = useNavigate()

  function handleSearch(event: FormEvent) {
    event.preventDefault()
    const trimmed = searchValue.trim().toUpperCase()
    if (trimmed) navigate(`/case/${trimmed}`)
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label htmlFor="reason-filter" className="mb-1 block text-xs font-medium text-ink-500">
          Reason code
        </label>
        <select
          id="reason-filter"
          value={reasonCode}
          onChange={(e) => onReasonCodeChange(e.target.value as ReasonCode | '')}
          className="rounded border border-ink-700 bg-ink-900 px-3 py-1.5 text-sm text-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        >
          {REASON_CODES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="status-filter" className="mb-1 block text-xs font-medium text-ink-500">
          Status
        </label>
        <select
          id="status-filter"
          value={status}
          onChange={(e) => onStatusChange(e.target.value as DisputeStatus | '')}
          className="rounded border border-ink-700 bg-ink-900 px-3 py-1.5 text-sm text-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        >
          {STATUSES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <form onSubmit={handleSearch} className="ml-auto flex items-end gap-2">
        <div>
          <label htmlFor="case-search" className="mb-1 block text-xs font-medium text-ink-500">
            Open case by ID
          </label>
          <input
            id="case-search"
            type="text"
            placeholder="DSP-031597"
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            className="w-44 rounded border border-ink-700 bg-ink-900 px-3 py-1.5 font-mono text-sm text-ink-100 placeholder:text-ink-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
          />
        </div>
        <button
          type="submit"
          className="rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-sm font-medium text-ink-100 transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        >
          Open
        </button>
      </form>
    </div>
  )
}
