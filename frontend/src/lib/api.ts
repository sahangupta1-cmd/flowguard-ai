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
