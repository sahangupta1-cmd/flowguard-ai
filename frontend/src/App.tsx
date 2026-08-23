import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  Database,
  IndianRupee,
  LayoutDashboard,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  UploadCloud,
  WalletCards,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import './App.css'
import UploadDataModal from './components/UploadDataModal'
import AskFlowGuardPanel from './components/AskFlowGuardPanel'
import {
  getCFOOverview,
  getPaymentDelays,
  getCustomerRiskDrilldown,
  type CFOOverview,
  type PaymentDelayPrediction,
  type CustomerRiskResponse,
} from './lib/api'


type Tone =
  | 'blue'
  | 'violet'
  | 'amber'
  | 'green'


function formatMoney(
  value: string | number,
): string {
  const amount = Number(value)

  if (!Number.isFinite(amount)) {
    return '₹0'
  }

  if (Math.abs(amount) >= 10_000_000) {
    return `₹${(amount / 10_000_000).toFixed(2)}Cr`
  }

  if (Math.abs(amount) >= 100_000) {
    return `₹${(amount / 100_000).toFixed(2)}L`
  }

  return new Intl.NumberFormat(
    'en-IN',
    {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    },
  ).format(amount)
}



function formatFinancialText(
  text: string,
): string {
  return text.replace(
    /\b\d+(?:\.\d+)?\b/g,
    (match) => {
      const value = Number(match)

      if (
        Number.isFinite(value) &&
        Math.abs(value) >= 100_000
      ) {
        return formatMoney(value)
      }

      return match
    },
  )
}


function scrollToSection(
  id: string,
): void {
  document
    .getElementById(id)
    ?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
}


function MetricCard({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ReactNode
  label: string
  value: string
  detail: string
  tone: Tone
}) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <div className="metric-top">
        <div className="metric-icon">
          {icon}
        </div>

        <ArrowUpRight size={17} />
      </div>

      <p className="metric-label">
        {label}
      </p>

      <h2>{value}</h2>

      <p className="metric-detail">
        {detail}
      </p>
    </article>
  )
}


function ProgressRow({
  label,
  value,
  percentage,
}: {
  label: string
  value: string
  percentage: number
}) {
  const safePercentage = Math.max(
    0,
    Math.min(100, percentage),
  )

  return (
    <div className="progress-row">
      <div className="progress-copy">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>

      <div className="progress-track">
        <div
          className="progress-fill"
          style={{
            width: `${safePercentage}%`,
          }}
        />
      </div>
    </div>
  )
}


function LoadingScreen() {
  return (
    <main className="state-screen">
      <div className="state-logo">
        <Sparkles size={24} />
      </div>

      <h1>Loading FlowGuard</h1>

      <p>
        Preparing operational finance intelligence…
      </p>
    </main>
  )
}


function App() {
  const [overview, setOverview] =
    useState<CFOOverview | null>(null)

  const [loading, setLoading] =
    useState(true)

  const [error, setError] =
    useState<string | null>(null)

  const [lastUpdated, setLastUpdated] =
    useState<Date | null>(null)


  const [uploadModalOpen, setUploadModalOpen] =
    useState(false)

  const [askFlowGuardOpen, setAskFlowGuardOpen] =
    useState(false)

  const [askFlowGuardPrompt, setAskFlowGuardPrompt] =
    useState('')

  const [currentImportId, setCurrentImportId] =
    useState<string | null>(null)

  const [datasetLabel, setDatasetLabel] =
    useState('Demo dataset')

  const [invoicePredictions, setInvoicePredictions] =
    useState<PaymentDelayPrediction[]>([])

  const [invoiceLoading, setInvoiceLoading] =
    useState(false)

  const [invoiceError, setInvoiceError] =
    useState<string | null>(null)

  const [customerRisk, setCustomerRisk] =
    useState<CustomerRiskResponse | null>(null)

  const [customerRiskLoading, setCustomerRiskLoading] =
    useState(false)

  const [customerRiskError, setCustomerRiskError] =
    useState<string | null>(null)

  const [customerRiskLimit, setCustomerRiskLimit] =
    useState<5 | 10 | 15>(5)


  function openAskFlowGuard(question = '') {
    setAskFlowGuardPrompt(question)
    setAskFlowGuardOpen(true)
  }

  async function loadOverview() {
    setLoading(true)
    setError(null)

    try {
      const result =
        await getCFOOverview()

      setOverview(result)
      setDatasetLabel('Demo dataset')
      setCurrentImportId(null)
      setLastUpdated(new Date())
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to load FlowGuard data.',
      )
    } finally {
      setLoading(false)
    }
  }


  useEffect(() => {
    void loadOverview()
  }, [])

  useEffect(() => {
    if (!overview) {
      setInvoicePredictions([])
      return
    }

    const asOfDate = overview.as_of_date
    let cancelled = false

    async function loadInvoicePredictions() {
      setInvoiceLoading(true)
      setInvoiceError(null)

      try {
        const result = await getPaymentDelays({
          importId: currentImportId,
          asOfDate,
        })

        if (!cancelled) {
          setInvoicePredictions(
            result.predictions,
          )
        }
      } catch (caught) {
        if (!cancelled) {
          setInvoicePredictions([])

          setInvoiceError(
            caught instanceof Error
              ? caught.message
              : 'Unable to load invoice risk data.',
          )
        }
      } finally {
        if (!cancelled) {
          setInvoiceLoading(false)
        }
      }
    }

    void loadInvoicePredictions()

    return () => {
      cancelled = true
    }
  }, [
    currentImportId,
    overview?.as_of_date,
  ])


  useEffect(() => {
    if (!overview) {
      setCustomerRisk(null)
      return
    }

    const asOfDate = overview.as_of_date
    const openingCashBalance =
      overview.cashflow.opening_cash_balance

    let cancelled = false

    async function loadCustomerRisk() {
      setCustomerRiskLoading(true)
      setCustomerRiskError(null)

      try {
        const result =
          await getCustomerRiskDrilldown({
            importId: currentImportId,
            asOfDate,
            openingCashBalance,
            horizonDays: 90,
            limit: customerRiskLimit,
          })

        if (!cancelled) {
          setCustomerRisk(result)
        }
      } catch (caught) {
        if (!cancelled) {
          setCustomerRisk(null)
          setCustomerRiskError(
            caught instanceof Error
              ? caught.message
              : 'Unable to load customer risk intelligence.',
          )
        }
      } finally {
        if (!cancelled) {
          setCustomerRiskLoading(false)
        }
      }
    }

    void loadCustomerRisk()

    return () => {
      cancelled = true
    }
  }, [
    currentImportId,
    customerRiskLimit,
    overview?.as_of_date,
    overview?.cashflow.opening_cash_balance,
  ])


  const highRiskInvoices = useMemo(() => {
    const threshold =
      overview?.receivables.high_risk_threshold_pct ?? 70

    return invoicePredictions
      .filter(
        (invoice) =>
          invoice.late_probability >= threshold,
      )
      .sort(
        (a, b) =>
          b.late_probability - a.late_probability ||
          Number(b.outstanding_amount) -
            Number(a.outstanding_amount),
      )
      .slice(0, 10)
  }, [
    invoicePredictions,
    overview?.receivables.high_risk_threshold_pct,
  ])


  const cashflowData = useMemo(
    () => {
      if (!overview) {
        return []
      }

      return [
        {
          name: 'Opening',
          amount: Number(
            overview.cashflow
              .opening_cash_balance,
          ),
        },
        {
          name: 'Inflows',
          amount: Number(
            overview.cashflow
              .total_expected_inflows,
          ),
        },
        {
          name: 'Outflows',
          amount: Number(
            overview.cashflow
              .total_scheduled_outflows,
          ),
        },
        {
          name: 'Projected',
          amount: Number(
            overview.cashflow
              .projected_ending_balance,
          ),
        },
      ]
    },
    [overview],
  )


  if (loading && !overview) {
    return <LoadingScreen />
  }


  if (!overview) {
    return (
      <main className="state-screen">
        <div className="state-logo error-logo">
          <AlertTriangle size={24} />
        </div>

        <h1>Backend unavailable</h1>

        <p>
          {error ??
            'FlowGuard could not load finance intelligence.'}
        </p>

        <button
          className="primary-button"
          onClick={() => void loadOverview()}
        >
          <RefreshCw size={17} />
          Try again
        </button>
      </main>
    )
  }


  const reconciliation =
    overview.reconciliation

  const receivables =
    overview.receivables

  const cashflow =
    overview.cashflow

  const liquidity =
    overview.liquidity_risk

  const exactRate =
    reconciliation.cases_processed
      ? (
          reconciliation.exact_match_cases /
          reconciliation.cases_processed
        ) * 100
      : 0

  const fuzzyRate =
    reconciliation.cases_processed
      ? (
          reconciliation.fuzzy_recovery_cases /
          reconciliation.cases_processed
        ) * 100
      : 0


  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={20} />
          </div>

          <div>
            <strong>FlowGuard</strong>
            <span>AI Finance Control</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <button
            className="nav-item active"
            onClick={() =>
              scrollToSection('overview')
            }
          >
            <LayoutDashboard size={18} />
            Overview
          </button>

          <button
            className="nav-item"
            onClick={() =>
              scrollToSection('reconciliation')
            }
          >
            <ReceiptText size={18} />
            Reconciliation
          </button>

          <button
            className="nav-item"
            onClick={() =>
              scrollToSection('receivables')
            }
          >
            <TrendingUp size={18} />
            Receivables
          </button>

          <button
            className="nav-item"
            onClick={() =>
              scrollToSection('cashflow')
            }
          >
            <WalletCards size={18} />
            Cashflow
          </button>

          <button
            className="nav-item"
            onClick={() =>
              scrollToSection('upload')
            }
          >
            <UploadCloud size={18} />
            Data imports
          </button>
        </nav>

        <div className="sidebar-bottom">
          <button
            className="copilot-button"
            onClick={() => setAskFlowGuardOpen(true)}
          >
            <Sparkles size={17} />
            Ask FlowGuard
            <span>AI</span>
          </button>

          <div className="safe-mode">
            <ShieldCheck size={18} />

            <div>
              <strong>Safe finance mode</strong>
              <span>
                Human review preserved
              </span>
            </div>
          </div>
        </div>
      </aside>


      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">
              Finance Control Center
            </p>

            <h1>
              Operational intelligence,
              <span> in one view.</span>
            </h1>
          </div>

          <div className="topbar-actions">
            <div className="dataset-pill">
              <span className="live-dot" />
              {datasetLabel}
            </div>

            <button
              className="secondary-button"
              onClick={() =>
                void loadOverview()
              }
              disabled={loading}
            >
              <RefreshCw
                size={16}
                className={
                  loading
                    ? 'spin'
                    : ''
                }
              />
              Refresh
            </button>

            <button
              className="primary-button"
              onClick={() =>
                setUploadModalOpen(true)
              }
            >
              <UploadCloud size={17} />
              Upload data
            </button>
          </div>
        </header>


        <section
          id="overview"
          className="section-block"
        >
          <div className="section-heading">
            <div>
              <p className="section-kicker">
                Portfolio snapshot
              </p>

              <h2>Today’s finance position</h2>
            </div>

            <div className="as-of">
              <Clock3 size={15} />
              As of {overview.as_of_date}
            </div>
          </div>


          <div className="metric-grid">
            <MetricCard
              icon={<IndianRupee size={20} />}
              label="Projected cash"
              value={formatMoney(
                cashflow.projected_ending_balance,
              )}
              detail={`90-day horizon ending ${cashflow.horizon_end}`}
              tone="blue"
            />

            <MetricCard
              icon={<TrendingUp size={20} />}
              label="High-risk receivables"
              value={formatMoney(
                receivables.high_risk_amount,
              )}
              detail={`${receivables.high_risk_invoices} invoices above ${receivables.high_risk_threshold_pct}% risk`}
              tone="violet"
            />

            <MetricCard
              icon={<AlertTriangle size={20} />}
              label="Review queue"
              value={String(
                reconciliation
                  .requires_review_count,
              )}
              detail={`${reconciliation.requires_review_rate_pct}% of reconciliation cases`}
              tone="amber"
            />

            <MetricCard
              icon={<CheckCircle2 size={20} />}
              label="Auto-closure"
              value={`${reconciliation.auto_closure_rate_pct}%`}
              detail={`${reconciliation.auto_closed_count} cases safely auto-closed`}
              tone="green"
            />
          </div>
        </section>


        <section
          id="cashflow"
          className="dashboard-grid"
        >
          <article className="panel panel-wide">
            <div className="panel-header">
              <div>
                <p className="section-kicker">
                  Cash intelligence
                </p>

                <h3>90-day cash position</h3>
              </div>

              <span
                className={`severity-badge severity-${cashflow.severity.toLowerCase()}`}
              >
                {cashflow.severity} risk
              </span>
            </div>


            <div className="cash-summary">
              <div>
                <span>Expected inflows</span>
                <strong>
                  {formatMoney(
                    cashflow.total_expected_inflows,
                  )}
                </strong>
              </div>

              <div>
                <span>Scheduled outflows</span>
                <strong>
                  {formatMoney(
                    cashflow.total_scheduled_outflows,
                  )}
                </strong>
              </div>

              <div>
                <span>Temporary cash gap</span>
                <strong>
                  {formatMoney(
                    liquidity.maximum_temporary_cash_gap,
                  )}
                </strong>
              </div>
            </div>


            <div className="chart-container">
              <ResponsiveContainer
                width="100%"
                height="100%"
              >
                <BarChart
                  data={cashflowData}
                  margin={{
                    top: 14,
                    right: 8,
                    left: 4,
                    bottom: 0,
                  }}
                >
                  <CartesianGrid
                    strokeDasharray="4 6"
                    vertical={false}
                    stroke="rgba(148,163,184,0.12)"
                  />

                  <XAxis
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{
                      fill: '#8f9bb7',
                      fontSize: 12,
                    }}
                  />

                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    width={72}
                    tick={{
                      fill: '#8f9bb7',
                      fontSize: 11,
                    }}
                    tickFormatter={(value) =>
                      formatMoney(Number(value))
                    }
                  />

                  <Tooltip
                    cursor={{
                      fill:
                        'rgba(108,124,255,0.08)',
                    }}
                  />

                  <Bar
                    dataKey="amount"
                    fill="#7283ff"
                    radius={[8, 8, 2, 2]}
                    maxBarSize={54}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>


            <div className="insight-strip">
              <ShieldCheck size={18} />

              <span>
                {cashflow.recommended_action}
              </span>
            </div>
          </article>


          <article className="panel priority-panel">
            <div className="panel-header">
              <div>
                <p className="section-kicker">
                  Action center
                </p>

                <h3>Priority actions</h3>
              </div>

              <span className="action-count">
                {overview.priorities.length}
              </span>
            </div>


            <div className="priority-list">
              {overview.priorities.map(
                (priority) => (
                  <div
                    key={priority.code}
                    className="priority-item"
                  >
                    <div
                      className={`priority-dot severity-${priority.severity.toLowerCase()}`}
                    />

                    <div>
                      <div className="priority-title-row">
                        <strong>
                          {priority.title}
                        </strong>

                        <span>
                          {priority.severity}
                        </span>
                      </div>

                      <p>
                          {formatFinancialText(
                            priority.detail,
                          )}
                        </p>
                    </div>
                  </div>
                ),
              )}
            </div>
          </article>
        </section>


        <section className="dashboard-grid">
          <article
            id="reconciliation"
            className="panel"
          >
            <div className="panel-header">
              <div>
                <p className="section-kicker">
                  Reconciliation
                </p>

                <h3>Matching health</h3>
              </div>

              <div className="panel-icon">
                <ReceiptText size={18} />
              </div>
            </div>


            <div className="big-number-row">
              <div>
                <strong>
                  {reconciliation
                    .complete_chain_rate_pct}
                  %
                </strong>

                <span>
                  Complete transaction chains
                </span>
              </div>

              <div className="circle-score">
                {reconciliation.cases_processed}
                <small>cases</small>
              </div>
            </div>


            <div className="progress-stack">
              <ProgressRow
                label="Exact matches"
                value={String(
                  reconciliation
                    .exact_match_cases,
                )}
                percentage={exactRate}
              />

              <ProgressRow
                label="Fuzzy recoveries"
                value={String(
                  reconciliation
                    .fuzzy_recovery_cases,
                )}
                percentage={fuzzyRate}
              />

              <ProgressRow
                label="Requires review"
                value={String(
                  reconciliation
                    .requires_review_count,
                )}
                percentage={
                  reconciliation
                    .requires_review_rate_pct
                }
              />
            </div>


            <div className="review-note">
              <ShieldCheck size={17} />

              <p>
                Ambiguous financial cases remain
                in human review instead of being
                force-resolved.
              </p>
            </div>
          </article>


          <article
            id="receivables"
            className="panel"
          >
            <div className="panel-header">
              <div>
                <p className="section-kicker">
                  Receivables intelligence
                </p>

                <h3>Payment risk</h3>
              </div>

              <div className="panel-icon">
                <CircleDollarSign size={18} />
              </div>
            </div>


            <div className="risk-hero">
              <div>
                <span>Open receivables</span>

                <strong>
                  {formatMoney(
                    receivables.amount_at_risk,
                  )}
                </strong>
              </div>

              <div className="risk-count">
                <strong>
                  {receivables.open_invoices}
                </strong>

                <span>open invoices</span>
              </div>
            </div>


            <div className="risk-stat-grid">
              <div>
                <span>
                  Avg. late probability
                </span>

                <strong>
                  {receivables
                    .average_late_probability_pct}
                  %
                </strong>
              </div>

              <div>
                <span>
                  Model confidence
                </span>

                <strong>
                  {receivables
                    .average_prediction_confidence_pct}
                  %
                </strong>
              </div>

              <div>
                <span>
                  Weighted delay
                </span>

                <strong>
                  {liquidity
                    .weighted_average_delay_days}
                  d
                </strong>
              </div>

              <div>
                <span>
                  Reduced liquidity
                </span>

                <strong>
                  {liquidity
                    .days_with_reduced_liquidity}
                  d
                </strong>
              </div>
            </div>


            <div className="invoice-risk-block">
              <div className="invoice-risk-header">
                <div>
                  <span className="invoice-risk-eyebrow">
                    Invoice drill-down
                  </span>

                  <h4>High-risk invoices</h4>

                  <p>
                    Highest predicted late-payment risks
                    from {datasetLabel.toLowerCase()}.
                  </p>
                </div>

                <div className="invoice-risk-total">
                  <strong>
                    {receivables.high_risk_invoices}
                  </strong>
                  <span>high risk</span>
                </div>
              </div>

              {invoiceLoading ? (
                <div className="invoice-table-state">
                  <RefreshCw
                    className="spin"
                    size={17}
                  />
                  Loading invoice intelligence...
                </div>
              ) : invoiceError ? (
                <div className="invoice-table-state error">
                  <AlertTriangle size={17} />
                  {invoiceError}
                </div>
              ) : highRiskInvoices.length === 0 ? (
                <div className="invoice-table-state">
                  <CheckCircle2 size={17} />
                  No high-risk open invoices found.
                </div>
              ) : (
                <>
                  <div className="invoice-table-scroll">
                    <table className="invoice-risk-table">
                      <thead>
                        <tr>
                          <th>Invoice</th>
                          <th>Customer</th>
                          <th>Outstanding</th>
                          <th>Due date</th>
                          <th>Late risk</th>
                          <th>Delay</th>
                          <th>Confidence</th>
                          <th>Ask AI</th>
                        </tr>
                      </thead>

                      <tbody>
                        {highRiskInvoices.map(
                          (invoice) => (
                            <tr key={invoice.invoice_id}>
                              <td>
                                <strong>
                                  {invoice.invoice_id}
                                </strong>
                              </td>

                              <td>
                                {invoice.customer_id}
                              </td>

                              <td>
                                {formatMoney(
                                  invoice.outstanding_amount,
                                )}
                              </td>

                              <td>
                                {invoice.due_date}
                              </td>

                              <td>
                                <span
                                  className={`invoice-risk-pill ${
                                    invoice.late_probability >= 85
                                      ? 'critical'
                                      : 'high'
                                  }`}
                                >
                                  {invoice.late_probability.toFixed(
                                    2,
                                  )}
                                  %
                                </span>
                              </td>

                              <td>
                                {invoice.expected_delay_days}d
                              </td>

                              <td>
                                {invoice.confidence.toFixed(
                                  2,
                                )}
                                %
                              </td>

                              <td>
                                <button
                                  type="button"
                                  className="table-ai-action"
                                  onClick={() =>
                                    openAskFlowGuard(
                                      `Tell me about ${invoice.invoice_id}`,
                                    )
                                  }
                                >
                                  <Sparkles size={14} />
                                  Ask
                                </button>
                              </td>
                            </tr>
                          ),
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="invoice-table-footer">
                    <span>
                      Showing up to 10 highest-risk
                      open invoices.
                    </span>

                    <button
                      type="button"
                      onClick={() =>
                        setAskFlowGuardOpen(true)
                      }
                    >
                      <Sparkles size={15} />
                      Ask FlowGuard
                    </button>
                  </div>
                </>
              )}
            </div>


            <div className="customer-risk-block">
              <div className="customer-risk-header">
                <div>
                  <span className="invoice-risk-eyebrow">
                    Customer cashflow intelligence
                  </span>

                  <h4>Customers affecting liquidity</h4>

                  <p>
                    Ranked by actual cashflow impact,
                    not simply invoice value.
                  </p>
                </div>

                <div className="customer-limit-selector">
                  {[5, 10, 15].map((limit) => (
                    <button
                      key={limit}
                      type="button"
                      className={
                        customerRiskLimit === limit
                          ? 'active'
                          : ''
                      }
                      onClick={() =>
                        setCustomerRiskLimit(
                          limit as 5 | 10 | 15,
                        )
                      }
                    >
                      Top {limit}
                    </button>
                  ))}
                </div>
              </div>

              {customerRiskLoading ? (
                <div className="invoice-table-state">
                  <RefreshCw
                    className="spin"
                    size={17}
                  />
                  Calculating customer cashflow impact...
                </div>
              ) : customerRiskError ? (
                <div className="invoice-table-state error">
                  <AlertTriangle size={17} />
                  {customerRiskError}
                </div>
              ) : customerRisk ? (
                <>
                  {customerRisk.combined_impact && (
                    <div className="combined-impact-grid">
                      <div>
                        <span>Combined outstanding</span>
                        <strong>
                          {formatMoney(
                            customerRisk.combined_impact
                              .combined_outstanding,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>Delayed exposure</span>
                        <strong>
                          {formatMoney(
                            customerRisk.combined_impact
                              .combined_delayed_exposure,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>Maximum cash gap</span>
                        <strong>
                          {formatMoney(
                            customerRisk.combined_impact
                              .maximum_temporary_cash_gap,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>Reduced liquidity</span>
                        <strong>
                          {
                            customerRisk.combined_impact
                              .days_with_reduced_liquidity
                          }
                          d
                        </strong>
                      </div>

                      <div>
                        <span>Extra shortfall</span>
                        <strong>
                          {formatMoney(
                            customerRisk.combined_impact
                              .incremental_shortfall,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>Combined severity</span>
                        <strong
                          className={`customer-severity ${
                            customerRisk.combined_impact
                              .severity.toLowerCase()
                          }`}
                        >
                          {
                            customerRisk.combined_impact
                              .severity
                          }
                        </strong>
                      </div>
                    </div>
                  )}

                  <div className="customer-ranking-meta">
                    <span>
                      Evaluated{' '}
                      {customerRisk.customer_count_evaluated}{' '}
                      customers
                    </span>

                    <span>
                      Ranking:{' '}
                      {customerRisk.ranking_basis
                        .replaceAll('_', ' ')}
                    </span>
                  </div>

                  <div className="invoice-table-scroll">
                    <table className="customer-risk-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Customer</th>
                          <th>Outstanding</th>
                          <th>Delayed exposure</th>
                          <th>Max cash gap</th>
                          <th>Liquidity</th>
                          <th>Severity</th>
                          <th>Ask AI</th>
                        </tr>
                      </thead>

                      <tbody>
                        {customerRisk.customers.map(
                          (customer) => (
                            <tr key={customer.customer_id}>
                              <td>
                                <strong>
                                  #{customer.rank}
                                </strong>
                              </td>

                              <td>
                                <div className="customer-cell">
                                  <strong>
                                    {customer.customer_name ||
                                      customer.customer_id}
                                  </strong>
                                  <span>
                                    {customer.customer_id}
                                  </span>
                                </div>
                              </td>

                              <td>
                                {formatMoney(
                                  customer.total_outstanding,
                                )}
                              </td>

                              <td>
                                {formatMoney(
                                  customer
                                    .predicted_delayed_exposure,
                                )}
                              </td>

                              <td>
                                {formatMoney(
                                  customer
                                    .maximum_temporary_cash_gap,
                                )}
                              </td>

                              <td>
                                {
                                  customer
                                    .days_with_reduced_liquidity
                                }
                                d
                              </td>

                              <td>
                                <span
                                  className={`customer-severity ${
                                    customer.severity.toLowerCase()
                                  }`}
                                >
                                  {customer.severity}
                                </span>
                              </td>

                              <td>
                                <button
                                  type="button"
                                  className="table-ai-action"
                                  onClick={() =>
                                    openAskFlowGuard(
                                      `How does ${customer.customer_id} affect my cashflow?`,
                                    )
                                  }
                                >
                                  <Sparkles size={14} />
                                  Ask
                                </button>
                              </td>
                            </tr>
                          ),
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="invoice-table-footer">
                    <span>
                      Combined impact is simulated on one
                      cashflow timeline — individual gaps are
                      not simply added.
                    </span>

                    <button
                      type="button"
                      onClick={() =>
                        setAskFlowGuardOpen(true)
                      }
                    >
                      <Sparkles size={15} />
                      Ask about customers
                    </button>
                  </div>
                </>
              ) : null}
            </div>


            <div className="model-note">
              <Sparkles size={17} />

              <div>
                <strong>
                  Prediction is advisory
                </strong>

                <p>
                  Confidence is surfaced explicitly.
                  Predictive signals do not override
                  deterministic finance controls.
                </p>
              </div>
            </div>
          </article>
        </section>


        <section
          id="upload"
          className="upload-panel"
        >
          <div className="upload-copy">
            <div className="upload-icon">
              <Database size={24} />
            </div>

            <div>
              <p className="section-kicker">
                Bring your own finance data
              </p>

              <h2>
                Analyze your operational CSVs
              </h2>

              <p>
                FlowGuard validates, normalizes and
                isolates every import before analysis.
                Your bundled demo dataset is never
                overwritten.
              </p>
            </div>
          </div>


          <div className="upload-files">
            <span>Invoices</span>
            <span>Payments</span>
            <span>Settlements</span>
            <span>Bank transactions</span>
            <span>Customers</span>
            <span>Expenses</span>

            <span className="optional-file">
              Refunds · optional
            </span>

            <span className="optional-file">
              Chargebacks · optional
            </span>
          </div>


          <button className="primary-button upload-action"
            onClick={() =>
              setUploadModalOpen(true)
            }>
            <UploadCloud size={18} />
            Upload company data
          </button>
        </section>


        <footer className="footer">
          <div>
            <ShieldCheck size={15} />
            Operational view · benchmark labels excluded
          </div>

          <span>
            {lastUpdated
              ? `Updated ${lastUpdated.toLocaleTimeString()}`
              : 'Connected'}
          </span>
        </footer>
      </main>

    <UploadDataModal
      open={uploadModalOpen}
      onClose={() =>
        setUploadModalOpen(false)
      }
      onAnalysis={(analysis, manifest) => {
        setOverview(analysis)
        setDatasetLabel('Uploaded dataset')
        setCurrentImportId(manifest.import_id)
        setLastUpdated(new Date())
        setError(null)

        window.scrollTo({
          top: 0,
          behavior: 'smooth',
        })
      }}
    />

    <AskFlowGuardPanel
      open={askFlowGuardOpen}
      onClose={() => setAskFlowGuardOpen(false)}
      asOfDate={overview.as_of_date}
      openingCashBalance={cashflow.opening_cash_balance}
      horizonDays={90}
      importId={currentImportId}
      initialQuestion={askFlowGuardPrompt}
    />
    </div>
  )
}

export default App
