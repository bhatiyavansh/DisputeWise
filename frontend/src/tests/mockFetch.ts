import { vi } from 'vitest'

type RouteHandler = (url: URL) => { status: number; body: unknown } | Promise<{ status: number; body: unknown }>

/** Minimal route-matching fetch mock: register handlers by method+path pattern. */
export function installFetchMock(routes: { method: string; pattern: RegExp; handler: RouteHandler }[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input.toString())
    const method = (init?.method ?? 'GET').toUpperCase()
    const route = routes.find((r) => r.method === method && r.pattern.test(url.pathname))
    if (!route) {
      throw new Error(`No mock route for ${method} ${url.pathname}`)
    }
    const { status, body } = await route.handler(url)
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function jsonRoute(method: string, pattern: RegExp, status: number, body: unknown) {
  return { method, pattern, handler: () => ({ status, body }) }
}
