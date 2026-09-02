/**
 * Single low-level HTTP client. Every API module (cases.ts, scoring.ts,
 * decisions.ts) goes through this -- no component ever calls fetch() directly.
 */

/**
 * Empty by default -- requests are made to the SAME ORIGIN the app is served
 * from (e.g. http://localhost:5173), which the Vite dev/preview server then
 * proxies through to the real backend (see vite.config.ts). This sidesteps
 * needing the backend to send CORS headers, which we are not allowed to add.
 *
 * Set VITE_API_BASE_URL to talk to a backend directly instead (e.g. a
 * deployment where the backend already sends CORS headers, or where there is
 * no dev proxy in front of it).
 */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

export type ApiErrorKind =
  | 'not_found' // 404 -- case does not exist
  | 'unavailable' // 503 -- model/artifacts not ready
  | 'invalid' // 422 -- malformed input rejected by the backend
  | 'network' // fetch itself failed (backend unreachable, timeout, CORS, DNS)
  | 'malformed' // response was not valid JSON / didn't match the expected shape
  | 'server' // any other non-2xx status

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly detail: unknown

  constructor(kind: ApiErrorKind, message: string, status: number | null = null, detail: unknown = undefined) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.detail = detail
  }
}

function classifyStatus(status: number): ApiErrorKind {
  if (status === 404) return 'not_found'
  if (status === 503) return 'unavailable'
  if (status === 422) return 'invalid'
  return 'server'
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  query?: Record<string, string | number | undefined>
  signal?: AbortSignal
  timeoutMs?: number
}

const DEFAULT_TIMEOUT_MS = 15_000

function buildUrl(path: string, query?: RequestOptions['query']): string {
  // An empty API_BASE_URL means "same origin as the page" -- new URL() needs
  // an absolute base, so fall back to window.location.origin (jsdom in tests
  // provides one too: http://localhost:3000 by default).
  const base = API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
  const url = new URL(path, base)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options
  const url = buildUrl(path, query)

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  const combinedSignal = signal ? anySignal([signal, controller.signal]) : controller.signal

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers: { Accept: 'application/json' },
      signal: combinedSignal,
    })
  } catch (error) {
    clearTimeout(timeout)
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('network', 'The request timed out or was cancelled.', null, error)
    }
    throw new ApiError('network', 'Could not reach the DisputeWise API. Is the backend running?', null, error)
  }
  clearTimeout(timeout)

  if (!response.ok) {
    let detail: unknown
    try {
      detail = await response.json()
    } catch {
      detail = await response.text().catch(() => undefined)
    }
    const kind = classifyStatus(response.status)
    const message = extractMessage(detail) ?? `Request failed with status ${response.status}`
    throw new ApiError(kind, message, response.status, detail)
  }

  try {
    return (await response.json()) as T
  } catch (error) {
    throw new ApiError('malformed', 'The server returned a response that was not valid JSON.', response.status, error)
  }
}

function extractMessage(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>
    if (typeof record.detail === 'string') return record.detail
    if (record.detail && typeof record.detail === 'object') {
      const inner = record.detail as Record<string, unknown>
      if (typeof inner.detail === 'string') return inner.detail
    }
  }
  return undefined
}

function anySignal(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController()
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort()
      break
    }
    signal.addEventListener('abort', () => controller.abort(), { once: true })
  }
  return controller.signal
}
