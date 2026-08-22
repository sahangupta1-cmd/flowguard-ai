import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  LoaderCircle,
  ShieldCheck,
  UploadCloud,
  X,
} from 'lucide-react'

import {
  analyzeImport,
  uploadOperationalData,
  type CFOOverview,
  type ImportManifestResponse,
  type OperationalUploadFiles,
} from '../lib/api'

type DatasetKey =
  | 'customers'
  | 'invoices'
  | 'payments'
  | 'settlements'
  | 'bank_transactions'
  | 'expenses'
  | 'refunds'
  | 'chargebacks'

type DatasetDefinition = {
  key: DatasetKey
  label: string
  required: boolean
}

const DATASETS: DatasetDefinition[] = [
  {
    key: 'customers',
    label: 'Customers',
    required: true,
  },
  {
    key: 'invoices',
    label: 'Invoices',
    required: true,
  },
  {
    key: 'payments',
    label: 'Payments',
    required: true,
  },
  {
    key: 'settlements',
    label: 'Settlements',
    required: true,
  },
  {
    key: 'bank_transactions',
    label: 'Bank transactions',
    required: true,
  },
  {
    key: 'expenses',
    label: 'Expenses',
    required: true,
  },
  {
    key: 'refunds',
    label: 'Refunds',
    required: false,
  },
  {
    key: 'chargebacks',
    label: 'Chargebacks',
    required: false,
  },
]

type Props = {
  open: boolean
  onClose: () => void
  onAnalysis: (
    analysis: CFOOverview,
    manifest: ImportManifestResponse,
  ) => void
}

export default function UploadDataModal({
  open,
  onClose,
  onAnalysis,
}: Props) {
  const [files, setFiles] = useState<
    Partial<Record<DatasetKey, File>>
  >({})

  const [manifest, setManifest] =
    useState<ImportManifestResponse | null>(null)

  const [asOfDate, setAsOfDate] =
    useState('2026-08-01')

  const [
    openingCashBalance,
    setOpeningCashBalance,
  ] = useState('500000.00')

  const [horizonDays, setHorizonDays] =
    useState('90')

  const [uploading, setUploading] =
    useState(false)

  const [analyzing, setAnalyzing] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)

  const requiredReady = useMemo(
    () =>
      DATASETS
        .filter((dataset) => dataset.required)
        .every((dataset) => files[dataset.key]),
    [files],
  )

  useEffect(() => {
    if (!open) {
      return
    }

    function handleEscape(
      event: KeyboardEvent,
    ) {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener(
      'keydown',
      handleEscape,
    )

    return () => {
      window.removeEventListener(
        'keydown',
        handleEscape,
      )
    }
  }, [open, onClose])

  if (!open) {
    return null
  }

  function selectFile(
    key: DatasetKey,
    file: File | undefined,
  ) {
    if (!file) {
      return
    }

    if (
      !file.name
        .toLowerCase()
        .endsWith('.csv')
    ) {
      setError(
        `${file.name} is not a CSV file.`,
      )
      return
    }

    setError(null)

    setFiles((current) => ({
      ...current,
      [key]: file,
    }))
  }

  async function handleImport() {
    if (!requiredReady) {
      setError(
        'Please select all six required CSV datasets.',
      )
      return
    }

    setUploading(true)
    setError(null)

    try {
      const uploadFiles:
        OperationalUploadFiles = {
        customers: files.customers!,
        invoices: files.invoices!,
        payments: files.payments!,
        settlements: files.settlements!,
        bank_transactions:
          files.bank_transactions!,
        expenses: files.expenses!,
        refunds: files.refunds ?? null,
        chargebacks:
          files.chargebacks ?? null,
      }

      const result =
        await uploadOperationalData(
          uploadFiles,
        )

      setManifest(result)
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'The import could not be completed.',
      )
    } finally {
      setUploading(false)
    }
  }

  async function handleAnalyze() {
    if (!manifest) {
      return
    }

    const horizon = Number(horizonDays)
    const balance =
      Number(openingCashBalance)

    if (
      !Number.isFinite(balance) ||
      balance < 0
    ) {
      setError(
        'Opening cash balance must be zero or greater.',
      )
      return
    }

    if (
      !Number.isInteger(horizon) ||
      horizon < 1 ||
      horizon > 365
    ) {
      setError(
        'Forecast horizon must be between 1 and 365 days.',
      )
      return
    }

    setAnalyzing(true)
    setError(null)

    try {
      const result = await analyzeImport(
        manifest.import_id,
        {
          as_of_date: asOfDate,
          opening_cash_balance:
            openingCashBalance,
          horizon_days: horizon,
        },
      )

      onAnalysis(
        result.analysis,
        manifest,
      )

      onClose()
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'The imported dataset could not be analyzed.',
      )
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div
      className="upload-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (
          event.target ===
          event.currentTarget
        ) {
          onClose()
        }
      }}
    >
      <section
        className="upload-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-modal-title"
      >
        <header className="upload-modal-header">
          <div>
            <p className="section-kicker">
              Secure data import
            </p>

            <h2 id="upload-modal-title">
              {manifest
                ? 'Configure analysis'
                : 'Upload company data'}
            </h2>

            <p>
              {manifest
                ? 'Your files passed validation. Configure the finance analysis before continuing.'
                : 'Add your operational CSV exports. FlowGuard validates and isolates every import.'}
            </p>
          </div>

          <button
            type="button"
            className="upload-modal-close"
            onClick={onClose}
            aria-label="Close upload window"
          >
            <X size={18} />
          </button>
        </header>

        {!manifest ? (
          <>
            <div className="upload-dataset-grid">
              {DATASETS.map(
                ({
                  key,
                  label,
                  required,
                }) => {
                  const file = files[key]

                  return (
                    <label
                      key={key}
                      className={
                        file
                          ? 'upload-file-card selected'
                          : 'upload-file-card'
                      }
                    >
                      <input
                        type="file"
                        accept=".csv,text/csv"
                        onChange={(event) =>
                          selectFile(
                            key,
                            event.target
                              .files?.[0],
                          )
                        }
                      />

                      <div className="upload-file-icon">
                        {file ? (
                          <CheckCircle2
                            size={20}
                          />
                        ) : (
                          <FileSpreadsheet
                            size={20}
                          />
                        )}
                      </div>

                      <div className="upload-file-copy">
                        <strong>
                          {label}
                        </strong>

                        <span>
                          {file
                            ? file.name
                            : required
                              ? 'Required CSV'
                              : 'Optional CSV'}
                        </span>
                      </div>

                      <span
                        className={
                          required
                            ? 'file-requirement required'
                            : 'file-requirement optional'
                        }
                      >
                        {required
                          ? 'Required'
                          : 'Optional'}
                      </span>
                    </label>
                  )
                },
              )}
            </div>

            <div className="upload-security-note">
              <ShieldCheck size={18} />

              <div>
                <strong>
                  Safe finance mode
                </strong>

                <span>
                  Demo data remains untouched.
                  Benchmark fields and invalid
                  financial values are rejected.
                </span>
              </div>
            </div>

            {error && (
              <div className="upload-error">
                <AlertTriangle size={17} />
                <span>{error}</span>
              </div>
            )}

            <footer className="upload-modal-footer">
              <span>
                {
                  DATASETS.filter(
                    (item) =>
                      item.required &&
                      files[item.key],
                  ).length
                }
                /6 required datasets selected
              </span>

              <button
                type="button"
                className="primary-button"
                disabled={
                  !requiredReady ||
                  uploading
                }
                onClick={() => {
                  void handleImport()
                }}
              >
                {uploading ? (
                  <>
                    <LoaderCircle
                      size={17}
                      className="spin"
                    />
                    Validating…
                  </>
                ) : (
                  <>
                    <UploadCloud
                      size={17}
                    />
                    Validate & import
                  </>
                )}
              </button>
            </footer>
          </>
        ) : (
          <>
            <div className="import-success-card">
              <CheckCircle2 size={22} />

              <div>
                <strong>
                  Import validated
                </strong>

                <span>
                  {manifest.total_rows}{' '}
                  rows across{' '}
                  {
                    manifest.datasets
                      .length
                  }{' '}
                  datasets
                </span>
              </div>

              <code>
                {manifest.import_id}
              </code>
            </div>

            <div className="analysis-form">
              <label>
                <span>Analysis date</span>

                <input
                  type="date"
                  value={asOfDate}
                  onChange={(event) =>
                    setAsOfDate(
                      event.target.value,
                    )
                  }
                />
              </label>

              <label>
                <span>
                  Opening cash balance
                </span>

                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={
                    openingCashBalance
                  }
                  onChange={(event) =>
                    setOpeningCashBalance(
                      event.target.value,
                    )
                  }
                />
              </label>

              <label>
                <span>
                  Forecast horizon
                </span>

                <div className="input-with-suffix">
                  <input
                    type="number"
                    min="1"
                    max="365"
                    value={horizonDays}
                    onChange={(event) =>
                      setHorizonDays(
                        event.target.value,
                      )
                    }
                  />

                  <span>days</span>
                </div>
              </label>
            </div>

            <div className="import-safety-grid">
              <div>
                <CheckCircle2 size={16} />
                Demo dataset preserved
              </div>

              <div>
                <CheckCircle2 size={16} />
                Benchmark labels excluded
              </div>

              <div>
                <CheckCircle2 size={16} />
                Invalid money rejected
              </div>
            </div>

            {error && (
              <div className="upload-error">
                <AlertTriangle size={17} />
                <span>{error}</span>
              </div>
            )}

            <footer className="upload-modal-footer">
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setManifest(null)
                }
              >
                Back
              </button>

              <button
                type="button"
                className="primary-button"
                disabled={
                  analyzing ||
                  !asOfDate
                }
                onClick={() => {
                  void handleAnalyze()
                }}
              >
                {analyzing ? (
                  <>
                    <LoaderCircle
                      size={17}
                      className="spin"
                    />
                    Analyzing…
                  </>
                ) : (
                  <>
                    Analyze dataset
                    <ArrowRight
                      size={17}
                    />
                  </>
                )}
              </button>
            </footer>
          </>
        )}
      </section>
    </div>
  )
}
