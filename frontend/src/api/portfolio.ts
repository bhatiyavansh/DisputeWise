import { apiRequest } from './client'
import type {
  PolicyConfig,
  PolicyDefaults,
  PolicySimulationResponse,
  PortfolioSummaryResponse,
} from './types'

/** Phase 7C -- server-side portfolio aggregation under the production policy. */
export function getPortfolioSummary(signal?: AbortSignal): Promise<PortfolioSummaryResponse> {
  return apiRequest<PortfolioSummaryResponse>('/portfolio/summary', { signal, timeoutMs: 30_000 })
}

/** Phase 7B -- the production decision-v1 parameters (the reset point). */
export function getPolicyDefaults(signal?: AbortSignal): Promise<PolicyDefaults> {
  return apiRequest<PolicyDefaults>('/policy/default', { signal })
}

/**
 * Phase 7B -- re-route the portfolio under a hypothetical policy.
 *
 * All routing and economics are computed by the backend's existing decision
 * engine; the frontend never applies a threshold or computes an expected
 * value of its own.
 */
export function simulatePolicy(
  overrides: Partial<PolicyConfig>,
  signal?: AbortSignal,
): Promise<PolicySimulationResponse> {
  return apiRequest<PolicySimulationResponse>('/policy/simulate', {
    method: 'POST',
    body: overrides,
    signal,
    timeoutMs: 30_000,
  })
}
