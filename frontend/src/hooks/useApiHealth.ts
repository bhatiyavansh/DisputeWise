import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

export type ApiHealth = 'checking' | 'up' | 'down'

/** Real GET /health poll, once on mount and every 30s -- not decorative. */
export function useApiHealth(): ApiHealth {
  const [health, setHealth] = useState<ApiHealth>('checking')

  useEffect(() => {
    let cancelled = false
    const check = () => {
      apiRequest<{ status: string }>('/health')
        .then(() => {
          if (!cancelled) setHealth('up')
        })
        .catch(() => {
          if (!cancelled) setHealth('down')
        })
    }
    check()
    const interval = setInterval(check, 30_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return health
}
