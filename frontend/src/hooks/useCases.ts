import { useEffect, useRef, useState } from 'react'
import { listCases } from '../api/cases'
import { ApiError } from '../api/client'
import type { CaseListFilters, CaseListItem, Page } from '../api/types'

export interface UseCasesState {
  status: 'loading' | 'success' | 'error'
  page: Page<CaseListItem> | null
  error: ApiError | null
  refetch: () => void
}

/** Not cached like useAsyncResource -- pagination/filters change constantly,
 * so every distinct query is expected to hit the API fresh. */
export function useCases(filters: CaseListFilters): UseCasesState {
  const [status, setStatus] = useState<UseCasesState['status']>('loading')
  const [page, setPage] = useState<Page<CaseListItem> | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [generation, setGeneration] = useState(0)
  const key = JSON.stringify(filters)
  const filtersRef = useRef(filters)
  filtersRef.current = filters

  useEffect(() => {
    const controller = new AbortController()
    setStatus('loading')
    setError(null)
    listCases(filtersRef.current, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setPage(result)
        setStatus('success')
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(err instanceof ApiError ? err : new ApiError('network', 'Unexpected error', null, err))
        setStatus('error')
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, generation])

  return { status, page, error, refetch: () => setGeneration((g) => g + 1) }
}
