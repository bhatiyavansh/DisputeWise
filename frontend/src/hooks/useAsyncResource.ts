import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

export interface AsyncState<T> {
  status: AsyncStatus
  data: T | null
  error: ApiError | null
}

/**
 * Module-level cache: once a (cacheKey) has successfully resolved, later
 * mounts of the same resource (e.g. navigating inbox -> case -> back ->
 * same case) reuse it instead of re-hitting the API. The dataset backing
 * these endpoints is static for the lifetime of a session, so this is safe
 * and keeps "opening a case" from re-fetching case/evidence/score/decision
 * every time a reviewer revisits it.
 */
const resourceCache = new Map<string, unknown>()

export function clearResourceCache(): void {
  resourceCache.clear()
}

/**
 * Generic fetch-with-loading/error/abort-on-unmount hook. Every resource
 * hook (useCase, useEvidence, useScore, useDecision) is a thin wrapper
 * around this so loading/error handling is implemented exactly once.
 *
 * `cacheKey` of `null` means "don't fetch yet" (e.g. waiting on a
 * prerequisite value) -- the hook stays in `idle`.
 */
export function useAsyncResource<T>(
  cacheKey: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
): AsyncState<T> & { refetch: () => void } {
  const [state, setState] = useState<AsyncState<T>>(() => {
    if (cacheKey && resourceCache.has(cacheKey)) {
      return { status: 'success', data: resourceCache.get(cacheKey) as T, error: null }
    }
    return { status: cacheKey ? 'loading' : 'idle', data: null, error: null }
  })
  const [generation, setGeneration] = useState(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    if (!cacheKey) {
      setState({ status: 'idle', data: null, error: null })
      return
    }

    if (generation === 0 && resourceCache.has(cacheKey)) {
      setState({ status: 'success', data: resourceCache.get(cacheKey) as T, error: null })
      return
    }

    const controller = new AbortController()
    setState({ status: 'loading', data: null, error: null })

    fetcherRef
      .current(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        resourceCache.set(cacheKey, data)
        setState({ status: 'success', data, error: null })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const apiError =
          error instanceof ApiError ? error : new ApiError('network', 'Unexpected error', null, error)
        setState({ status: 'error', data: null, error: apiError })
      })

    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, generation])

  return {
    ...state,
    refetch: () => {
      if (cacheKey) resourceCache.delete(cacheKey)
      setGeneration((g) => g + 1)
    },
  }
}
