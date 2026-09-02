import { afterEach, describe, expect, it, vi } from 'vitest'
import { decideCase } from './decisions'
import { ApiError } from './client'
import { SCORE_RESPONSE, makeDecision } from '../tests/fixtures'
import { installFetchMock, jsonRoute } from '../tests/mockFetch'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('decideCase adapter', () => {
  it('returns the real decision when the backend succeeds', async () => {
    installFetchMock([jsonRoute('POST', /\/cases\/DSP-031597\/decision$/, 200, makeDecision())])

    const result = await decideCase('DSP-031597', { score: SCORE_RESPONSE })

    expect(result.source).toBe('real')
    expect(result.data.decision).toBe('CONTEST')
  })

  it('propagates a 404 without falling back to any mock (case genuinely does not exist)', async () => {
    installFetchMock([jsonRoute('POST', /\/cases\/.*\/decision$/, 404, { detail: 'not found' })])
    // import.meta.env.DEV is true under vitest by default; explicitly enable the mock flag too
    vi.stubEnv('VITE_ENABLE_DECISION_MOCK', 'true')

    await expect(decideCase('DSP-999999', { score: SCORE_RESPONSE })).rejects.toMatchObject({ kind: 'not_found' })
  })

  it('never falls back to the mock when VITE_ENABLE_DECISION_MOCK is not set, even if the backend is unreachable', async () => {
    installFetchMock([jsonRoute('POST', /\/cases\/.*\/decision$/, 503, { detail: 'model not ready' })])
    // mock flag deliberately left unset (the default / production posture)

    await expect(decideCase('DSP-031597', { score: SCORE_RESPONSE })).rejects.toBeInstanceOf(ApiError)
  })

  it('only falls back to the mock when explicitly enabled AND the endpoint is unavailable', async () => {
    installFetchMock([jsonRoute('POST', /\/cases\/.*\/decision$/, 503, { detail: 'model not ready' })])
    vi.stubEnv('VITE_ENABLE_DECISION_MOCK', 'true')

    const result = await decideCase('DSP-031597', { score: SCORE_RESPONSE })

    expect(result.source).toBe('mock')
    expect(result.data.decision_policy_version).toContain('[DEV MOCK]')
    expect(result.data.reason).toContain('[DEV MOCK]')
  })
})
