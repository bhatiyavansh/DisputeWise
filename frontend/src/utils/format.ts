/** Handles the string-vs-number amount inconsistency documented in api/types.ts. */
export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const n = typeof value === 'number' ? value : Number.parseFloat(value)
  return Number.isFinite(n) ? n : null
}

const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

const currencyFormatterPrecise = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
})

export function formatCurrency(value: string | number | null | undefined, precise = false): string {
  const n = toNumber(value)
  if (n === null) return '—'
  return (precise ? currencyFormatterPrecise : currencyFormatter).format(n)
}

/** Signed currency, e.g. "+₹7,928" / "−₹56" -- used for expected net value. */
export function formatSignedCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const formatted = currencyFormatter.format(Math.abs(value))
  return value > 0 ? `+${formatted}` : value < 0 ? `−${formatted}` : formatted
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-IN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const REASON_CODE_LABELS: Record<string, string> = {
  unauthorized_transaction: 'Unauthorized Transaction',
  goods_not_received: 'Goods Not Received',
  duplicate_charge: 'Duplicate Charge',
}

export function formatReasonCode(code: string): string {
  return REASON_CODE_LABELS[code] ?? code
}

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  evidence_submitted: 'Evidence Submitted',
  under_review: 'Under Review',
  closed: 'Closed',
}

export function formatStatus(status: string): string {
  return STATUS_LABELS[status] ?? status
}

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  three_ds: '3-D Secure',
  avs: 'Address Verification (AVS)',
  cvv: 'CVV Match',
  device_match: 'Device Match',
  ip_match: 'IP Match',
  delivery_confirmed: 'Delivery Confirmed',
  tracking_available: 'Carrier Tracking',
  delivery_address_match: 'Delivery Address Match',
  delivery_timestamp: 'Delivery Timestamp',
  proof_of_delivery: 'Proof of Delivery',
  prior_order_history: 'Prior Order History',
  prior_successful_orders: 'Prior Successful Orders',
  prior_disputes: 'Prior Disputes',
  customer_communication_available: 'Customer Communication',
  cancellation_request: 'Cancellation Request',
  refund_request: 'Refund Request',
}

export function formatEvidenceType(type: string): string {
  return EVIDENCE_TYPE_LABELS[type] ?? type
}

/** Formats an evidence row's raw `value` JSON object as "Key: value" pairs.
 * Purely mechanical (key humanization + type-appropriate formatting) -- does
 * not interpret or invent meaning beyond what the API returned. */
export function formatEvidenceValue(value: Record<string, unknown> | null): string {
  if (!value || Object.keys(value).length === 0) return '—'
  return Object.entries(value)
    .map(([key, raw]) => {
      const label = key.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
      let formatted: string
      if (typeof raw === 'boolean') {
        formatted = raw ? 'Yes' : 'No'
      } else if (key.toLowerCase().includes('timestamp') && typeof raw === 'string') {
        formatted = formatDateTime(raw)
      } else {
        formatted = String(raw)
      }
      return `${label}: ${formatted}`
    })
    .join(' · ')
}

/** Turns a snake_case feature name into a short, readable label as a last
 * resort -- the API's own `description` field should be preferred wherever
 * one is present; this is only for the raw `feature` name shown as a caption. */
export function formatFeatureName(feature: string): string {
  return feature
    .replace(/^ev_/, '')
    .replace(/_(available|strength|value)$/, '')
    .replace(/_/g, ' ')
}
