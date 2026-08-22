export type PriorityAction = {
  code: string
  severity: string
  title: string
  detail: string
}

export type CFOOverview = {
  as_of_date: string

  reconciliation: {
    cases_processed: number
    complete_chain_count: number
    complete_chain_rate_pct: number
    auto_closed_count: number
    auto_closure_rate_pct: number
    requires_review_count: number
    requires_review_rate_pct: number
    exact_match_cases: number
    fuzzy_recovery_cases: number
    unresolved_or_review_count: number
  }

  receivables: {
    open_invoices: number
    amount_at_risk: string
    high_risk_threshold_pct: number
    high_risk_invoices: number
    high_risk_amount: string
    average_late_probability_pct: number
    average_prediction_confidence_pct: number
  }

  cashflow: {
    opening_cash_balance: string
    horizon_end: string
    total_expected_inflows: string
    total_scheduled_outflows: string
    projected_ending_balance: string
    shortfall_detected: boolean
    first_shortfall_date: string | null
    maximum_shortfall: string
    minimum_projected_balance: string
    severity: string
    recommended_action: string
  }

  liquidity_risk: {
    total_delayed_receivables: string
    weighted_average_delay_days: number
    maximum_temporary_cash_gap: string
    maximum_gap_date: string
    days_with_reduced_liquidity: number
    cash_delayed_by_first_expense: string
    incremental_shortfall: string
    severity: string
  }

  priorities: PriorityAction[]
}

export async function getCFOOverview(): Promise<CFOOverview> {
  const response = await fetch(
    '/api/v1/intelligence/overview?opening_cash_balance=500000.00&horizon_days=90'
  )

  if (!response.ok) {
    throw new Error(`FlowGuard API error: ${response.status}`)
  }

  return response.json()
}
