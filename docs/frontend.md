# Frontend — Risk Command Center

React + TypeScript + Vite + Tailwind CSS. A merchant-facing risk operations console for reviewing chargeback disputes, driven entirely by the real Phase 1/2/3 backend API. No backend code was modified to build this.

## Setup

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

Requires the backend running at `http://localhost:8001` (`docker compose up -d --build` from the repo root — see the main [README.md](../README.md)). Nothing else to configure: the dev server proxies API calls for you (see "Why a proxy?" below).

Other commands:

```bash
npm run build      # production build (tsc -b && vite build) -> dist/
npm run preview    # serve the production build locally, also proxied
npm run test       # run the test suite once
npm run test:watch # watch mode
npx tsc -b         # type-check only
```

## Why a proxy, and why the frontend route is `/case/:id` not `/cases/:id`

The backend does not send CORS headers, and per this project's rules the frontend must not modify backend code to add them. Instead, `vite.config.ts` proxies `/cases` and `/health` from the Vite dev/preview server through to `http://localhost:8001`, so every request the browser makes is same-origin — no CORS involved, zero backend changes.

One consequence: the frontend's own page route for a case's detail view could **not** be `/cases/:caseId`, because that string also matches the proxy's `/cases` prefix — the dev server would try to proxy the page navigation itself to the backend instead of serving the React app. The case detail route is therefore the singular `/case/:caseId`, with `/case/:caseId/decision`, `/case/:caseId/evidence`, `/case/:caseId/response`, and `/case/:caseId/audit` as nested sub-routes (see `src/App.tsx`). This tripped up initial testing in a real browser (curl doesn't enforce CORS or hit this collision, so it looked fine until actually opened in Chromium) — worth knowing if you extend routing later.

The inbox route is `/disputes` (`/` redirects there).

To point the frontend at a different backend (one that already sends its own CORS headers, for instance), set `VITE_API_BASE_URL` in `frontend/.env.local` — see `.env.example`.

## Manual testing

### Open a real case

Fastest path: run in dev mode and click the **"Dev: Demo Cases"** button in the bottom-right corner (only rendered when `import.meta.env.DEV` is true — never in a production build). It links to four real cases from the dataset, one per decision bucket, plus a deliberately unknown case ID:

| Case | What it demonstrates |
|---|---|
| `DSP-010035` | High winnability → **CONTEST** |
| `DSP-028533` | Borderline → **HUMAN_REVIEW** |
| `DSP-018767` | Low winnability → **DO_NOT_CONTEST** |
| `DSP-031597` | Strong case with missing `proof_of_delivery` → CONTEST downgraded to **HUMAN_REVIEW** |
| `DSP-999999` | Doesn't exist → 404 / not-found state |

These IDs were pulled from the live dataset by querying `/cases` and `/cases/{id}/decision` directly (see `src/utils/demoCases.ts` for the exact provenance note) — they are real rows, not fabricated fixtures.

Alternatively, from the Dispute Inbox: use the **"Open case by ID"** box in the filter bar, or click any row's Case ID link.

### View /score and /decision

Both fire automatically the moment a case detail page loads (`src/hooks/useCaseWorkspace.ts`) — no button needed. Open your browser's Network tab and filter for `score` / `decision` to inspect the raw responses, or just watch the Winnability card and Economic Decision panel populate.

### Test missing evidence

Open `DSP-031597` (see table above) — it's missing `proof_of_delivery`, a high-relevance evidence type for `goods_not_received`. You'll see it called out in:
- the Overview tab's Evidence Coverage bar warning,
- the **Evidence** tab's Evidence Gap Analysis panel (CRITICAL, from `/evidence-gap`) and the Evidence Inventory row for Proof of Delivery (marked unavailable, dimmed row),
- the **Decision** tab's evidence-gap notice (the case would otherwise qualify for CONTEST).

### Test the AI Response workflow

Open any case's **Response** tab and click **"Generate response draft"** — this calls the real `/draft` endpoint (an LLM call, can take up to ~60-90s) and is deliberately not auto-fired on tab open. You'll see the backend's own `response_state` rendered verbatim (`DRAFT_READY` / `DRAFT_FLAGGED` / `DRAFT_BLOCKED` / `GENERATION_UNAVAILABLE` — never softened), the drafted body, per-claim verification (expand a claim to see its cited evidence/source IDs and the verifier's explanation), and retrieved knowledge-base sources. The **Audit** tab's "Include response-generation provenance" button reuses this same cached result to show the full pipeline version trace (model → decision policy → evidence schema → knowledge base → prompt → verifier).

### Test API failure

Stop the backend (`docker compose stop backend` from the repo root) and reload any page. You should see:
- Dispute Inbox: a page-level error state with **Retry**.
- Case detail: independent error states per section — "Risk scoring unavailable" for `/score`, "Decision engine unavailable" for `/decision`, "Evidence gap analysis unavailable", "Response generation unavailable" — never a fabricated probability, decision, or draft. Restart the backend and click Retry (or reload) to recover.

### Test an unknown case

Navigate to `/case/DSP-999999` (or use the demo picker's last entry). You'll get a clear "Case not found" state, not a blank page or a crash.

## The `/decision` mock adapter

`/decision` is fully implemented on the backend and is used by default — there is nothing to switch on for normal use. A dev-only fallback exists purely for the scenario the original build brief anticipated (developing the frontend before Phase 3 shipped):

- `src/api/decisions.ts` always tries the real endpoint first.
- `src/api/devDecisionMock.ts` is the isolated placeholder — same `DecisionResponse` TypeScript shape, but its `reason`/`decision_policy_version` are prefixed `[DEV MOCK]` so it can never be mistaken for a real response, and it does not reimplement `decision-v1`'s actual logic (see the file's header comment).
- The mock only activates when **all** of: `import.meta.env.DEV` is true (impossible in a production build), `VITE_ENABLE_DECISION_MOCK=true` is explicitly set (see `.env.example`; off by default), and the real endpoint failed with a 503 ("unavailable") or a network error — never on a 404 (the case doesn't exist) or 422 (bad input).
- Whenever a mock decision is shown, a visible **"⚠ Dev Mock"** badge renders next to it (`DecisionSourceBadge`) — see it fire in `src/api/decisions.test.ts` and `EconomicDecisionPanel.test.tsx`.

To exercise it: set `VITE_ENABLE_DECISION_MOCK=true` in `.env.local`, stop the backend's `backend` container (or otherwise make `/decision` 503), and open any case.

Delete `src/api/devDecisionMock.ts` and the fallback branch in `src/api/decisions.ts` whenever this scaffolding is no longer wanted — both are self-contained.

## Architecture

```
src/
  api/           client.ts (typed fetch wrapper + ApiError, supports an optional
                 JSON body for /verify), cases.ts, scoring.ts,
                 decisions.ts (real endpoint + isolated dev mock),
                 evidence.ts (/evidence-gap, /evidence-packet),
                 response.ts (/draft, /verify),
                 types.ts (mirrors the ACTUAL backend response shapes -- see the
                 file's own header comment for two real serialization quirks it
                 deliberately preserves)
  hooks/         useAsyncResource (generic fetch/cache/error hook), useCaseWorkspace
                 (case/evidence/score/decision/evidence-gap/evidence-packet/draft --
                 draft is lazy, gated behind an `enabled` flag since it's an LLM
                 call), useCases (inbox pagination/filters), usePageEconomics
                 (batched per-page score+decision fetch), useApiHealth
  components/
    layout/      AppShell (sidebar + top bar shell), Sidebar (collapsible, shows
                 case-scoped links only when a case route is active),
                 QuickCaseLookup (top-bar "go to case" box)
    inbox/       SummaryStats, FilterBar, DisputeTable, DisputeRow, Pagination
    case/        CaseHeader, CaseTabs (case-local tab nav, mirrors the sidebar's
                 case links for small screens), WinnabilityCard, ShapPanel,
                 EvidenceInventory, EvidenceGapPanel, EvidencePacketViewer,
                 EconomicDecisionPanel, BreakEvenVisualization, SensitivityTable,
                 DecisionExplanation, ResponseDraftWorkspace, DraftStateBanner,
                 ClaimVerificationList, RetrievedKnowledgePanel, AuditTrailTimeline,
                 CaseRawDetail
    common/      DecisionBadge, RiskBandBadge, DecisionSourceBadge, EvidenceCoverageBar,
                 ErrorState, EmptyState, LoadingStates (skeletons), DemoCasePicker (dev-only)
  pages/         DisputeInboxPage,
                 case/CaseLayout (fetches case+score+decision once, renders header +
                 tabs + <Outlet>), case/CaseOverviewPage, CaseDecisionPage,
                 CaseEvidencePage, CaseResponsePage, CaseAuditPage
  utils/         cn.ts (clsx + tailwind-merge, for Aceternity-style components),
                 format.ts (currency/percent/date formatting, all amount-parsing
                 goes through toNumber() to handle the string-vs-number quirk),
                 evidenceCategories.ts (mirrors the backend's real 4-category
                 taxonomy -- no invented "Payment"/"Other" bucket), demoCases.ts
```

### Routes beyond the case workspace

`/simulation` (new-dispute simulation), `/risk` (portfolio view), and `/playground` (policy playground) round out the routes referenced above — named to avoid the same proxy-prefix collision as `/case/:id` (`/simulate`, `/portfolio`, and `/policy` are all proxied API prefixes; see "Why a proxy" above). Their API modules live at `src/api/simulation.ts`, `src/api/scenario.ts`, and `src/api/portfolio.ts`. The evidence-scenario "what if this evidence changed?" panel (`EvidenceScenarioPanel`) is rendered on the case Evidence tab, directly below `EvidenceGapPanel`.

### Case tab layout

`/case/:caseId/*` is a nested route under `CaseLayout`, which fetches case detail, `/score`, and `/decision` once and shares them with its child route (`useOutletContext`) — Overview, Decision, Evidence, Response, and Audit are separate route components, not a single flat page. Each tab that needs its own resource (evidence-gap, evidence-packet, draft) fetches it independently via the hooks in `useCaseWorkspace.ts`; because `useAsyncResource` caches by a `resource:caseId` key at module scope, switching tabs never re-fetches something already loaded — including score/decision/case, which the layout and no other component re-requests.

### Performance notes

- Case detail: case, evidence, score, decision, evidence-gap, and evidence-packet are all cheap/deterministic and safe to fetch as soon as their tab mounts; each is cached in-memory for the session (`useAsyncResource`'s module-level cache) — revisiting a case or tab doesn't refetch it.
- `/draft` is the one expensive resource (a live LLM call, up to ~60-90s) — it is never fetched automatically. The Response tab requires an explicit "Generate response draft" click; the Audit tab has its own explicit "Include response-generation provenance" toggle that reuses the same cached result if the Response tab was already visited.
- Dispute Inbox: there is no bulk-scoring backend endpoint, so `/score` + `/decision` are fetched per row, but only for the **current page** (`usePageEconomics`), not the full 50,000-row dataset. Page size is capped at 20 to keep this bounded.
- No polling anywhere except the API health indicator (30s interval, `useApiHealth`).

## Tests

`npm run test` (Vitest + Testing Library, jsdom). Covers: inbox rendering from real API shapes, case header/tab rendering the correct case, calibrated probability display, SHAP factor rendering (and that contributions are never shown as a probability), missing-evidence display on the Evidence tab (both the inventory and the `/evidence-gap` coverage numbers), all three decision states rendering with backend-verbatim numbers on the Decision tab, error states (network/500/503) per tab, the not-found state, that no probability renders when scoring fails, that no decision is silently shown when `/decision` is unavailable, and that the Response tab requires an explicit action before calling `/draft` and never softens a `DRAFT_BLOCKED` state into a ready one.
