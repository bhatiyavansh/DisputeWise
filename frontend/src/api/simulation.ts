import { apiRequest } from './client'
import type { SimulationRequest, SimulationResponse } from './types'

/**
 * Phase 6 -- POST /simulate. Scores a hypothetical dispute through the same
 * pipeline as a real case without storing it.
 *
 * Note the endpoint is `/simulate`, not under `/cases` -- production case
 * endpoints are never overloaded for scenario analysis, and the dev proxy
 * forwards this prefix separately (see vite.config.ts). Because `/simulate`
 * is a proxied API prefix, the SPA's own page route is `/simulation` --
 * the same collision the case route already works around (docs/frontend.md).
 */
export function runSimulation(request: SimulationRequest, signal?: AbortSignal): Promise<SimulationResponse> {
  return apiRequest<SimulationResponse>('/simulate', {
    method: 'POST',
    body: request,
    signal,
    // Everything except generation is deterministic and fast (<1s). With
    // `generate_response` the request includes a live LLM call, which needs
    // the same headroom the /draft call gets rather than the 15s default.
    timeoutMs: request.generate_response ? 120_000 : 30_000,
  })
}
