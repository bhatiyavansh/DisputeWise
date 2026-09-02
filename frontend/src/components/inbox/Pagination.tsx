export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  return (
    <div className="flex items-center justify-between border-t border-ink-800 px-4 py-3 text-sm text-ink-400">
      <span>
        Showing <span className="tabular text-ink-200">{start.toLocaleString('en-IN')}</span>–
        <span className="tabular text-ink-200">{end.toLocaleString('en-IN')}</span> of{' '}
        <span className="tabular text-ink-200">{total.toLocaleString('en-IN')}</span>
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded border border-ink-700 px-2.5 py-1 text-ink-200 transition-colors hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        >
          Previous
        </button>
        <span className="tabular px-1 text-ink-500">
          Page {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="rounded border border-ink-700 px-2.5 py-1 text-ink-200 transition-colors hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        >
          Next
        </button>
      </div>
    </div>
  )
}
