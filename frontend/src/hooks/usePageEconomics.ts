import { useEffect, useRef, useState } from 'react'
import { decideCase } from '../api/decisions'
import { scoreCase } from '../api/scoring'
import type { CaseListItem, DecisionResponse, ScoreResponse } from '../api/types'
import { toNumber } from '../utils/format'

export interface RowEconomics {
  scoreStatus: 'loading' | 'success' | 'error'
  score: ScoreResponse | null
  decisionStatus: 'loading' | 'success' | 'error'
  decision: DecisionResponse | null
  decisionSource: 'real' | 'mock' | null
}

const emptyRow: RowEconomics = {
  scoreStatus: 'loading',
  score: null,
  decisionStatus: 'loading',
  decision: null,
  decisionSource: null,
}

/**
 * Fetches /score + /decision for exactly the currently-visible page of
 * cases -- one hook call per page render, not one per row. There is no
 * bulk-scoring backend endpoint, so this is bounded by page_size, fired in
 * parallel, and updates progressively as each case resolves (used both to
 * populate the table's per-row cells and the page-level summary stats).
 */
export function usePageEconomics(items: CaseListItem[]): Map<string, RowEconomics> {
  const [rows, setRows] = useState<Map<string, RowEconomics>>(new Map())
  const idsKey = items.map((i) => i.dispute_id).join(',')
  const amountsRef = useRef<Map<string, string>>(new Map())
  amountsRef.current = new Map(items.map((i) => [i.dispute_id, i.dispute_amount]))

  useEffect(() => {
    const controller = new AbortController()
    setRows(new Map(items.map((i) => [i.dispute_id, emptyRow])))

    for (const item of items) {
      const caseId = item.dispute_id

      scoreCase(caseId, controller.signal)
        .then((score) => {
          if (controller.signal.aborted) return
          setRows((prev) => new Map(prev).set(caseId, { ...(prev.get(caseId) ?? emptyRow), scoreStatus: 'success', score }))

          decideCase(caseId, { score, disputeAmount: toNumber(amountsRef.current.get(caseId)) ?? undefined }, controller.signal)
            .then((result) => {
              if (controller.signal.aborted) return
              setRows((prev) =>
                new Map(prev).set(caseId, {
                  ...(prev.get(caseId) ?? emptyRow),
                  decisionStatus: 'success',
                  decision: result.data,
                  decisionSource: result.source,
                }),
              )
            })
            .catch(() => {
              if (controller.signal.aborted) return
              setRows((prev) => new Map(prev).set(caseId, { ...(prev.get(caseId) ?? emptyRow), decisionStatus: 'error' }))
            })
        })
        .catch(() => {
          if (controller.signal.aborted) return
          setRows((prev) =>
            new Map(prev).set(caseId, { ...(prev.get(caseId) ?? emptyRow), scoreStatus: 'error', decisionStatus: 'error' }),
          )
        })
    }

    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey])

  return rows
}
