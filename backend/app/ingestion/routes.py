from __future__ import annotations

import json
from datetime import date
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
    status,
)

from backend.app.api.schemas import (
    PaymentDelayListResponse,
    PaymentDelayResponse,
)

from backend.app.ingestion.contracts import CONTRACTS
from backend.app.intelligence.service import CFOIntelligenceService
from backend.app.prediction.delay_predictor import DelayPredictor
from backend.app.ingestion.schemas import (
    ImportAnalysisRequest,
    ImportAnalysisResponse,
    ImportManifestResponse,
)
from backend.app.ingestion.service import (
    MAX_CSV_BYTES,
    CSVImportService,
)


router = APIRouter()

DEFAULT_IMPORT_ROOT = Path(
    "data/imports"
)

UPLOAD_CHUNK_BYTES = 1024 * 1024

IMPORT_ID_PATTERN = re.compile(
    r"^imp_[0-9a-f]{12}$"
)


async def _save_upload(
    *,
    dataset_type: str,
    upload: UploadFile,
    destination: Path,
) -> None:
    """
    Stream one uploaded CSV to a temporary location.

    The file is not written into data/imports until the complete
    multi-file dataset has passed FlowGuard validation.
    """

    original_filename = (
        upload.filename or ""
    )

    if (
        Path(original_filename).suffix.lower()
        != ".csv"
    ):
        raise ValueError(
            f"{dataset_type}: only CSV files are supported."
        )

    total_bytes = 0

    try:
        with destination.open(
            "wb"
        ) as handle:
            while True:
                chunk = await upload.read(
                    UPLOAD_CHUNK_BYTES
                )

                if not chunk:
                    break

                total_bytes += len(
                    chunk
                )

                if total_bytes > MAX_CSV_BYTES:
                    raise ValueError(
                        f"{dataset_type}: CSV exceeds "
                        f"{MAX_CSV_BYTES} byte upload limit."
                    )

                handle.write(
                    chunk
                )

    finally:
        await upload.close()

    if total_bytes == 0:
        raise ValueError(
            f"{dataset_type}: uploaded CSV is empty."
        )


def _read_manifest(
    manifest_path: Path,
) -> ImportManifestResponse:
    try:
        payload = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            "Import manifest could not be read."
        ) from exc

    return ImportManifestResponse(
        **payload
    )


@router.post(
    "/api/v1/imports",
    response_model=ImportManifestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["imports"],
)
async def create_operational_import(
    customers: UploadFile = File(...),
    invoices: UploadFile = File(...),
    payments: UploadFile = File(...),
    settlements: UploadFile = File(...),
    bank_transactions: UploadFile = File(...),
    expenses: UploadFile = File(...),
    refunds: UploadFile | None = File(None),
    chargebacks: UploadFile | None = File(None),
) -> ImportManifestResponse:
    """
    Validate and create an isolated operational finance import.

    Required datasets:
    customers, invoices, payments, settlements,
    bank_transactions and expenses.

    Refunds and chargebacks are optional.
    """

    uploads: dict[
        str,
        UploadFile | None,
    ] = {
        "customers": customers,
        "invoices": invoices,
        "payments": payments,
        "settlements": settlements,
        "bank_transactions": bank_transactions,
        "expenses": expenses,
        "refunds": refunds,
        "chargebacks": chargebacks,
    }

    try:
        with TemporaryDirectory(
            prefix="flowguard_upload_"
        ) as temporary:
            temporary_path = Path(
                temporary
            )

            source_files: dict[
                str,
                Path,
            ] = {}

            for (
                dataset_type,
                upload,
            ) in uploads.items():
                if upload is None:
                    continue

                contract = CONTRACTS[
                    dataset_type
                ]

                destination = (
                    temporary_path
                    / contract.filename
                )

                await _save_upload(
                    dataset_type=dataset_type,
                    upload=upload,
                    destination=destination,
                )

                source_files[
                    dataset_type
                ] = destination

            service = CSVImportService(
                import_root=DEFAULT_IMPORT_ROOT
            )

            result = service.create_import(
                source_files
            )

        return _read_manifest(
            Path(
                result.manifest_path
            )
        )

    except (
        ValueError,
        FileNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Operational import could not be completed."
            ),
        ) from exc


@router.get(
    "/api/v1/imports/{import_id}",
    response_model=ImportManifestResponse,
    tags=["imports"],
)
def get_operational_import(
    import_id: str,
) -> ImportManifestResponse:
    """
    Return metadata for an existing isolated import.

    Raw filesystem paths are never returned.
    """

    if not IMPORT_ID_PATTERN.fullmatch(
        import_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import not found.",
        )

    manifest_path = (
        DEFAULT_IMPORT_ROOT
        / import_id
        / "manifest.json"
    )

    if not manifest_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import not found.",
        )

    try:
        return _read_manifest(
            manifest_path
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Import metadata could not be read."
            ),
        ) from exc


@router.post(
    "/api/v1/imports/{import_id}/analyze",
    response_model=ImportAnalysisResponse,
    tags=["imports"],
)
def analyze_operational_import(
    import_id: str,
    request: ImportAnalysisRequest,
) -> ImportAnalysisResponse:
    """
    Run FlowGuard CFO intelligence against one isolated import.

    The bundled demo dataset is never replaced or overwritten.
    """

    # Reuse the existing safe import-ID validation and lookup.
    manifest = get_operational_import(
        import_id
    )

    normalized_path = (
        DEFAULT_IMPORT_ROOT
        / import_id
        / "normalized"
    )

    if not normalized_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Imported operational dataset is unavailable "
                "for analysis."
            ),
        )

    try:
        intelligence = CFOIntelligenceService(
            raw_dir=normalized_path,
            as_of_date=request.as_of_date,
        )

        overview = intelligence.build_overview(
            opening_cash_balance=(
                request.opening_cash_balance
            ),
            horizon_days=request.horizon_days,
        )

        return ImportAnalysisResponse(
            import_id=import_id,
            fingerprint=manifest.fingerprint,
            analysis=overview,
        )

    except (
        FileNotFoundError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Imported operational dataset could not "
                "be analyzed."
            ),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Operational intelligence analysis failed."
            ),
        ) from exc


@router.get(
    "/api/v1/imports/{import_id}/payment-delays",
    response_model=PaymentDelayListResponse,
    tags=["imports", "prediction"],
)
def get_import_payment_delays(
    import_id: str,
    as_of_date: date,
) -> PaymentDelayListResponse:
    """
    Predict payment timing for open invoices from one
    isolated uploaded operational dataset.

    The demo dataset is never used for this endpoint.
    """

    # Reuse FlowGuard's existing safe import validation.
    get_operational_import(import_id)

    normalized_path = (
        DEFAULT_IMPORT_ROOT
        / import_id
        / "normalized"
    )

    if not normalized_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Imported operational dataset is unavailable "
                "for payment-delay analysis."
            ),
        )

    try:
        predictor = DelayPredictor(
            raw_dir=normalized_path,
            as_of_date=as_of_date,
        )

        predictions = predictor.predict_open_invoices()

        api_predictions = [
            PaymentDelayResponse(
                **prediction.to_dict()
            )
            for prediction in predictions
        ]

        return PaymentDelayListResponse(
            as_of_date=predictor.as_of_date.isoformat(),
            count=len(api_predictions),
            predictions=api_predictions,
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Imported payment-delay analysis failed."
            ),
        ) from exc
