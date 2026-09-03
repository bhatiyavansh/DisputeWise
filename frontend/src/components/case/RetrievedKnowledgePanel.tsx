import { useState } from 'react'
import type { RetrievalResult } from '../../api/types'
import { Panel } from '../common/Panel'

/**
 * The RAG layer's own retrieval results -- a citation list, not a chatbot
 * transcript. Each entry is a real chunk with its source, relevance score,
 * and the excerpt actually retrieved, exactly as returned by the backend.
 */
export function RetrievedKnowledgePanel({ sources }: { sources: RetrievalResult[] }) {
  return (
    <Panel title="Retrieved Knowledge" subtitle={`${sources.length} source chunk(s) retrieved for this reason code`}>
      <ul className="flex flex-col gap-3">
        {sources.map((source) => (
          <SourceCard key={source.chunk_id} source={source} />
        ))}
      </ul>
    </Panel>
  )
}

function SourceCard({ source }: { source: RetrievalResult }) {
  const [expanded, setExpanded] = useState(false)
  const excerpt = expanded || source.text.length <= 220 ? source.text : `${source.text.slice(0, 220)}…`

  return (
    <li className="rounded border border-ink-800 px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-ink-100">{source.source_name}</span>
        <span className="tabular text-xs text-ink-500" title="Relevance score">
          relevance {source.relevance_score.toFixed(2)}
        </span>
      </div>
      <p className="mt-1.5 text-sm text-ink-300">{excerpt}</p>
      {source.text.length > 220 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs font-medium text-accent-500 hover:text-accent-600"
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-600">
        <span>source: {source.source_id}</span>
        <span>chunk: {source.chunk_id}</span>
        <span>{source.metadata.doc_type}</span>
        {source.metadata.addresses_gap && <span className="text-review-600">addresses evidence gap</span>}
      </div>
    </li>
  )
}
