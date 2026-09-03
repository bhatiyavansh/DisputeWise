import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'

/**
 * Global "jump to case" box in the top bar. Not a fake command palette --
 * just a text field that navigates to the singular /case/:id route once a
 * case ID is entered, available from anywhere in the app (not just the inbox).
 */
export function QuickCaseLookup() {
  const [value, setValue] = useState('')
  const navigate = useNavigate()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = value.trim().toUpperCase()
    if (!trimmed) return
    navigate(`/case/${trimmed}`)
    setValue('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center">
      <label htmlFor="quick-case-lookup" className="sr-only">
        Open case by ID
      </label>
      <input
        id="quick-case-lookup"
        type="text"
        placeholder="Go to case (e.g. DSP-031597)"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-56 rounded border border-ink-700 bg-ink-900 px-3 py-1.5 font-mono text-xs text-ink-100 placeholder:text-ink-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
      />
    </form>
  )
}
