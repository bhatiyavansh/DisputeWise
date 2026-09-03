import type { ContributingFactor } from '../../api/types'
import { Panel } from '../common/Panel'

/**
 * Renders the ACTUAL SHAP factors from /score -- nothing here is invented.
 * `description` comes straight from the API (app/ml/explain.py's
 * describe_feature); the raw `feature` name and `contribution` are shown as
 * supporting detail, explicitly labeled as model log-odds units so they are
 * never mistaken for a probability.
 */
export function ShapPanel({
  positive,
  negative,
}: {
  positive: ContributingFactor[]
  negative: ContributingFactor[]
}) {
  return (
    <Panel
      title="Why the model thinks this"
      subtitle="SHAP attributions explain the MODEL'S prediction, in log-odds units -- not a probability breakdown"
    >
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <FactorList
          heading="What looks strong"
          emptyLabel="No positive drivers returned."
          factors={positive}
          tone="positive"
        />
        <FactorList
          heading="What reduces confidence"
          emptyLabel="No negative drivers returned."
          factors={negative}
          tone="negative"
        />
      </div>
    </Panel>
  )
}

function FactorList({
  heading,
  factors,
  emptyLabel,
  tone,
}: {
  heading: string
  factors: ContributingFactor[]
  emptyLabel: string
  tone: 'positive' | 'negative'
}) {
  const icon = tone === 'positive' ? '✓' : '⚠'
  const iconClass = tone === 'positive' ? 'text-contest-500' : 'text-review-500'

  return (
    <div>
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-ink-400">{heading}</h3>
      {factors.length === 0 ? (
        <p className="text-sm text-ink-600">{emptyLabel}</p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {factors.map((factor) => (
            <li key={factor.feature} className="flex items-start justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-start gap-2">
                <span className={`mt-0.5 shrink-0 ${iconClass}`} aria-hidden="true">
                  {icon}
                </span>
                <span className="min-w-0 text-ink-200">{factor.description}</span>
              </span>
              <span
                className={`tabular shrink-0 whitespace-nowrap font-mono text-xs ${tone === 'positive' ? 'text-contest-500' : 'text-avoid-500'}`}
                title="SHAP contribution in log-odds (margin) units, not a probability"
              >
                {factor.contribution > 0 ? '+' : ''}
                {factor.contribution.toFixed(3)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
