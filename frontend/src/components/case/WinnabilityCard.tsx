import type { ScoreResponse } from '../../api/types'
import { formatPercent } from '../../utils/format'
import { Panel } from '../common/Panel'
import { RiskBandBadge } from '../common/RiskBandBadge'

/**
 * The model's winnability estimate. Deliberately says nothing about whether
 * to contest -- that is the Economic Decision panel's job, driven by the
 * separate /decision endpoint. See the note at the bottom of this card.
 */
export function WinnabilityCard({ score }: { score: ScoreResponse }) {
  return (
    <Panel title="Winnability" subtitle="P(favorable outcome | evidence) -- Phase 2 model prediction">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="tabular text-5xl font-bold text-ink-50">{formatPercent(score.calibrated_probability, 1)}</p>
          <p className="mt-1 text-sm text-ink-500">
            calibrated probability{' '}
            <span className="tabular text-ink-400">(raw: {formatPercent(score.raw_probability, 1)})</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <RiskBandBadge band={score.risk_band} />
          <dl className="grid grid-cols-1 gap-x-4 text-right text-xs text-ink-500">
            <div>
              <dt className="inline">Model </dt>
              <dd className="inline font-mono text-ink-300">{score.model_version}</dd>
            </div>
            <div>
              <dt className="inline">Features </dt>
              <dd className="inline font-mono text-ink-300">{score.feature_schema_version}</dd>
            </div>
            <div>
              <dt className="inline">Calibration </dt>
              <dd className="inline font-mono text-ink-300">{score.calibration_method}</dd>
            </div>
          </dl>
        </div>
      </div>
      <p className="mt-4 border-t border-ink-800 pt-3 text-xs text-ink-500">
        A high winnability score is not a recommendation to contest. See{' '}
        <span className="font-medium text-ink-300">Economic Decision</span> below for whether contesting is
        worthwhile.
      </p>
    </Panel>
  )
}
