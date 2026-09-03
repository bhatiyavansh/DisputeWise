import type { SimulationRequest } from '../../api/types'

/**
 * The starting point for a new scenario. Deliberately a *neutral* case
 * rather than a pre-loaded winner: nothing here is tuned to make the model
 * or the policy look good, and every value is something a merchant would
 * know before the dispute is resolved.
 *
 * These are only the form's initial values -- the backend applies its own
 * documented defaults for anything omitted (app/schemas/simulation.py).
 */
export const SIMULATION_DEFAULTS: Required<
  Pick<
    SimulationRequest,
    | 'reason_code'
    | 'dispute_amount'
    | 'transaction_amount'
    | 'payment_method'
    | 'days_transaction_to_dispute'
    | 'days_to_respond'
    | 'three_ds_authenticated'
    | 'avs_result'
    | 'cvv_result'
    | 'device_match'
    | 'ip_match'
    | 'billing_shipping_match'
    | 'account_age_days'
    | 'previous_order_count'
    | 'previous_successful_order_count'
    | 'previous_dispute_count'
    | 'previous_refund_count'
    | 'delivery_confirmed'
    | 'tracking_available'
    | 'delivery_address_match'
    | 'proof_of_delivery'
    | 'customer_communication_available'
    | 'cancellation_request'
    | 'refund_request'
    | 'generate_response'
  >
> = {
  reason_code: 'goods_not_received',
  dispute_amount: 12000,
  transaction_amount: 12000,
  payment_method: 'card',
  days_transaction_to_dispute: 30,
  days_to_respond: 14,

  three_ds_authenticated: true,
  avs_result: 'Y',
  cvv_result: 'M',
  device_match: false,
  ip_match: false,
  billing_shipping_match: true,

  account_age_days: 180,
  previous_order_count: 4,
  previous_successful_order_count: 4,
  previous_dispute_count: 0,
  previous_refund_count: 0,

  delivery_confirmed: true,
  tracking_available: true,
  delivery_address_match: true,
  proof_of_delivery: false,

  customer_communication_available: false,
  cancellation_request: false,
  refund_request: false,

  generate_response: false,
}

export type SimulationFormState = typeof SIMULATION_DEFAULTS
