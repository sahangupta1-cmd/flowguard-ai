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

export type PaymentDelayPrediction = {
  invoice_id: string
  customer_id: string
  invoice_amount: string
  outstanding_amount: string
  due_date: string
  expected_delay_days: number
  expected_payment_date: string
  late_probability: number
  confidence: number
  history_count: number
  prediction_basis: string
  amount_at_risk: string
}

export type PaymentDelayListResponse = {
  as_of_date: string
  count: number
  predictions: PaymentDelayPrediction[]
}

export async function getPaymentDelays(options: {
  importId?: string | null
  asOfDate: string
}): Promise<PaymentDelayListResponse> {
  const url = options.importId
    ? `/api/v1/imports/${encodeURIComponent(
        options.importId
      )}/payment-delays?as_of_date=${encodeURIComponent(
        options.asOfDate
      )}`
    : '/api/v1/payment-delays'

  const response = await fetch(url)

  if (!response.ok) {
    throw new Error(
      `Payment-delay API error: ${response.status}`
    )
  }

  return response.json()
}


export type ImportDatasetResponse = {
  dataset_type: string
  normalized_filename: string
  row_count: number
  alias_mappings: Record<string, string>
  extra_columns: string[]
  sha256: string
}

export type ImportSafetyResponse = {
  demo_dataset_modified: boolean
  benchmark_fields_allowed: boolean
  invalid_money_coerced_to_zero: boolean
}

export type ImportManifestResponse = {
  import_id: string
  created_at_utc: string
  fingerprint: string
  total_rows: number
  datasets: ImportDatasetResponse[]
  safety: ImportSafetyResponse
}

export type OperationalUploadFiles = {
  customers: File
  invoices: File
  payments: File
  settlements: File
  bank_transactions: File
  expenses: File
  refunds?: File | null
  chargebacks?: File | null
}

export type ImportAnalysisRequest = {
  as_of_date: string
  opening_cash_balance: string
  horizon_days: number
}

export type ImportAnalysisResponse = {
  import_id: string
  fingerprint: string
  analysis: CFOOverview
}

async function apiErrorMessage(
  response: Response,
): Promise<string> {
  try {
    const payload = await response.json()

    if (
      payload &&
      typeof payload.detail === 'string'
    ) {
      return payload.detail
    }
  } catch {
    // Fall back to the HTTP status below.
  }

  return `FlowGuard API error: ${response.status}`
}

export async function uploadOperationalData(
  files: OperationalUploadFiles,
): Promise<ImportManifestResponse> {
  const formData = new FormData()

  formData.append('customers', files.customers)
  formData.append('invoices', files.invoices)
  formData.append('payments', files.payments)
  formData.append('settlements', files.settlements)
  formData.append(
    'bank_transactions',
    files.bank_transactions,
  )
  formData.append('expenses', files.expenses)

  if (files.refunds) {
    formData.append('refunds', files.refunds)
  }

  if (files.chargebacks) {
    formData.append(
      'chargebacks',
      files.chargebacks,
    )
  }

  const response = await fetch(
    '/api/v1/imports',
    {
      method: 'POST',
      body: formData,
    },
  )

  if (!response.ok) {
    throw new Error(
      await apiErrorMessage(response),
    )
  }

  return response.json()
}

export async function analyzeImport(
  importId: string,
  request: ImportAnalysisRequest,
): Promise<ImportAnalysisResponse> {
  const response = await fetch(
    `/api/v1/imports/${encodeURIComponent(
      importId,
    )}/analyze`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
  )

  if (!response.ok) {
    throw new Error(
      await apiErrorMessage(response),
    )
  }

  return response.json()
}

// -----------------------------------------------------------------------------
// Customer risk / cashflow drill-down
// -----------------------------------------------------------------------------

export type CustomerRiskItem = {
  rank: number
  customer_id: string
  customer_name: string
  industry?: string
  payment_terms_days?: string

  open_invoices: number
  high_risk_invoices: number

  total_outstanding: string
  predicted_delayed_exposure: string

  weighted_late_probability_pct: number
  weighted_expected_delay_days: number
  average_prediction_confidence_pct: number

  maximum_temporary_cash_gap: string
  maximum_gap_date: string | null
  days_with_reduced_liquidity: number
  incremental_shortfall: string

  severity: string
  risk_level?: string

  invoice_ids: string[]
  delayed_invoice_ids: string[]
}

export type CombinedCustomerImpact = {
  customer_ids: string[]
  customer_count: number

  combined_outstanding: string
  combined_delayed_exposure: string

  weighted_expected_delay_days: number

  maximum_temporary_cash_gap: string
  maximum_gap_date: string | null
  days_with_reduced_liquidity: number

  baseline_minimum_balance: string
  combined_delay_minimum_balance: string
  minimum_balance_deterioration: string

  baseline_shortfall: string
  combined_delay_shortfall: string
  incremental_shortfall: string

  severity: string
  horizon_days: number
}

export type CustomerRiskResponse = {
  source_type: string
  import_id: string | null
  as_of_date: string

  ranking_basis: string
  customer_count_evaluated: number
  customer_count_returned: number

  customers: CustomerRiskItem[]
  combined_impact: CombinedCustomerImpact | null
}

export async function getCustomerRiskDrilldown(options: {
  importId?: string | null
  asOfDate: string
  openingCashBalance: string
  horizonDays?: number
  limit?: number
}): Promise<CustomerRiskResponse> {
  const params = new URLSearchParams({
    as_of_date: options.asOfDate,
    opening_cash_balance: options.openingCashBalance,
    horizon_days: String(options.horizonDays ?? 90),
    limit: String(options.limit ?? 5),
  })

  if (options.importId) {
    params.set('import_id', options.importId)
  }

  const response = await fetch(
    `/api/v1/drilldown/customer-risk?${params.toString()}`,
  )

  if (!response.ok) {
    throw new Error(
      await apiErrorMessage(response),
    )
  }

  return response.json()
}


// -----------------------------------------------------------------------------
// Ask FlowGuard AI
// -----------------------------------------------------------------------------

export type AskFlowGuardRequest = {
  question: string
  as_of_date: string
  opening_cash_balance: string
  horizon_days: number
  import_id?: string | null
}

export type AskFlowGuardEvidence = {
  evidence_id: string
  value: string | number | boolean | null
  unit?: string | null
  label?: string | null
}

export type AskFlowGuardAction = {
  action: string
  rationale?: string
  priority?: string
}

export type AskFlowGuardSafety = {
  grounded: boolean
  numeric_claims_validated: boolean
  evidence_references_validated: boolean
  unsupported_claims_detected: number
  benchmark_data_accessed: boolean
  human_review_preserved: boolean
}

export type AskFlowGuardResponse = {
  answer: string
  risk_level: string
  confidence: string
  safety_state: string
  evidence: AskFlowGuardEvidence[]
  recommended_actions: AskFlowGuardAction[]
  safety: AskFlowGuardSafety
}

export async function askFlowGuard(
  request: AskFlowGuardRequest,
): Promise<AskFlowGuardResponse> {
  const response = await fetch('/api/v1/ai/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error(
      await apiErrorMessage(response),
    )
  }

  return response.json()
}
