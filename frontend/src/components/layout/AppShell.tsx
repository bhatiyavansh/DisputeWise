import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { API_BASE_URL } from '../../api/client'
import { useApiHealth } from '../../hooks/useApiHealth'

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-ink-950">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-accent-600 focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      <header className="sticky top-0 z-40 border-b border-ink-800 bg-ink-950/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-center gap-2.5 text-ink-50 no-underline">
              <span className="flex h-7 w-7 items-center justify-center rounded bg-accent-600 text-xs font-bold text-white">
                DW
              </span>
              <span className="text-sm font-semibold tracking-tight">
                DisputeWise <span className="font-normal text-ink-400">Risk Command Center</span>
              </span>
            </NavLink>
            <nav aria-label="Primary" className="flex items-center gap-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                    isActive ? 'bg-ink-800 text-ink-50' : 'text-ink-400 hover:bg-ink-900 hover:text-ink-200'
                  }`
                }
              >
                Dispute Inbox
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3 text-xs text-ink-500">
            <span className="hidden font-mono sm:inline">{API_BASE_URL || 'same-origin (dev proxy)'}</span>
            <ApiStatusDot />
          </div>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-[1440px] px-6 py-6">
        {children}
      </main>
    </div>
  )
}

function ApiStatusDot() {
  const health = useApiHealth()
  const color = health === 'up' ? 'bg-contest-500' : health === 'down' ? 'bg-avoid-500' : 'bg-ink-500'
  const label = health === 'up' ? 'API online' : health === 'down' ? 'API unreachable' : 'Checking API…'
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-ink-700 px-2 py-0.5" role="status">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}
