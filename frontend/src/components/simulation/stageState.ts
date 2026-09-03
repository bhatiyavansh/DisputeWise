import type { SimulationResponse } from '../../api/types'

/**
 * Stage-state derivation for PipelineStages, kept out of the component file
 * so that module exports components only (fast refresh).
 */
export type StageState = 'idle' | 'running' | 'done' | 'skipped'

export const STAGES = ['SCORING', 'DECISION', 'EVIDENCE', 'KNOWLEDGE', 'RESPONSE', 'VERIFICATION'] as const

export function stageStates(
  status: 'idle' | 'running' | 'done' | 'error',
  result: SimulationResponse | null,
): Record<(typeof STAGES)[number], StageState> {
  if (status === 'running') {
    return { SCORING: 'running', DECISION: 'running', EVIDENCE: 'running', KNOWLEDGE: 'running', RESPONSE: 'running', VERIFICATION: 'running' }
  }
  if (status !== 'done' || !result) {
    return { SCORING: 'idle', DECISION: 'idle', EVIDENCE: 'idle', KNOWLEDGE: 'idle', RESPONSE: 'idle', VERIFICATION: 'idle' }
  }

  const generation = result.generation
  return {
    SCORING: result.score ? 'done' : 'skipped',
    DECISION: result.decision ? 'done' : 'skipped',
    EVIDENCE: result.evidence_gap ? 'done' : 'skipped',
    KNOWLEDGE: result.retrieved_sources.length > 0 ? 'done' : 'skipped',
    // Generation is opt-in, and can legitimately be unavailable.
    RESPONSE: !generation || !generation.generation_available ? 'skipped' : 'done',
    VERIFICATION: generation && generation.claim_verifications.length > 0 ? 'done' : 'skipped',
  }
}

