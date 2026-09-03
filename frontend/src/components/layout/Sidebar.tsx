import { motion } from 'motion/react'
import { NavLink, useLocation } from 'react-router-dom'
import { cn } from '../../utils/cn'

/**
 * Persistent application sidebar. Aceternity's Sidebar pattern (animated
 * width collapse, icon-only rail state) implemented directly with `motion`
 * rather than pulled in as an installed package -- Aceternity distributes
 * components as copy-paste source, not an npm library.
 *
 * "Case Intelligence / Decisions / Evidence / AI Response / Audit Trail" are
 * real sections of an OPEN case, not standalone pages with their own data --
 * there is no "list all decisions across every case" endpoint, so showing
 * them as global links when no case is open would be a dead end / a fake
 * section. They appear here, scoped to the current case, only once a case
 * route is active.
 */

const CASE_ID_PATTERN = /^\/case\/([^/]+)/

const CASE_TABS = [
  { to: '', label: 'Case Intelligence' },
  { to: '/decision', label: 'Decisions' },
  { to: '/evidence', label: 'Evidence' },
  { to: '/response', label: 'AI Response' },
  { to: '/audit', label: 'Audit Trail' },
]

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const location = useLocation()
  const caseMatch = location.pathname.match(CASE_ID_PATTERN)
  const activeCaseId = caseMatch?.[1] ?? null

  return (
    <motion.aside
      animate={{ width: collapsed ? 60 : 232 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="sticky top-0 flex h-screen shrink-0 flex-col border-r border-ink-800 bg-ink-950"
    >
      <div className="flex h-14 items-center gap-2.5 border-b border-ink-800 px-4">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent-600 text-xs font-bold text-white">
          DW
        </span>
        {!collapsed && <span className="truncate text-sm font-semibold tracking-tight text-ink-50">DisputeWise</span>}
      </div>

      <nav aria-label="Primary" className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 py-3">
        <SidebarLink to="/disputes" label="Disputes" collapsed={collapsed} />
        <SidebarLink to="/risk" label="Portfolio Risk" collapsed={collapsed} />
        <SidebarLink to="/playground" label="Policy Playground" collapsed={collapsed} />
        <NavLink
          to="/simulation"
          title={collapsed ? 'Simulate New Dispute' : undefined}
          className={({ isActive }) =>
            cn(
              'mt-1 flex items-center gap-1.5 rounded-md border border-ink-700 px-2.5 py-1.5 text-sm font-medium text-ink-300 no-underline transition-colors hover:border-ink-600 hover:bg-ink-900 hover:text-ink-100',
              isActive && 'border-accent-600/50 bg-ink-800 text-ink-50',
            )
          }
        >
          <span aria-hidden="true">+</span>
          <span className={cn('truncate', collapsed && 'sr-only')}>Simulate New Dispute</span>
        </NavLink>

        {activeCaseId && (
          <div className="mt-5">
            {!collapsed && (
              <p className="mb-1.5 truncate px-2.5 font-mono text-[11px] font-medium uppercase tracking-wide text-ink-500">
                {activeCaseId}
              </p>
            )}
            <div className="flex flex-col gap-0.5">
              {CASE_TABS.map((tab) => (
                <SidebarLink
                  key={tab.label}
                  to={`/case/${activeCaseId}${tab.to}`}
                  label={tab.label}
                  collapsed={collapsed}
                  end={tab.to === ''}
                />
              ))}
            </div>
          </div>
        )}
      </nav>

      <button
        type="button"
        onClick={onToggle}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        className="flex h-10 items-center justify-center border-t border-ink-800 text-ink-500 transition-colors hover:bg-ink-900 hover:text-ink-200 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-500"
      >
        <ChevronIcon collapsed={collapsed} />
      </button>
    </motion.aside>
  )
}

function SidebarLink({
  to,
  label,
  collapsed,
  end,
}: {
  to: string
  label: string
  collapsed: boolean
  end?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(
          'flex items-center rounded-md px-2.5 py-1.5 text-sm font-medium text-ink-400 no-underline transition-colors hover:bg-ink-900 hover:text-ink-100',
          isActive && 'bg-ink-800 text-ink-50 hover:bg-ink-800 hover:text-ink-50',
        )
      }
    >
      <span className={cn('truncate', collapsed && 'sr-only')}>{label}</span>
      {collapsed && <span aria-hidden="true">{label.charAt(0)}</span>}
    </NavLink>
  )
}

function ChevronIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      className={cn('transition-transform', collapsed && 'rotate-180')}
      aria-hidden="true"
    >
      <path d="M10 3L5 8l5 5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
