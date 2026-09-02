import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { DemoCasePicker } from './components/common/DemoCasePicker'
import { CaseIntelligencePage } from './pages/CaseIntelligencePage'
import { DisputeInboxPage } from './pages/DisputeInboxPage'

function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DisputeInboxPage />} />
        {/* singular "/case/:id", not "/cases/:id" -- the latter collides with
            the dev proxy's "/cases" prefix (see vite.config.ts), which would
            forward this SPA route's own page request to the backend API */}
        <Route path="/case/:caseId" element={<CaseIntelligencePage />} />
      </Routes>
      {import.meta.env.DEV && <DemoCasePicker />}
    </AppShell>
  )
}

export default App
