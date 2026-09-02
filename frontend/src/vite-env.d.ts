/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  /** DEV ONLY: enable the isolated /decision mock fallback (src/api/devDecisionMock.ts).
   * Only ever consulted when `import.meta.env.DEV` is also true. */
  readonly VITE_ENABLE_DECISION_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
