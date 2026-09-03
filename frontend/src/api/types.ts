/**
 * Types mirror the ACTUAL backend response shapes, verified live against the
 * running Phase 1/2/3 API (see docs/frontend.md for how to re-verify).
 *
 * Notable real-world quirks preserved deliberately (not "fixed" client-side,
 * since the backend is the source of truth and must not be modified):
 *
 *   - Case.dispute_amount is a STRING ("27531.38") -- FastAPI/Pydantic
 *     serializes Decimal fields as strings in /cases and /cases/{id}.
 *   - DecisionResponse.dispute_amount is a NUMBER -- Phase 3's schema types
 *     it as `float`, so it serializes as a JSON number instead.
 *
 * Use `toNumber()` from src/utils/format.ts when displaying an amount field
 * rather than assuming either representation.
 */

export type ReasonCode = 'unauthorized_transaction' | 'goods_not_received' | 'duplicate_charge'

export type DisputeStatus = 'open' | 'evidence_submitted' | 'under_review' | 'closed'

export type ScenarioArchetype = 'strong_legitimate' | 'weak' | 'ambiguous' | 'high_value_strong'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// ---------------------------------------------------------------------------
// GET /cases, GET /cases/{id}
// ---------------------------------------------------------------------------

export interface CaseListItem {
  dispute_id: string
  reason_code: ReasonCode
  status: DisputeStatus
  dispute_amount: string
  created_at: string
  response_deadline: string
  scenario_archetype: ScenarioArchetype
  split: 'train' | 'validation' | 'test'
}

export interface Transaction {
  transaction_id: string
  merchant_id: string
  amount: string
  currency: string
  payment_method: 'card' | 'upi' | 'netbanking'
  created_at: string
  captured_at: string | null
  status: 'captured' | 'refunded' | 'failed'
  device_id: string
  ip_address: string
  billing_address_id: string
  shipping_address_id: string
  avs_result: 'Y' | 'N' | 'U' | 'M'
  cvv_result: 'M' | 'N' | 'U'
  three_ds_authenticated: boolean
}

export interface Customer {
  customer_id: string
  account_created_at: string
  country: string
  account_age_days: number
  previous_order_count: number
  previous_successful_order_count: number
  previous_dispute_count: number
  previous_refund_count: number
}

export interface CaseDetail extends CaseListItem {
  transaction: Transaction
  customer: Customer
}

// ---------------------------------------------------------------------------
// GET /cases/{id}/evidence
// ---------------------------------------------------------------------------

export type EvidenceType =
  | 'three_ds'
  | 'avs'
  | 'cvv'
  | 'device_match'
  | 'ip_match'
  | 'delivery_confirmed'
  | 'tracking_available'
  | 'delivery_address_match'
  | 'delivery_timestamp'
  | 'proof_of_delivery'
  | 'prior_order_history'
  | 'prior_successful_orders'
  | 'prior_disputes'
  | 'customer_communication_available'
  | 'cancellation_request'
  | 'refund_request'

export type EvidenceRelevance = 'high' | 'medium' | 'low'

export interface EvidenceItem {
  evidence_id: string
  evidence_type: EvidenceType
  available: boolean
  value: Record<string, unknown> | null
  relevance: EvidenceRelevance
  strength: number
  created_at: string
}

// ---------------------------------------------------------------------------
// POST /cases/{id}/score  (Phase 2)
// ---------------------------------------------------------------------------

export interface ContributingFactor {
  feature: string
  contribution: number
  value: number | boolean | null
  description: string
}

export interface EvidenceSummary {
  total: number
  available: number
  strong: number
  high_relevance_total: number
  high_relevance_available: number
  missing_key_types: EvidenceType[]
}

export type RiskBand = 'HIGH_WINNABILITY' | 'MEDIUM_WINNABILITY' | 'LOW_WINNABILITY'

export interface ScoreResponse {
  case_id: string
  model_version: string
  feature_schema_version: string
  reason_code: ReasonCode
  raw_probability: number
  calibrated_probability: number
  risk_band: RiskBand
  calibration_method: string
  top_positive_factors: ContributingFactor[]
  top_negative_factors: ContributingFactor[]
  evidence_summary: EvidenceSummary
  disclaimer: string
}

// ---------------------------------------------------------------------------
// POST /cases/{id}/decision  (Phase 3)
// ---------------------------------------------------------------------------

export type Decision = 'CONTEST' | 'HUMAN_REVIEW' | 'DO_NOT_CONTEST'

export interface SensitivityPoint {
  probability: number
  delta: number
  expected_recovery: number
  expected_net_value: number
}

export interface DecisionResponse {
  case_id: string
  model_version: string
  feature_schema_version: string
  decision_policy_version: string
  reason_code: ReasonCode

  decision: Decision
  reason: string
  evidence_gap_downgrade: boolean

  calibrated_probability: number
  risk_band: RiskBand

  dispute_amount: number
  recovery_rate: number
  recoverable_amount: number
  contest_cost: number
  expected_recovery: number
  expected_net_value: number
  break_even_probability: number | null
  break_even_explanation: string
  sensitivity: SensitivityPoint[]

  top_positive_factors: ContributingFactor[]
  top_negative_factors: ContributingFactor[]
  evidence_summary: EvidenceSummary

  disclaimer: string
}

// ---------------------------------------------------------------------------
// POST /cases/{id}/evidence-gap  (Phase 4, Part A)
// ---------------------------------------------------------------------------

export type EvidenceGapStatus = 'AVAILABLE' | 'MISSING'
export type EvidenceGapRelevance = 'HIGH' | 'MEDIUM' | 'LOW'
export type EvidenceGapPriority = 'CRITICAL' | 'IMPORTANT' | 'OPTIONAL' | 'NONE'

export interface EvidenceGapItem {
  evidence_type: EvidenceType
  required: boolean
  status: EvidenceGapStatus
  relevance: EvidenceGapRelevance
  priority: EvidenceGapPriority
  reason: string
  source_id: string
  strength: number
  evidence_id: string | null
}

export interface EvidenceGapResponse {
  case_id: string
  reason_code: ReasonCode
  schema_version: string
  coverage: { required: number; available: number; missing: number }
  coverage_ratio: number
  items: EvidenceGapItem[]
}

// ---------------------------------------------------------------------------
// POST /cases/{id}/evidence-packet  (Phase 4, Part B)
// ---------------------------------------------------------------------------

export interface EvidencePacketItem {
  evidence_id: string
  evidence_type: EvidenceType
  available: boolean
  value: Record<string, unknown> | null
  relevance: EvidenceRelevance
  strength: number
  claim_type: string
}

export interface ReasonCodeGuidance {
  reason_code_id: string
  reason_code_name: string
  description: string
  source_id: string
  claim_type: string
}

export interface EvidencePacketTransactionFacts {
  payment_method: string
  transaction_status: string
  three_ds_authenticated: boolean
  avs_result: string
  cvv_result: string
}

export interface EvidencePacketCustomerFacts {
  account_age_days: number
  previous_order_count: number
  previous_successful_order_count: number
  previous_dispute_count: number
  previous_refund_count: number
}

export interface EvidencePacketResponse {
  case_id: string
  schema_version: string
  generated_at: string
  reason_code: ReasonCode
  dispute_amount: number
  dispute_status: string
  transaction: EvidencePacketTransactionFacts
  customer: EvidencePacketCustomerFacts
  evidence: EvidencePacketItem[]
  gap: EvidenceGapResponse
  guidance: ReasonCodeGuidance
}

// ---------------------------------------------------------------------------
// POST /cases/{id}/draft, POST /cases/{id}/verify  (Phase 4, Parts D-I)
// ---------------------------------------------------------------------------

export interface RetrievalResult {
  chunk_id: string
  text: string
  source_id: string
  source_name: string
  source_url: string
  relevance_score: number
  metadata: {
    doc_type: string
    reason_code_id: string
    evidence_type: EvidenceType | null
    relevance: string | null
    addresses_gap: boolean
  }
}

export type ClaimType = 'fact' | 'reference' | 'inference' | 'summary'

export interface GeneratedClaim {
  claim_id: string
  text: string
  claim_type: ClaimType
  evidence_ids: string[]
  source_ids: string[]
}

export type ClaimVerificationStatus = 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'UNSUPPORTED' | 'INVALID_REFERENCE' | 'INCOMPLETE'

export interface ClaimVerification {
  claim_id: string
  status: ClaimVerificationStatus
  evidence_ids: string[]
  source_ids: string[]
  explanation: string
  verifier_version: string
}

export type ResponseState = 'DRAFT_READY' | 'DRAFT_FLAGGED' | 'DRAFT_BLOCKED' | 'GENERATION_UNAVAILABLE'

/**
 * Why generation produced no draft, when it produced none. Additive to
 * `response_state` (which keeps its Phase 4 meaning): it lets the UI tell an
 * LLM outage apart from a verifier rejection, since the backend reports both
 * as DRAFT_BLOCKED. Null when a draft exists or generation was not attempted.
 */
export type GenerationErrorKind = 'provider_unavailable' | 'invalid_output' | null

export interface DecisionSummary {
  decision: Decision
  calibrated_probability: number
  expected_net_value: number
  risk_band: RiskBand
}

export interface ResponseTrace {
  case_id: string
  decision: string | null
  model_version: string
  feature_schema_version: string
  decision_policy_version: string | null
  evidence_schema_version: string
  knowledge_base_version: string
  retrieval_config_version: string
  prompt_version: string
  response_schema_version: string
  verifier_version: string
  retrieved_source_ids: string[]
  retrieved_chunk_ids: string[]
  cited_evidence_ids: string[]
  claim_count: number
  claim_statuses: Record<string, number>
  response_state: ResponseState
  generated_at: string
}

export interface DraftResponse {
  case_id: string
  reason_code: ReasonCode

  model_version: string
  feature_schema_version: string
  decision_policy_version: string | null
  evidence_schema_version: string
  knowledge_base_version: string
  prompt_version: string
  response_schema_version: string
  verifier_version: string

  decision: DecisionSummary | null
  evidence_gap: EvidenceGapResponse
  retrieved_sources: RetrievalResult[]

  generation_available: boolean
  summary: string | null
  claims: GeneratedClaim[]
  missing_evidence: EvidenceType[]
  response_body: string | null

  claim_verifications: ClaimVerification[]
  response_state: ResponseState
  response_state_reason: string
  generation_error_kind: GenerationErrorKind

  trace: ResponseTrace
  disclaimer: string
}

export interface VerifyResponse {
  case_id: string
  verifier_version: string
  claim_verifications: ClaimVerification[]
  response_state: ResponseState
  response_state_reason: string
  disclaimer: string
}

// ---------------------------------------------------------------------------
// Filters used by the inbox
// ---------------------------------------------------------------------------

export interface CaseListFilters {
  page?: number
  page_size?: number
  reason_code?: ReasonCode
  status?: DisputeStatus
}

// ---------------------------------------------------------------------------
// POST /simulate  (Phase 6 -- hypothetical dispute, never persisted)
// ---------------------------------------------------------------------------

/** Mirrors app/schemas/simulation.py's SimulationRequest. The backend model
 * is `extra="forbid"` and rejects every outcome/target field by name, so
 * there is deliberately no field here describing a dispute's result. */
export interface SimulationRequest {
  simulation_case_id?: string

  reason_code: ReasonCode
  dispute_amount: number
  dispute_status?: DisputeStatus

  transaction_amount: number
  payment_method?: 'card' | 'upi' | 'netbanking'
  transaction_status?: 'captured' | 'refunded' | 'failed'
  capture_lag_minutes?: number
  days_transaction_to_dispute?: number
  days_to_respond?: number

  three_ds_authenticated?: boolean
  avs_result?: 'Y' | 'N' | 'U' | 'M'
  cvv_result?: 'M' | 'N' | 'U'
  device_match?: boolean
  ip_match?: boolean
  billing_shipping_match?: boolean

  account_age_days?: number
  previous_order_count?: number
  previous_successful_order_count?: number
  previous_dispute_count?: number
  previous_refund_count?: number

  delivery_confirmed?: boolean
  tracking_available?: boolean
  delivery_address_match?: boolean
  proof_of_delivery?: boolean
  delivery_days_after_capture?: number

  customer_communication_available?: boolean
  cancellation_request?: boolean
  refund_request?: boolean

  evidence_on_file?: EvidenceType[]
  evidence_not_on_file?: EvidenceType[]

  generate_response?: boolean
}

export interface SimulationScore {
  raw_probability: number
  calibrated_probability: number
  risk_band: RiskBand
  calibration_method: string
  top_positive_factors: ContributingFactor[]
  top_negative_factors: ContributingFactor[]
  evidence_summary: EvidenceSummary
}

export interface SimulationDecision {
  decision: Decision
  reason: string
  decision_policy_version: string
  evidence_gap_downgrade: boolean
  dispute_amount: number
  recovery_rate: number
  recoverable_amount: number
  contest_cost: number
  expected_recovery: number
  expected_net_value: number
  break_even_probability: number | null
  break_even_explanation: string
  sensitivity: SensitivityPoint[]
}

export interface SimulationGeneration {
  response_state: ResponseState
  response_state_reason: string
  generation_available: boolean
  summary: string | null
  response_body: string | null
  claims: GeneratedClaim[]
  claim_verifications: ClaimVerification[]
  missing_evidence: EvidenceType[]
}

export interface SimulationTrace {
  simulation_id: string
  model_version: string
  feature_schema_version: string
  decision_policy_version: string
  evidence_schema_version: string
  knowledge_base_version: string
  retrieval_config_version: string
  /** null when the stage did not run -- generation is opt-in. */
  prompt_version: string | null
  response_schema_version: string | null
  verifier_version: string | null
  retrieved_source_ids: string[]
  retrieved_chunk_ids: string[]
  generated_at: string
  /** Always false. Simulations are scenario analysis, never stored. */
  persisted: boolean
}

export interface SimulationResponse {
  simulation_id: string
  is_simulation: boolean
  reason_code: ReasonCode
  score: SimulationScore
  decision: SimulationDecision
  evidence_gap: EvidenceGapResponse
  retrieved_sources: RetrievalResult[]
  generation: SimulationGeneration | null
  trace: SimulationTrace
  disclaimer: string
}

// ---------------------------------------------------------------------------
// POST /cases/{id}/evidence-scenario  (Phase 7A -- scenario analysis)
// ---------------------------------------------------------------------------

export interface EvidenceScenarioRequest {
  add_evidence?: EvidenceType[]
  remove_evidence?: EvidenceType[]
}

export interface ScenarioScore {
  raw_probability: number
  calibrated_probability: number
  risk_band: RiskBand
  top_positive_factors: ContributingFactor[]
  top_negative_factors: ContributingFactor[]
  evidence_summary: EvidenceSummary
}

export interface ScenarioDecision {
  decision: Decision
  reason: string
  evidence_gap_downgrade: boolean
  expected_recovery: number
  expected_net_value: number
  contest_cost: number
  break_even_probability: number | null
  sensitivity: SensitivityPoint[]
}

export interface ScenarioSide {
  score: ScenarioScore
  decision: ScenarioDecision
  evidence_gap: EvidenceGapResponse
}

export interface ScenarioDelta {
  calibrated_probability: number
  expected_net_value: number
  decision_changed: boolean
  decision_from: Decision
  decision_to: Decision
  critical_gaps_resolved: EvidenceType[]
  critical_gaps_introduced: EvidenceType[]
}

export interface EvidenceScenarioResponse {
  case_id: string
  reason_code: ReasonCode
  is_scenario: boolean
  evidence_added: EvidenceType[]
  evidence_removed: EvidenceType[]
  current: ScenarioSide
  scenario: ScenarioSide
  delta: ScenarioDelta
  model_version: string
  feature_schema_version: string
  decision_policy_version: string
  evidence_schema_version: string
  generated_at: string
  /** Always false. Scenario analysis never modifies or stores the case. */
  persisted: boolean
  disclaimer: string
}

// ---------------------------------------------------------------------------
// Policy playground (7B) + portfolio (7C)
// ---------------------------------------------------------------------------

export interface PolicyConfig {
  contest_cost: number
  recovery_rate: number
  high_confidence_probability: number
  low_confidence_probability: number
  min_expected_net_value: number
  review_margin: number
}

export interface PolicyDefaults {
  decision_policy_version: string
  tunable_fields: (keyof PolicyConfig)[]
  defaults: PolicyConfig
  economics_explanation: string
  note: string
}

export interface PolicyBucket {
  count: number
  percentage: number
  actual_favorable_outcome_rate: number | null
  expected_recovery_total: number
  expected_net_value_total: number
  realized_recovery_total: number
  estimated_contest_cost_total: number
  realized_net_value_total: number
  evidence_gap_downgrades: number
}

export interface PolicySummary {
  policy: string
  n_total: number
  buckets: Record<Decision, PolicyBucket>
  portfolio: {
    total_expected_net_value: number
    contest_only_expected_net_value: number
    contest_only_realized_net_value: number
    contest_volume: number
    review_volume: number
    do_not_contest_volume: number
  }
}

export interface PolicySimulationResponse {
  split: string
  n_cases: number
  is_simulation: boolean
  decision_policy_version: string
  model_version: string
  feature_schema_version: string
  default_config: PolicyConfig
  scenario_config: PolicyConfig
  changed_fields: (keyof PolicyConfig)[]
  default_policy: PolicySummary
  scenario_policy: PolicySummary
  contest_everything_baseline: PolicySummary
  economics_explanation: string
  note: string
}

export interface PortfolioBucket {
  decision: Decision
  count: number
  percentage: number
  total_amount: number
  expected_recovery: number
  expected_net_value: number
  actual_favorable_outcome_rate: number | null
  evidence_gap_downgrades: number
}

export interface PortfolioGroup {
  key: string
  count: number
  total_amount: number
  mean_probability: number
}

export interface PortfolioSummaryResponse {
  split: string
  n_cases: number
  total_disputed_amount: number
  total_expected_recovery: number
  total_expected_net_value: number
  contest_only_expected_net_value: number
  contest_only_realized_net_value: number
  mean_calibrated_probability: number
  cases_with_missing_high_relevance_evidence: number
  decisions: PortfolioBucket[]
  by_reason_code: PortfolioGroup[]
  by_probability_band: PortfolioGroup[]
  by_evidence_completeness: PortfolioGroup[]
  model_version: string
  feature_schema_version: string
  decision_policy_version: string
  note: string
}
