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
// Filters used by the inbox
// ---------------------------------------------------------------------------

export interface CaseListFilters {
  page?: number
  page_size?: number
  reason_code?: ReasonCode
  status?: DisputeStatus
}
