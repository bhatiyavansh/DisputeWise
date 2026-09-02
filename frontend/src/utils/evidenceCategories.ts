import type { EvidenceType } from '../api/types'

/**
 * Mirrors backend/app/ml/schema.py's EVIDENCE_CATEGORIES exactly -- these are
 * the real four categories the evidence taxonomy is organized into. There is
 * no "Payment" or "Other" category in the actual data, so none is invented
 * here.
 */
export const EVIDENCE_CATEGORIES: { key: string; label: string; types: EvidenceType[] }[] = [
  {
    key: 'authentication',
    label: 'Authentication',
    types: ['three_ds', 'avs', 'cvv', 'device_match', 'ip_match'],
  },
  {
    key: 'fulfillment',
    label: 'Fulfillment',
    types: [
      'delivery_confirmed',
      'tracking_available',
      'delivery_address_match',
      'delivery_timestamp',
      'proof_of_delivery',
    ],
  },
  {
    key: 'customer',
    label: 'Customer History',
    types: ['prior_order_history', 'prior_successful_orders', 'prior_disputes'],
  },
  {
    key: 'communication',
    label: 'Communication',
    types: ['customer_communication_available', 'cancellation_request', 'refund_request'],
  },
]

export function categoryForEvidenceType(type: EvidenceType): string {
  return EVIDENCE_CATEGORIES.find((c) => c.types.includes(type))?.label ?? 'Other'
}
