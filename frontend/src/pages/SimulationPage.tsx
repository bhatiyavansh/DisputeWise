import { useState } from 'react'
import { ApiError } from '../api/client'
import { runSimulation } from '../api/simulation'
import type { SimulationResponse } from '../api/types'
import { ErrorState } from '../components/common/ErrorState'
import { NumberField, Row, Section, SelectField, ToggleField } from '../components/simulation/FormControls'
import { PipelineStages } from '../components/simulation/PipelineStages'
import { stageStates } from '../components/simulation/stageState'
import { SimulationResult } from '../components/simulation/SimulationResult'
import { SIMULATION_DEFAULTS, type SimulationFormState } from '../components/simulation/simulationDefaults'

type RunStatus = 'idle' | 'running' | 'done' | 'error'

/**
 * Phase 6 scenario workspace: describe a hypothetical dispute, run it
 * through the real pipeline, inspect every stage.
 *
 * The form collects only facts available at decision time -- there is no
 * field for an outcome, and the backend rejects one outright.
 */
export function SimulationPage() {
  const [form, setForm] = useState<SimulationFormState>(SIMULATION_DEFAULTS)
  const [status, setStatus] = useState<RunStatus>('idle')
  const [result, setResult] = useState<SimulationResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  function set<K extends keyof SimulationFormState>(key: K, value: SimulationFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function run() {
    setStatus('running')
    setError(null)
    try {
      const response = await runSimulation(form)
      setResult(response)
      setStatus('done')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError('network', 'Unexpected error', null, caught))
      setStatus('error')
    }
  }

  function reset() {
    setForm(SIMULATION_DEFAULTS)
    setResult(null)
    setError(null)
    setStatus('idle')
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-semibold tracking-tight text-ink-50">Simulate a dispute</h1>
            <span className="rounded border border-review-500/40 bg-review-50/5 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-review-700">
              Scenario
            </span>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-ink-400">
            Runs a hypothetical dispute through the same pipeline as a real case — the same model, decision policy,
            evidence-gap analyzer and retrieval. Nothing is saved, and no real merchant dispute is affected.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {status === 'done' && (
            <button
              type="button"
              onClick={reset}
              className="rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-sm font-medium text-ink-200 transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
            >
              Reset
            </button>
          )}
          <button
            type="button"
            onClick={run}
            disabled={status === 'running'}
            className="rounded bg-accent-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500"
          >
            {status === 'running' ? 'Running…' : status === 'done' ? 'Run again' : 'Run simulation'}
          </button>
        </div>
      </header>

      {status !== 'idle' && (
        <div className="rounded-lg border border-ink-800 bg-ink-900 px-4 py-3">
          <PipelineStages states={stageStates(status, result)} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void run()
          }}
          className="h-fit rounded-lg border border-ink-800 bg-ink-900 px-5 py-1"
        >
          <Section title="Transaction" summary="amount, method, timing" defaultOpen>
            <SelectField
              label="Reason code"
              value={form.reason_code}
              onChange={(value) => set('reason_code', value)}
              options={[
                { value: 'goods_not_received', label: 'Goods Not Received' },
                { value: 'unauthorized_transaction', label: 'Unauthorized Transaction' },
                { value: 'duplicate_charge', label: 'Duplicate Charge' },
              ]}
            />
            <NumberField
              label="Disputed amount"
              value={form.dispute_amount}
              onChange={(value) => {
                set('dispute_amount', value)
                set('transaction_amount', value)
              }}
              min={1}
              prefix="₹"
            />
            <SelectField
              label="Payment method"
              value={form.payment_method}
              onChange={(value) => set('payment_method', value)}
              options={[
                { value: 'card', label: 'Card' },
                { value: 'upi', label: 'UPI' },
                { value: 'netbanking', label: 'Netbanking' },
              ]}
            />
            <NumberField
              label="Days transaction → dispute"
              value={form.days_transaction_to_dispute}
              onChange={(value) => set('days_transaction_to_dispute', value)}
            />
            <NumberField
              label="Days to respond"
              value={form.days_to_respond}
              onChange={(value) => set('days_to_respond', value)}
            />
          </Section>

          <Section title="Authentication" summary="3DS, AVS, CVV">
            <ToggleField
              label="3-D Secure authenticated"
              value={form.three_ds_authenticated}
              onChange={(value) => set('three_ds_authenticated', value)}
            />
            <SelectField
              label="AVS result"
              hint="Y = full match"
              value={form.avs_result}
              onChange={(value) => set('avs_result', value)}
              options={[
                { value: 'Y', label: 'Y — match' },
                { value: 'N', label: 'N — no match' },
                { value: 'U', label: 'U — unavailable' },
                { value: 'M', label: 'M — partial' },
              ]}
            />
            <SelectField
              label="CVV result"
              hint="M = match"
              value={form.cvv_result}
              onChange={(value) => set('cvv_result', value)}
              options={[
                { value: 'M', label: 'M — match' },
                { value: 'N', label: 'N — no match' },
                { value: 'U', label: 'U — unavailable' },
              ]}
            />
            <ToggleField label="Device match" value={form.device_match} onChange={(v) => set('device_match', v)} />
            <ToggleField label="IP match" value={form.ip_match} onChange={(v) => set('ip_match', v)} />
            <ToggleField
              label="Billing = shipping address"
              value={form.billing_shipping_match}
              onChange={(v) => set('billing_shipping_match', v)}
            />
          </Section>

          <Section title="Customer" summary="account history">
            <NumberField
              label="Account age (days)"
              value={form.account_age_days}
              onChange={(v) => set('account_age_days', v)}
            />
            <NumberField
              label="Previous orders"
              value={form.previous_order_count}
              onChange={(v) => set('previous_order_count', v)}
            />
            <NumberField
              label="Previous successful orders"
              hint="cannot exceed previous orders"
              value={form.previous_successful_order_count}
              onChange={(v) => set('previous_successful_order_count', v)}
            />
            <NumberField
              label="Previous disputes"
              value={form.previous_dispute_count}
              onChange={(v) => set('previous_dispute_count', v)}
            />
            <NumberField
              label="Previous refunds"
              value={form.previous_refund_count}
              onChange={(v) => set('previous_refund_count', v)}
            />
          </Section>

          <Section title="Fulfillment" summary="delivery evidence" defaultOpen>
            <ToggleField
              label="Delivery confirmed"
              value={form.delivery_confirmed}
              onChange={(v) => set('delivery_confirmed', v)}
            />
            <ToggleField
              label="Tracking available"
              value={form.tracking_available}
              onChange={(v) => set('tracking_available', v)}
            />
            <ToggleField
              label="Delivery address match"
              value={form.delivery_address_match}
              onChange={(v) => set('delivery_address_match', v)}
            />
            <ToggleField
              label="Proof of delivery"
              value={form.proof_of_delivery}
              onChange={(v) => set('proof_of_delivery', v)}
            />
          </Section>

          <Section title="Communication" summary="customer contact record">
            <ToggleField
              label="Customer communication on file"
              value={form.customer_communication_available}
              onChange={(v) => set('customer_communication_available', v)}
            />
            <ToggleField
              label="Cancellation was requested"
              value={form.cancellation_request}
              onChange={(v) => set('cancellation_request', v)}
            />
            <ToggleField
              label="Refund was requested"
              value={form.refund_request}
              onChange={(v) => set('refund_request', v)}
            />
          </Section>

          <Section title="Response generation" summary="optional, slow">
            <ToggleField
              label="Generate a draft response"
              hint="Live LLM call + claim verification. Can take up to a minute."
              value={form.generate_response}
              onChange={(v) => set('generate_response', v)}
            />
            <Row label="Everything else is deterministic" hint="scoring, decision, gap and retrieval always run">
              <span />
            </Row>
          </Section>
        </form>

        <div className="min-w-0">
          {status === 'idle' && (
            <div className="rounded-lg border border-dashed border-ink-800 px-5 py-10 text-center">
              <p className="text-sm text-ink-400">Describe a scenario, then run it.</p>
              <p className="mt-1 text-xs text-ink-600">
                Results appear here: P(win), decision, economics, evidence gaps and retrieved requirements.
              </p>
            </div>
          )}
          {status === 'error' && (
            <ErrorState
              error={error}
              title={error?.kind === 'invalid' ? 'This scenario was rejected' : undefined}
              onRetry={() => void run()}
            />
          )}
          {status === 'running' && (
            <div className="rounded-lg border border-ink-800 bg-ink-900 px-5 py-10 text-center">
              <p className="text-sm text-ink-400">Running the pipeline…</p>
            </div>
          )}
          {status === 'done' && result && <SimulationResult result={result} />}
        </div>
      </div>
    </div>
  )
}
