import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { DemoCasePicker } from './components/common/DemoCasePicker'
import { CaseLayout } from './pages/case/CaseLayout'
import { CaseOverviewPage } from './pages/case/CaseOverviewPage'
import { CaseDecisionPage } from './pages/case/CaseDecisionPage'
import { CaseEvidencePage } from './pages/case/CaseEvidencePage'
import { CaseResponsePage } from './pages/case/CaseResponsePage'
import { CaseAuditPage } from './pages/case/CaseAuditPage'
import { DisputeInboxPage } from './pages/DisputeInboxPage'
import { SimulationPage } from './pages/SimulationPage'
import { PortfolioPage } from './pages/PortfolioPage'
import { PolicyPlaygroundPage } from './pages/PolicyPlaygroundPage'

function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/disputes" replace />} />
        <Route path="/disputes" element={<DisputeInboxPage />} />
        {/* "/simulation", not "/simulate" -- the latter is a proxied API
            prefix (see vite.config.ts), same collision the case route avoids */}
        <Route path="/simulation" element={<SimulationPage />} />
        {/* "/risk" and "/playground": "/portfolio" and "/policy" are proxied
            API prefixes, and Vite proxies by prefix match */}
        <Route path="/risk" element={<PortfolioPage />} />
        <Route path="/playground" element={<PolicyPlaygroundPage />} />
        {/* singular "/case/:id", not "/cases/:id" -- the latter collides with
            the dev proxy's "/cases" prefix (see vite.config.ts), which would
            forward this SPA route's own page request to the backend API */}
        <Route path="/case/:caseId" element={<CaseLayout />}>
          <Route index element={<CaseOverviewPage />} />
          <Route path="decision" element={<CaseDecisionPage />} />
          <Route path="evidence" element={<CaseEvidencePage />} />
          <Route path="response" element={<CaseResponsePage />} />
          <Route path="audit" element={<CaseAuditPage />} />
        </Route>
      </Routes>
      {import.meta.env.DEV && <DemoCasePicker />}
    </AppShell>
  )
}

export default App
