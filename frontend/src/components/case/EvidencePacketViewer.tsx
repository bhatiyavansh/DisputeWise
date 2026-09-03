import { useState } from 'react'
import type { EvidencePacketItem, EvidencePacketResponse } from '../../api/types'
import { formatEvidenceType } from '../../utils/format'
import { Panel } from '../common/Panel'

/**
 * The structured packet from POST /evidence-packet -- the facts and evidence
 * a generated response would be grounded in. Rendered as labeled fact
 * groups + an evidence table, never as raw JSON by default (spec: analyst
 * workspace, not a debug view). A "View raw JSON" toggle is offered at the
 * bottom for anyone who wants it, but it starts closed.
 *
 * Every field rendered here comes straight from the response schema -- there
 * is no favorable_outcome / recovery_amount / any other hidden-target field
 * in this schema to begin with, so there is nothing to filter out.
 */
export function EvidencePacketViewer({ packet }: { packet: EvidencePacketResponse }) {
  const [showRaw, setShowRaw] = useState(false)

  return (
    <Panel title="Evidence Packet" subtitle={`generated ${packet.generated_at} -- schema ${packet.schema_version}`}>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <FactGroup
          title="Transaction"
          rows={[
            ['Payment method', packet.transaction.payment_method.toUpperCase()],
            ['Status', packet.transaction.transaction_status],
            ['3-D Secure', packet.transaction.three_ds_authenticated ? 'Authenticated' : 'Not authenticated'],
            ['AVS result', packet.transaction.avs_result],
            ['CVV result', packet.transaction.cvv_result],
          ]}
        />
        <FactGroup
          title="Customer"
          rows={[
            ['Account age', `${packet.customer.account_age_days} days`],
            ['Previous orders', String(packet.customer.previous_order_count)],
            ['Successful orders', String(packet.customer.previous_successful_order_count)],
            ['Previous disputes', String(packet.customer.previous_dispute_count)],
            ['Previous refunds', String(packet.customer.previous_refund_count)],
          ]}
        />
      </div>

      <div className="mt-6 border-t border-ink-800 pt-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">
          Evidence used for grounding ({packet.evidence.length})
        </h3>
        <ul className="flex flex-col divide-y divide-ink-800 overflow-hidden rounded border border-ink-800">
          {packet.evidence.map((item) => (
            <EvidenceRow key={item.evidence_id} item={item} />
          ))}
        </ul>
      </div>

      <div className="mt-6 border-t border-ink-800 pt-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Reason code guidance</h3>
        <p className="text-sm font-medium text-ink-100">{packet.guidance.reason_code_name}</p>
        <p className="mt-1 text-sm text-ink-400">{packet.guidance.description}</p>
        <p className="mt-1 text-xs text-ink-600">source: {packet.guidance.source_id}</p>
      </div>

      <div className="mt-5 border-t border-ink-800 pt-3">
        <button
          type="button"
          onClick={() => setShowRaw((v) => !v)}
          className="text-xs font-medium text-ink-500 underline decoration-dotted underline-offset-2 hover:text-ink-300"
        >
          {showRaw ? 'Hide raw JSON' : 'View raw JSON'}
        </button>
        {showRaw && (
          <pre className="mt-2 max-h-96 overflow-auto rounded border border-ink-800 bg-ink-950 p-3 text-xs text-ink-400">
            {JSON.stringify(packet, null, 2)}
          </pre>
        )}
      </div>
    </Panel>
  )
}

function FactGroup({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">{title}</h3>
      <dl className="flex flex-col gap-1.5 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-ink-500">{label}</dt>
            <dd className="tabular text-right text-ink-200">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function EvidenceRow({ item }: { item: EvidencePacketItem }) {
  return (
    <li className={`px-3 py-2.5 ${item.available ? '' : 'bg-avoid-50/5'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium text-ink-100">
          <span className={item.available ? 'text-contest-500' : 'text-avoid-500'} aria-hidden="true">
            {item.available ? '✓' : '✕'}
          </span>
          {formatEvidenceType(item.evidence_type)}
        </span>
        <span className="text-xs text-ink-500">{item.relevance}</span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-xs text-ink-500">
        <span>{item.claim_type}</span>
        {item.available && (
          <span className="tabular" title="Evidence strength (0-1)">
            strength {item.strength.toFixed(2)}
          </span>
        )}
      </div>
    </li>
  )
}
