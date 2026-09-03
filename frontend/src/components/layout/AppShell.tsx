import { type ReactNode, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { API_BASE_URL } from '../../api/client'
import { useApiHealth } from '../../hooks/useApiHealth'
import { Sidebar } from './Sidebar'
import { QuickCaseLookup } from './QuickCaseLookup'

const SECTION_LABELS: Record<string, string> = {
  '': 'Overview',
  decision: 'Decision',
  evidence: 'Evidence',
  response: 'Response',
  audit: 'Audit',
}

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex min-h-screen bg-ink-950">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-accent-600 focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center justify-between border-b border-ink-800 bg-ink-950/95 px-6 backdrop-blur">
          <Breadcrumb />
          <div className="flex items-center gap-3 text-xs text-ink-500">
            <QuickCaseLookup />
            <span className="hidden font-mono lg:inline">{API_BASE_URL || 'same-origin (dev proxy)'}</span>
            <ApiStatusDot />
          </div>
        </header>
        <main id="main-content" className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-6">
          {children}
        </main>
      </div>
    </div>
  )
}

function Breadcrumb() {
  const location = useLocation()
  const params = useParams<{ caseId?: string }>()

  if (!params.caseId) {
    return <span className="text-sm font-medium text-ink-200">Disputes</span>
  }

  const segments = location.pathname.split('/').filter(Boolean) // ["case", ":id", ...section]
  const section = segments[2] ?? ''
  const sectionLabel = SECTION_LABELS[section] ?? section

  return (
    <div className="flex items-center gap-1.5 text-sm">
      <span className="text-ink-500">Case</span>
      <span className="text-ink-600">/</span>
      <span className="font-mono font-medium text-ink-100">{params.caseId}</span>
      <span className="text-ink-600">/</span>
      <span className="font-medium text-ink-200">{sectionLabel}</span>
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
      <span className="hidden sm:inline">{label}</span>
    </span>
  )
}
