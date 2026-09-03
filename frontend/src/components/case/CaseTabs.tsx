import { motion } from 'motion/react'
import { NavLink, useLocation } from 'react-router-dom'

const TABS = [
  { to: '', label: 'Overview' },
  { to: 'decision', label: 'Decision' },
  { to: 'evidence', label: 'Evidence' },
  { to: 'response', label: 'Response' },
  { to: 'audit', label: 'Audit' },
]

/**
 * Case-local sub-navigation. Duplicates the "current case" links already in
 * the sidebar -- deliberately, because the sidebar collapses to icons (or
 * hides entirely) on small screens (spec §"responsive"), and this row is
 * what keeps case context navigable there.
 */
export function CaseTabs({ caseId }: { caseId: string }) {
  const location = useLocation()
  const activeTo = TABS.slice()
    .reverse()
    .find((tab) => location.pathname === `/case/${caseId}${tab.to ? `/${tab.to}` : ''}`)?.to

  return (
    <nav aria-label="Case sections" className="flex gap-1 border-b border-ink-800">
      {TABS.map((tab) => {
        const isActive = tab.to === activeTo
        return (
          <NavLink
            key={tab.label}
            to={tab.to ? `/case/${caseId}/${tab.to}` : `/case/${caseId}`}
            end={tab.to === ''}
            className="relative px-3 py-2.5 text-sm font-medium text-ink-400 no-underline transition-colors hover:text-ink-100 aria-[current=page]:text-ink-50"
          >
            {tab.label}
            {isActive && (
              <motion.span
                layoutId="case-tab-underline"
                className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent-500"
                transition={{ duration: 0.2, ease: 'easeOut' }}
              />
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}
