import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  FileSearch,
  LoaderCircle,
  Send,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  WalletCards,
  X,
} from 'lucide-react'

import {
  askFlowGuard,
  type AskFlowGuardResponse,
} from '../lib/api'

type Props = {
  open: boolean
  onClose: () => void
  asOfDate: string
  openingCashBalance: string
  horizonDays: number
  importId?: string | null
  initialQuestion?: string
}

const SUGGESTIONS = [
  {
    question: 'What should I prioritize today and why?',
    icon: TrendingUp,
  },
  {
    question: 'Which receivables are highest risk?',
    icon: AlertTriangle,
  },
  {
    question: 'Explain my liquidity exposure',
    icon: WalletCards,
  },
  {
    question: 'Why are reconciliation cases under review?',
    icon: FileSearch,
  },
]

function normalisePriority(value?: string) {
  return (value || 'ADVISORY').toUpperCase()
}

export default function AskFlowGuardPanel({
  open,
  onClose,
  asOfDate,
  openingCashBalance,
  horizonDays,
  importId = null,
  initialQuestion = '',
}: Props) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] =
    useState<AskFlowGuardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] =
    useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    const nextQuestion = initialQuestion.trim()

    if (!nextQuestion) {
      return
    }

    setQuestion(nextQuestion)
    setAnswer(null)
    setError(null)
  }, [open, initialQuestion])

  const evidencePreview = useMemo(
    () => answer?.evidence?.slice(0, 5) ?? [],
    [answer],
  )

  if (!open) {
    return null
  }

  async function submitQuestion(
    requestedQuestion?: string,
  ) {
    const finalQuestion =
      (requestedQuestion ?? question).trim()

    if (!finalQuestion || loading) {
      return
    }

    setQuestion(finalQuestion)
    setLoading(true)
    setError(null)

    try {
      const result = await askFlowGuard({
        question: finalQuestion,
        as_of_date: asOfDate,
        opening_cash_balance:
          openingCashBalance,
        horizon_days: horizonDays,
        import_id: importId,
      })

      setAnswer(result)
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Ask FlowGuard could not complete the request.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="ai-drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <aside className="ai-drawer">
        <header className="ai-drawer-header">
          <div className="ai-brand">
            <div className="ai-brand-icon">
              <ShieldCheck size={21} />
            </div>

            <div>
              <strong>Ask FlowGuard</strong>
              <span>Your AI Finance Assistant</span>
            </div>
          </div>

          <div className="ai-header-actions">
            <span className="grounded-badge">
              <CheckCircle2 size={14} />
              Grounded AI
            </span>

            <button
              type="button"
              className="ai-close"
              onClick={onClose}
              aria-label="Close Ask FlowGuard"
            >
              <X size={19} />
            </button>
          </div>
        </header>

        <div className="ai-drawer-body">
          {!answer && (
            <section className="ai-landing">
              <div className="ai-orbit">
                <Sparkles size={28} />
              </div>

              <p className="ai-eyebrow">
                FINANCIAL DECISION SUPPORT
              </p>

              <h2>
                What would you like to understand
                <br />
                about your finances today?
              </h2>

              <p className="ai-subtitle">
                Ask questions about cash flow,
                reconciliation, receivables and
                liquidity using verified finance
                evidence.
              </p>

              <div className="ai-suggestion-grid">
                {SUGGESTIONS.map((item) => {
                  const Icon = item.icon

                  return (
                    <button
                      type="button"
                      key={item.question}
                      onClick={() =>
                        void submitQuestion(
                          item.question,
                        )
                      }
                    >
                      <span>{item.question}</span>

                      <div>
                        <Icon size={19} />
                      </div>
                    </button>
                  )
                })}
              </div>
            </section>
          )}

          {answer && (
            <section className="ai-response">
              <div className="ai-user-question">
                {question}
              </div>

              <article className="ai-answer-card">
                <div className="ai-answer-heading">
                  <div className="ai-avatar">
                    <Bot size={18} />
                  </div>

                  <div>
                    <strong>FlowGuard AI</strong>
                    <span>
                      Grounded finance analysis
                    </span>
                  </div>
                </div>

                <p className="ai-answer-copy">
                  {answer.answer}
                </p>

                <div className="ai-response-meta">
                  <span>
                    Risk
                    <strong>
                      {answer.risk_level}
                    </strong>
                  </span>

                  <span>
                    Confidence
                    <strong>
                      {answer.confidence}
                    </strong>
                  </span>

                  <span>
                    Safety
                    <strong>
                      {answer.safety_state}
                    </strong>
                  </span>
                </div>
              </article>

              <article className="ai-actions-card">
                <div className="ai-section-title">
                  <Sparkles size={17} />
                  <strong>
                    Recommended actions
                  </strong>
                </div>

                <div className="ai-actions-list">
                  {answer.recommended_actions.map(
                    (action, index) => (
                      <div
                        className="ai-action-item"
                        key={`${action.action}-${index}`}
                      >
                        <span className="ai-action-number">
                          {index + 1}
                        </span>

                        <div>
                          <div className="ai-action-title">
                            <strong>
                              {action.action}
                            </strong>

                            <span>
                              {normalisePriority(
                                action.priority,
                              )}
                            </span>
                          </div>

                          {action.rationale && (
                            <p>
                              {action.rationale}
                            </p>
                          )}
                        </div>
                      </div>
                    ),
                  )}
                </div>
              </article>

              <article className="ai-evidence-card">
                <div className="ai-section-title">
                  <ShieldCheck size={17} />
                  <strong>
                    Evidence & validation
                  </strong>
                </div>

                <div className="ai-validation-grid">
                  <div>
                    <CheckCircle2 size={16} />
                    Numeric claims verified
                  </div>

                  <div>
                    <CheckCircle2 size={16} />
                    Evidence references verified
                  </div>

                  <div>
                    <CheckCircle2 size={16} />
                    Human review preserved
                  </div>

                  <div>
                    <CheckCircle2 size={16} />
                    Benchmark data excluded
                  </div>
                </div>

                {evidencePreview.length > 0 && (
                  <div className="ai-evidence-list">
                    {evidencePreview.map(
                      (item, index) => (
                        <div
                          key={`${item.evidence_id}-${index}`}
                        >
                          <span>
                            {item.label ||
                              item.evidence_id}
                          </span>

                          <strong>
                            {String(item.value)}
                            {item.unit
                              ? ` ${item.unit}`
                              : ''}
                          </strong>
                        </div>
                      ),
                    )}
                  </div>
                )}

                <div className="ai-safety-summary">
                  <ShieldCheck size={17} />

                  <span>
                    {answer.safety.grounded
                      ? 'Grounding validation passed.'
                      : 'Answer has validation limitations.'}
                  </span>
                </div>
              </article>

              <button
                type="button"
                className="ai-new-question"
                onClick={() => {
                  setAnswer(null)
                  setQuestion('')
                  setError(null)
                }}
              >
                Ask another question
                <ArrowRight size={16} />
              </button>
            </section>
          )}

          {error && (
            <div className="ai-error">
              <AlertTriangle size={17} />
              <div>
                <strong>Unable to verify this answer safely.</strong>
                <span>
                  FlowGuard did not find enough validated financial
                  evidence for this request. Try asking about invoices,
                  customers, receivables, cashflow, liquidity, or
                  reconciliation.
                </span>
              </div>
            </div>
          )}
        </div>

        <footer className="ai-composer">
          <div className="ai-input-shell">
            <input
              value={question}
              onChange={(event) =>
                setQuestion(event.target.value)
              }
              onKeyDown={(event) => {
                if (
                  event.key === 'Enter' &&
                  !event.shiftKey
                ) {
                  event.preventDefault()
                  void submitQuestion()
                }
              }}
              placeholder="Ask about cash flow, reconciliation, receivables..."
              disabled={loading}
            />

            <button
              type="button"
              onClick={() =>
                void submitQuestion()
              }
              disabled={
                loading || !question.trim()
              }
              aria-label="Ask FlowGuard"
            >
              {loading ? (
                <LoaderCircle
                  size={19}
                  className="spin"
                />
              ) : (
                <Send size={18} />
              )}
            </button>
          </div>

          <p>
            FlowGuard AI is a decision-support
            assistant. Always review before taking
            action.
          </p>
        </footer>
      </aside>
    </div>
  )
}
