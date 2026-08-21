from __future__ import annotations

import json
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

from backend.app.ingestion.contracts import CONTRACTS
from backend.app.ingestion.schemas import (
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
