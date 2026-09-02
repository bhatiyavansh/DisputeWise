import type { CaseDetail, CaseListItem, DecisionResponse, EvidenceItem, Page, ScoreResponse } from '../api/types'

export const CASE_LIST_ITEM: CaseListItem = {
  dispute_id: 'DSP-031597',
  reason_code: 'goods_not_received',
  status: 'closed',
  dispute_amount: '27531.38',
  created_at: '2026-10-14T11:07:00Z',
  response_deadline: '2026-10-28T11:07:00Z',
  scenario_archetype: 'high_value_strong',
  split: 'train',
}

export const CASE_PAGE: Page<CaseListItem> = {
  items: [
    CASE_LIST_ITEM,
    { ...CASE_LIST_ITEM, dispute_id: 'DSP-041961', reason_code: 'unauthorized_transaction', dispute_amount: '3890.35' },
  ],
  total: 50000,
  page: 1,
  page_size: 20,
}

export const CASE_DETAIL: CaseDetail = {
  ...CASE_LIST_ITEM,
  transaction: {
    transaction_id: 'TXN-031597',
    merchant_id: 'MERCH-0039',
    amount: '27531.38',
    currency: 'INR',
    payment_method: 'upi',
    created_at: '2026-08-31T11:00:00Z',
    captured_at: '2026-08-31T11:07:00Z',
    status: 'captured',
    device_id: 'DEV-1313456352',
    ip_address: '196.31.40.152',
    billing_address_id: 'ADDR-6154829',
    shipping_address_id: 'ADDR-6154829',
    avs_result: 'Y',
    cvv_result: 'M',
    three_ds_authenticated: true,
  },
  customer: {
    customer_id: 'CUST-012494',
    account_created_at: '2026-04-19T12:00:00Z',
    country: 'AE',
    account_age_days: 135,
    previous_order_count: 5,
    previous_successful_order_count: 4,
    previous_dispute_count: 0,
    previous_refund_count: 0,
  },
}

export const EVIDENCE_LIST: EvidenceItem[] = [
  {
    evidence_id: 'EVD-0081597',
    evidence_type: 'avs',
    available: true,
    value: { result: 'Y' },
    relevance: 'low',
    strength: 0.6973,
    created_at: '2026-10-13T11:07:00Z',
  },
  {
    evidence_id: 'EVD-0091597',
    evidence_type: 'proof_of_delivery',
    available: false,
    value: null,
    relevance: 'high',
    strength: 0,
    created_at: '2026-10-13T11:07:00Z',
  },
]

export const SCORE_RESPONSE: ScoreResponse = {
  case_id: 'DSP-031597',
  model_version: 'risk-v1',
  feature_schema_version: 'features-v1',
  reason_code: 'goods_not_received',
  raw_probability: 0.96784,
  calibrated_probability: 0.968005,
  risk_band: 'HIGH_WINNABILITY',
  calibration_method: 'sigmoid',
  top_positive_factors: [
    { feature: 'strong_evidence_count', contribution: 1.471977, value: 14, description: '14 evidence items are strong.' },
  ],
  top_negative_factors: [
    {
      feature: 'ev_proof_of_delivery_strength',
      contribution: -0.034062,
      value: 0,
      description: 'Proof of delivery evidence has a strength of 0.00.',
    },
  ],
  evidence_summary: {
    total: 16,
    available: 14,
    strong: 14,
    high_relevance_total: 5,
    high_relevance_available: 4,
    missing_key_types: ['proof_of_delivery'],
  },
  disclaimer: 'Winnability probability only. This is decision SUPPORT, not a recommendation to contest.',
}

export function makeDecision(overrides: Partial<DecisionResponse> = {}): DecisionResponse {
  return {
    case_id: 'DSP-031597',
    model_version: 'risk-v1',
    feature_schema_version: 'features-v1',
    decision_policy_version: 'decision-v1',
    reason_code: 'goods_not_received',
    decision: 'CONTEST',
    reason: 'Expected recovery materially exceeds estimated contest cost.',
    evidence_gap_downgrade: false,
    calibrated_probability: 0.968005,
    risk_band: 'HIGH_WINNABILITY',
    dispute_amount: 8500,
    recovery_rate: 1.0,
    recoverable_amount: 8500,
    contest_cost: 300,
    expected_recovery: 8228,
    expected_net_value: 7928,
    break_even_probability: 0.0353,
    break_even_explanation: 'At current assumptions, this case becomes economically positive above a 3.5% win probability.',
    sensitivity: [
      { probability: 0.868, delta: -0.1, expected_recovery: 7378, expected_net_value: 7078 },
      { probability: 0.968, delta: 0, expected_recovery: 8228, expected_net_value: 7928 },
    ],
    top_positive_factors: SCORE_RESPONSE.top_positive_factors,
    top_negative_factors: SCORE_RESPONSE.top_negative_factors,
    evidence_summary: SCORE_RESPONSE.evidence_summary,
    disclaimer: 'Decision support only, not an instruction to act.',
    ...overrides,
  }
}
