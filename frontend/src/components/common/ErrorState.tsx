import type { ApiError } from '../../api/client'

const KIND_COPY: Record<string, { title: string; hint: string }> = {
  not_found: { title: 'Case not found', hint: 'This case ID does not exist in the current dataset.' },
  unavailable: {
    title: 'Risk scoring unavailable',
    hint: 'The model has not been trained/loaded in this environment yet.',
  },
  invalid: { title: 'Request rejected', hint: 'The backend rejected this request as invalid.' },
  network: { title: 'Backend unreachable', hint: 'Could not reach the DisputeWise API. Check that it is running.' },
  malformed: { title: 'Unexpected response', hint: 'The backend returned a response the UI could not parse.' },
  server: { title: 'Something went wrong', hint: 'The backend returned an unexpected error.' },
}

export function ErrorState({
  error,
  title,
  onRetry,
  compact = false,
}: {
  error?: ApiError | null
  title?: string
  onRetry?: () => void
  compact?: boolean
}) {
  const copy = (error && KIND_COPY[error.kind]) ?? KIND_COPY.server
  const heading = title ?? copy.title

  return (
    <div
      role="alert"
      className={`flex flex-col items-start gap-2 rounded-lg border border-avoid-500/30 bg-avoid-50/5 ${
        compact ? 'p-3' : 'p-5'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-avoid-500/20 text-avoid-500" aria-hidden="true">
          !
        </span>
        <p className="font-semibold text-ink-50">{heading}</p>
      </div>
      <p className="text-sm text-ink-400">{error?.message || copy.hint}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-sm font-medium text-ink-100 transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        >
          Retry
        </button>
      )}
    </div>
  )
}
