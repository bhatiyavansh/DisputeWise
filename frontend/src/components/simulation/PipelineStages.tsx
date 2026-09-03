import { cn } from '../../utils/cn'
import { STAGES, type StageState } from './stageState'

/**
 * The pipeline stages, driven by what the response actually contains.
 *
 * Deliberately NOT a fake progress animation: /simulate is a single request,
 * so the frontend genuinely cannot observe the backend moving from scoring
 * to decision to retrieval. While in flight every stage reads "running";
 * once the response lands each stage is marked from real evidence in the
 * payload (a score object, a decision, gap coverage, retrieved chunks, a
 * generation block). Stages that did not run are shown as skipped, never as
 * complete.
 */

const STATE_CLASSES: Record<StageState, string> = {
  idle: 'text-ink-600',
  running: 'text-ink-300',
  done: 'text-contest-600',
  skipped: 'text-ink-600',
}

export function PipelineStages({
  states,
}: {
  states: Record<(typeof STAGES)[number], StageState>
}) {
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-2" aria-label="Simulation pipeline">
      {STAGES.map((stage, index) => {
        const state = states[stage]
        return (
          <li key={stage} className="flex items-center gap-1">
            <span
              className={cn(
                'flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wide',
                STATE_CLASSES[state],
              )}
            >
              <StageMark state={state} />
              {stage}
              {state === 'skipped' && <span className="text-ink-700">(not run)</span>}
            </span>
            {index < STAGES.length - 1 && (
              <span className="px-1 text-ink-700" aria-hidden="true">
                →
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function StageMark({ state }: { state: StageState }) {
  if (state === 'running') {
    return (
      <span
        className="h-2.5 w-2.5 animate-spin rounded-full border border-ink-600 border-t-accent-500"
        aria-hidden="true"
      />
    )
  }
  if (state === 'done') return <span aria-hidden="true">✓</span>
  if (state === 'skipped') return <span aria-hidden="true">–</span>
  return <span className="h-1.5 w-1.5 rounded-full bg-ink-700" aria-hidden="true" />
}
