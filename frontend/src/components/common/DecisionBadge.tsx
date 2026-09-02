import type { Decision } from '../../api/types'

const DECISION_META: Record<
  Decision,
  { label: string; icon: string; classes: string; description: string }
> = {
  CONTEST: {
    label: 'Contest',
    icon: '✓',
    classes: 'bg-contest-50 text-contest-700 ring-1 ring-inset ring-contest-500/40',
    description: 'Positive economics and high model confidence',
  },
  HUMAN_REVIEW: {
    label: 'Human Review',
    icon: '!',
    classes: 'bg-review-50 text-review-700 ring-1 ring-inset ring-review-500/40',
    description: 'Economics or confidence are not conclusive -- needs a reviewer',
  },
  DO_NOT_CONTEST: {
    label: "Don't Contest",
    icon: '✕',
    classes: 'bg-avoid-50 text-avoid-700 ring-1 ring-inset ring-avoid-500/40',
    description: 'Negative economics and low model confidence',
  },
}

export function DecisionBadge({
  decision,
  size = 'md',
}: {
  decision: Decision
  size?: 'sm' | 'md' | 'lg'
}) {
  const meta = DECISION_META[decision]
  const sizeClasses =
    size === 'lg'
      ? 'px-4 py-2 text-base gap-2'
      : size === 'sm'
        ? 'px-2 py-0.5 text-xs gap-1'
        : 'px-3 py-1 text-sm gap-1.5'

  return (
    <span
      className={`inline-flex items-center rounded-md font-semibold ${sizeClasses} ${meta.classes}`}
      title={meta.description}
    >
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  )
}
