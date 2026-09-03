import { getCase, getCaseEvidence } from '../api/cases'
import { decideCase } from '../api/decisions'
import { getEvidenceGap, getEvidencePacket } from '../api/evidence'
import { generateDraft } from '../api/response'
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

/** Phase 4 Part A -- evidence gap analysis (reason code + evidence -> required/available/missing). */
export function useEvidenceGap(caseId: string, enabled = true) {
  return useAsyncResource(enabled ? `evidence-gap:${caseId}` : null, (signal) => getEvidenceGap(caseId, signal))
}

/** Phase 4 Part B -- the full evidence packet (facts + evidence + gap + guidance). */
export function useEvidencePacket(caseId: string) {
  return useAsyncResource(`evidence-packet:${caseId}`, (signal) => getEvidencePacket(caseId, signal))
}

/**
 * Phase 4 Parts E-I -- the grounded response draft. Deliberately NOT
 * fetched automatically alongside the other case resources: unlike
 * score/decision/evidence (cheap, deterministic), generating a draft calls
 * an LLM and can take significant time, so it is only requested once
 * `enabled` is true (the Response tab sets this once the analyst opens it;
 * `useAsyncResource` treats a `null` cacheKey as "don't fetch yet").
 */
export function useDraft(caseId: string, enabled: boolean) {
  return useAsyncResource(enabled ? `draft:${caseId}` : null, (signal) => generateDraft(caseId, signal))
}
