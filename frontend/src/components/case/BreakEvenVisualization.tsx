import { formatPercent } from '../../utils/format'

/**
 * "High win probability" is not the same as "worth contesting" -- this is
 * one of DisputeWise's key differentiators (spec §11), so it gets its own
 * visual rather than being folded into a table row.
 */
export function BreakEvenVisualization({
  currentProbability,
  breakEvenProbability,
}: {
  currentProbability: number
  breakEvenProbability: number | null
}) {
  if (breakEvenProbability === null) {
    return (
      <div className="rounded border border-ink-800 bg-ink-850 px-4 py-3 text-sm text-ink-400">
        Break-even probability is undefined for this case (recoverable amount is zero).
      </div>
    )
  }

  const clampedBreakEven = Math.min(1, Math.max(0, breakEvenProbability))
  const clampedCurrent = Math.min(1, Math.max(0, currentProbability))
  const margin = currentProbability - breakEvenProbability

  return (
    <div>
      <div className="flex items-center justify-between text-xs text-ink-500">
        <span>0%</span>
        <span>100%</span>
      </div>
      <div className="relative mt-1 h-3 rounded-full bg-ink-800">
        {/* margin band between break-even and current probability */}
        <div
          className={`absolute top-0 h-full rounded-full ${margin >= 0 ? 'bg-contest-500/30' : 'bg-avoid-500/30'}`}
          style={{
            left: `${Math.min(clampedBreakEven, clampedCurrent) * 100}%`,
            width: `${Math.abs(clampedCurrent - clampedBreakEven) * 100}%`,
          }}
        />
        <Marker position={clampedBreakEven} className="bg-ink-300" />
        <Marker position={clampedCurrent} className={margin >= 0 ? 'bg-contest-500' : 'bg-avoid-500'} />
      </div>
      <div className="relative mt-1 h-8 text-xs">
        <Label position={clampedBreakEven} title="Break-even" value={formatPercent(breakEvenProbability)} />
        <Label position={clampedCurrent} title="Current P(win)" value={formatPercent(currentProbability)} emphasize />
      </div>
      <p className="mt-2 text-xs text-ink-500">
        Current win probability is{' '}
        <span className={margin >= 0 ? 'font-medium text-contest-600' : 'font-medium text-avoid-600'}>
          {margin >= 0 ? `${formatPercent(Math.abs(margin))} above` : `${formatPercent(Math.abs(margin))} below`}
        </span>{' '}
        the economic break-even point.
      </p>
    </div>
  )
}

function Marker({ position, className }: { position: number; className: string }) {
  return (
    <div
      className={`absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-ink-900 ${className}`}
      style={{ left: `${position * 100}%` }}
    />
  )
}

function Label({ position, title, value, emphasize = false }: { position: number; title: string; value: string; emphasize?: boolean }) {
  const clampedLeft = Math.min(88, Math.max(0, position * 100))
  return (
    <div className="absolute top-0 -translate-x-1/2 text-center" style={{ left: `${clampedLeft}%` }}>
      <p className="whitespace-nowrap text-ink-500">{title}</p>
      <p className={`tabular whitespace-nowrap font-semibold ${emphasize ? 'text-ink-50' : 'text-ink-300'}`}>{value}</p>
    </div>
  )
}
