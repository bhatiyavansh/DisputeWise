export function SkeletonLine({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-ink-800 ${className}`} aria-hidden="true" />
}

export function SkeletonTableRows({ rows = 8, columns = 7 }: { rows?: number; columns?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <tr key={rowIndex} className="border-b border-ink-800">
          {Array.from({ length: columns }).map((__, colIndex) => (
            <td key={colIndex} className="px-4 py-3">
              <SkeletonLine className="h-4 w-full max-w-[8rem]" />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`rounded-lg border border-ink-800 bg-ink-900 p-5 ${className}`}>
      <SkeletonLine className="mb-3 h-3 w-24" />
      <SkeletonLine className="mb-2 h-8 w-32" />
      <SkeletonLine className="h-3 w-full" />
    </div>
  )
}

export function InlineSpinner({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-400" role="status" aria-live="polite">
      <span
        className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-600 border-t-accent-500"
        aria-hidden="true"
      />
      {label}
    </span>
  )
}
