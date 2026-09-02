import type { CaseDetail } from '../../api/types'
import { formatCurrency, formatDate, formatDateTime, formatReasonCode, formatStatus } from '../../utils/format'

/** Lowest priority on the page per spec's visual hierarchy -- raw
 * case/transaction/customer fields for a reviewer who wants to dig deeper. */
export function CaseRawDetail({ caseDetail }: { caseDetail: CaseDetail }) {
  const { transaction, customer } = caseDetail

  return (
    <details className="rounded-lg border border-ink-800 bg-ink-900">
      <summary className="cursor-pointer select-none px-5 py-3.5 text-sm font-semibold text-ink-100">
        Case, transaction &amp; customer details
      </summary>
      <div className="border-t border-ink-800 px-5 py-4">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <DetailGroup
            title="Dispute"
            rows={[
              ['Reason', formatReasonCode(caseDetail.reason_code)],
              ['Status', formatStatus(caseDetail.status)],
              ['Amount', formatCurrency(caseDetail.dispute_amount, true)],
              ['Filed', formatDateTime(caseDetail.created_at)],
              ['Response deadline', formatDate(caseDetail.response_deadline)],
            ]}
          />
          <DetailGroup
            title="Transaction"
            rows={[
              ['Transaction ID', transaction.transaction_id],
              ['Amount', formatCurrency(transaction.amount, true)],
              ['Payment method', transaction.payment_method.toUpperCase()],
              ['Status', transaction.status],
              ['3-D Secure', transaction.three_ds_authenticated ? 'Authenticated' : 'Not authenticated'],
              ['AVS result', transaction.avs_result],
              ['CVV result', transaction.cvv_result],
              ['Captured', formatDateTime(transaction.captured_at)],
            ]}
          />
          <DetailGroup
            title="Customer"
            rows={[
              ['Customer ID', customer.customer_id],
              ['Country', customer.country],
              ['Account age', `${customer.account_age_days} days`],
              ['Previous orders', String(customer.previous_order_count)],
              ['Successful orders', String(customer.previous_successful_order_count)],
              ['Previous disputes', String(customer.previous_dispute_count)],
              ['Previous refunds', String(customer.previous_refund_count)],
            ]}
          />
        </div>
      </div>
    </details>
  )
}

function DetailGroup({ title, rows }: { title: string; rows: [string, string][] }) {
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
