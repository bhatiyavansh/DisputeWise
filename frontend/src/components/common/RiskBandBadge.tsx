import type { RiskBand } from '../../api/types'

const RISK_BAND_META: Record<RiskBand, { label: string; classes: string }> = {
  HIGH_WINNABILITY: { label: 'High Winnability', classes: 'bg-contest-50 text-contest-700 ring-contest-500/40' },
  MEDIUM_WINNABILITY: { label: 'Medium Winnability', classes: 'bg-review-50 text-review-700 ring-review-500/40' },
  LOW_WINNABILITY: { label: 'Low Winnability', classes: 'bg-avoid-50 text-avoid-700 ring-avoid-500/40' },
}

export function RiskBandBadge({ band }: { band: RiskBand }) {
  const meta = RISK_BAND_META[band]
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${meta.classes}`}>
      {meta.label}
    </span>
  )
}
