import { getCase, getCaseEvidence } from '../api/cases'
import { decideCase } from '../api/decisions'
import { scoreCase } from '../api/scoring'
import { useAsyncResource } from './useAsyncResource'
import { toNumber } from '../utils/format'

/** Case detail. */
export function useCase(caseId: string) {
  return useAsyncResource(`case:${caseId}`, (signal) => getCase(caseId, signal))
}

/** Evidence list. */
export function useEvidence(caseId: string) {
  return useAsyncResource(`evidence:${caseId}`, (signal) => getCaseEvidence(caseId, signal))
}

/** Phase 2 /score -- always the real endpoint. */
export function useScore(caseId: string) {
  return useAsyncResource(`score:${caseId}`, (signal) => scoreCase(caseId, signal))
}

/**
 * Phase 3 /decision. Fetched immediately and in parallel with everything
 * else -- the real endpoint needs nothing but caseId. `score`/`disputeAmount`
 * are only consulted if the request fails and the dev mock fallback is both
 * enabled and eligible (see decisions.ts); if score hasn't resolved yet at
 * that moment, the mock simply can't activate and the real error propagates,
 * which is fine since this fallback path is dev-only and rare.
 */
export function useDecision(
  caseId: string,
  disputeAmount: string | number | null | undefined,
  score: { data: import('../api/types').ScoreResponse | null },
) {
  return useAsyncResource(`decision:${caseId}`, (signal) =>
    decideCase(caseId, { score: score.data ?? undefined, disputeAmount: toNumber(disputeAmount) ?? undefined }, signal),
  )
}
