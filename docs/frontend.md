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

One consequence: the frontend's own page route for a case's detail view could **not** be `/cases/:caseId`, because that string also matches the proxy's `/cases` prefix — the dev server would try to proxy the page navigation itself to the backend instead of serving the React app. The case detail route is therefore the singular `/case/:caseId` (see `src/App.tsx`). This tripped up initial testing in a real browser (curl doesn't enforce CORS or hit this collision, so it looked fine until actually opened in Chromium) — worth knowing if you extend routing later.

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
- the Evidence Coverage bar's "Missing high-relevance evidence" warning,
- the Evidence Inventory row for Proof of Delivery (marked unavailable, dimmed row),
- the Economic Decision panel's evidence-gap notice (the case would otherwise qualify for CONTEST).

### Test API failure

Stop the backend (`docker compose stop backend` from the repo root) and reload any page. You should see:
- Dispute Inbox: a page-level error state with **Retry**.
- Case detail: independent error states per section — "Risk scoring unavailable" for `/score`, "Decision engine unavailable" for `/decision" — never a fabricated probability or decision. Restart the backend and click Retry (or reload) to recover.

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
  api/           client.ts (typed fetch wrapper + ApiError), cases.ts, scoring.ts,
                 decisions.ts (real endpoint + isolated dev mock), types.ts (mirrors
                 the ACTUAL backend response shapes -- see the file's own header
                 comment for two real serialization quirks it deliberately preserves)
  hooks/         useAsyncResource (generic fetch/cache/error hook), useCaseWorkspace
                 (case/evidence/score/decision), useCases (inbox pagination/filters),
                 usePageEconomics (batched per-page score+decision fetch), useApiHealth
  components/
    layout/      AppShell (nav + live API health indicator)
    inbox/       SummaryStats, FilterBar, DisputeTable, DisputeRow, Pagination
    case/        CaseHeader, WinnabilityCard, ShapPanel, EvidenceInventory,
                 EconomicDecisionPanel, BreakEvenVisualization, SensitivityTable,
                 DecisionExplanation, EvidenceResponsePlaceholder (Phase 4 slot),
                 CaseRawDetail
    common/      DecisionBadge, RiskBandBadge, DecisionSourceBadge, EvidenceCoverageBar
                 (reusable -- built for Phase 4's Evidence Gap Analyzer to reuse),
                 ErrorState, EmptyState, LoadingStates (skeletons), DemoCasePicker (dev-only)
  pages/         DisputeInboxPage, CaseIntelligencePage
  utils/         format.ts (currency/percent/date formatting, all amount-parsing
                 goes through toNumber() to handle the string-vs-number quirk),
                 evidenceCategories.ts (mirrors the backend's real 4-category
                 taxonomy -- no invented "Payment"/"Other" bucket), demoCases.ts
```

### Performance notes

- Case detail: case, evidence, score, and decision are fetched once in parallel per case and cached in-memory for the session (`useAsyncResource`'s module-level cache) — revisiting a case doesn't refetch it.
- Dispute Inbox: there is no bulk-scoring backend endpoint, so `/score` + `/decision` are fetched per row, but only for the **current page** (`usePageEconomics`), not the full 50,000-row dataset. Page size is capped at 20 to keep this bounded. The summary stats and "Decision" filter are explicitly labeled "this page" wherever they depend on this — see `SummaryStats.tsx`'s header comment for the full reasoning.
- No polling anywhere except the API health indicator (30s interval, `useApiHealth`).

## Tests

`npm run test` (Vitest + Testing Library, jsdom). 24 tests across 6 files, covering: inbox rendering from real API shapes, case detail rendering the correct case, calibrated probability display, SHAP factor rendering (and that contributions are never shown as a probability), missing-evidence display, all three decision states rendering with backend-verbatim numbers, error states (network/500/503), the not-found state, that no probability renders when scoring fails, that the panel never recomputes a decision (renders exactly what the backend returned, even deliberately inconsistent numbers), and that no decision is silently shown when `/decision` is unavailable and the mock is disabled.
