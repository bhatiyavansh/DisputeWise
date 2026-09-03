import { type ReactNode, useId, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'

/**
 * Quiet form primitives for the simulation workspace: label-left / control-
 * right rows on subtle dividers rather than a grid of boxed cards, so a
 * long scenario form still reads as a document.
 */

export function Section({
  title,
  summary,
  children,
  defaultOpen = false,
}: {
  title: string
  summary?: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <section className="border-b border-ink-800 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-500"
      >
        <span>
          <span className="text-sm font-medium text-ink-100">{title}</span>
          {summary && <span className="ml-3 text-xs text-ink-500">{summary}</span>}
        </span>
        <svg
          viewBox="0 0 16 16"
          width="12"
          height="12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className={`shrink-0 text-ink-500 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            {/* overflow-hidden above is required for the height animation,
                which makes it a clipping boundary -- so content keeps a small
                horizontal inset rather than sitting flush against it,
                otherwise a right-aligned control (the toggles) gets its
                border/thumb/focus ring cut off at the edge. */}
            <div className="flex flex-col gap-px px-0.5 pb-4 pr-1.5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

export function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <span className="min-w-0">
        <span className="block text-sm text-ink-300">{label}</span>
        {hint && <span className="block text-xs text-ink-600">{hint}</span>}
      </span>
      <span className="shrink-0">{children}</span>
    </div>
  )
}

export function NumberField({
  label,
  hint,
  value,
  onChange,
  min = 0,
  step = 1,
  prefix,
}: {
  label: string
  hint?: string
  value: number
  onChange: (value: number) => void
  min?: number
  step?: number
  prefix?: string
}) {
  const id = useId()
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <label htmlFor={id} className="min-w-0">
        <span className="block text-sm text-ink-300">{label}</span>
        {hint && <span className="block text-xs text-ink-600">{hint}</span>}
      </label>
      <span className="flex shrink-0 items-center gap-1.5">
        {prefix && <span className="text-xs text-ink-500">{prefix}</span>}
        <input
          id={id}
          type="number"
          inputMode="numeric"
          min={min}
          step={step}
          value={value}
          onChange={(e) => onChange(e.target.value === '' ? min : Number(e.target.value))}
          className="tabular w-28 rounded border border-ink-700 bg-ink-900 px-2 py-1 text-right text-sm text-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        />
      </span>
    </div>
  )
}

export function SelectField<T extends string>({
  label,
  hint,
  value,
  options,
  onChange,
}: {
  label: string
  hint?: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  const id = useId()
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <label htmlFor={id} className="min-w-0">
        <span className="block text-sm text-ink-300">{label}</span>
        {hint && <span className="block text-xs text-ink-600">{hint}</span>}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="shrink-0 rounded border border-ink-700 bg-ink-900 px-2 py-1 text-sm text-ink-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

export function ToggleField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint?: string
  value: boolean
  onChange: (value: boolean) => void
}) {
  const id = useId()
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <label htmlFor={id} className="min-w-0 cursor-pointer">
        <span className="block text-sm text-ink-300">{label}</span>
        {hint && <span className="block text-xs text-ink-600">{hint}</span>}
      </label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={value}
        aria-label={label}
        onClick={() => onChange(!value)}
        className={`relative mr-0.5 h-5 w-9 shrink-0 rounded-full border transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-500 ${
          value ? 'border-accent-500 bg-accent-600' : 'border-ink-700 bg-ink-800'
        }`}
      >
        <motion.span
          animate={{ x: value ? 16 : 2 }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
          className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full bg-ink-50"
        />
      </button>
    </div>
  )
}
