import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DEMO_CASES } from '../../utils/demoCases'

/**
 * DEV-ONLY manual-testing aid. Only rendered when `import.meta.env.DEV` is
 * true (see App.tsx) -- never present in a production build. Links to real
 * case IDs from the existing dataset; picking one navigates straight to its
 * Case Intelligence page.
 */
export function DemoCasePicker() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {open && (
        <div className="mb-2 w-80 rounded-lg border border-ink-700 bg-ink-900 p-3 shadow-xl">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-review-600">
            <span aria-hidden="true">⚠</span> Dev only -- demo cases
          </p>
          <ul className="flex flex-col gap-1.5">
            {DEMO_CASES.map((demo) => (
              <li key={demo.caseId}>
                <button
                  type="button"
                  onClick={() => {
                    navigate(`/case/${demo.caseId}`)
                    setOpen(false)
                  }}
                  className="w-full rounded border border-ink-800 px-2.5 py-1.5 text-left transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
                >
                  <span className="block font-mono text-xs text-accent-500">{demo.caseId}</span>
                  <span className="block text-xs font-medium text-ink-200">{demo.label}</span>
                  <span className="block text-[11px] text-ink-500">{demo.description}</span>
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                onClick={() => {
                  navigate('/case/DSP-999999')
                  setOpen(false)
                }}
                className="w-full rounded border border-ink-800 px-2.5 py-1.5 text-left transition-colors hover:bg-ink-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
              >
                <span className="block font-mono text-xs text-accent-500">DSP-999999</span>
                <span className="block text-xs font-medium text-ink-200">Unknown case (404 test)</span>
              </button>
            </li>
          </ul>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="rounded-full border border-ink-700 bg-ink-800 px-3 py-2 text-xs font-semibold text-ink-200 shadow-lg transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
      >
        {open ? 'Close' : 'Dev: Demo Cases'}
      </button>
    </div>
  )
}
