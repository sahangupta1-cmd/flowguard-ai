from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from backend.app.ingestion.contracts import CONTRACTS
from backend.app.ingestion.validator import (
    CSVValidationReport,
    read_and_normalize_csv,
)


# Buildathon-safe upload limit per CSV.
# This is a configurable operational limit, not a model/output value.
MAX_CSV_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class ImportedDataset:
    dataset_type: str
    normalized_filename: str
    row_count: int
    alias_mappings: dict[str, str]
    extra_columns: tuple[str, ...]
    sha256: str


@dataclass(frozen=True)
class ImportResult:
    import_id: str
    import_path: str
    normalized_path: str
    manifest_path: str
    total_rows: int
    fingerprint: str
    datasets: tuple[ImportedDataset, ...]

    def to_dict(self) -> dict:
        return {
            "import_id": self.import_id,
            "import_path": self.import_path,
            "normalized_path": self.normalized_path,
            "manifest_path": self.manifest_path,
            "total_rows": self.total_rows,
            "fingerprint": self.fingerprint,
            "datasets": [
                asdict(dataset)
                for dataset in self.datasets
            ],
        }


class CSVImportService:
    """
    Validate and normalize external operational CSV datasets.

    Safety properties:
    - Never writes to data/raw.
    - Validates the complete dataset before persistence.
    - Rejects benchmark/evaluation leakage through the validator.
    - Uses canonical FlowGuard column order.
    - Does not silently repair invalid finance values.
    - Creates an isolated import directory.
    - Generates SHA-256 fingerprints for reproducibility.
    """

    def __init__(
        self,
        *,
        import_root: str | Path = "data/imports",
    ) -> None:
        self.import_root = Path(import_root)

    @staticmethod
    def _required_dataset_types() -> set[str]:
        return {
            name
            for name, contract in CONTRACTS.items()
            if not contract.optional
        }

    @staticmethod
    def _validate_source_file(
        dataset_type: str,
        path: Path,
    ) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"{dataset_type}: file not found: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"{dataset_type}: source is not a file: {path}"
            )

        if path.suffix.lower() != ".csv":
            raise ValueError(
                f"{dataset_type}: only CSV files are supported."
            )

        size = path.stat().st_size

        if size <= 0:
            raise ValueError(
                f"{dataset_type}: CSV file is empty."
            )

        if size > MAX_CSV_BYTES:
            raise ValueError(
                f"{dataset_type}: CSV exceeds "
                f"{MAX_CSV_BYTES} byte upload limit."
            )

    def _validate_request(
        self,
        files: Mapping[str, str | Path],
    ) -> dict[str, Path]:
        if not files:
            raise ValueError(
                "No operational CSV files were provided."
            )

        unknown = sorted(
            set(files)
            - set(CONTRACTS)
        )

        if unknown:
            raise ValueError(
                "Unknown dataset types: "
                + ", ".join(unknown)
            )

        missing = sorted(
            self._required_dataset_types()
            - set(files)
        )

        if missing:
            raise ValueError(
                "Missing required operational datasets: "
                + ", ".join(missing)
            )

        resolved: dict[str, Path] = {}

        for dataset_type, source in files.items():
            path = Path(source)

            self._validate_source_file(
                dataset_type,
                path,
            )

            resolved[
                dataset_type
            ] = path

        return resolved

    @staticmethod
    def _serialize_normalized_csv(
        dataset_type: str,
        rows: list[dict[str, str]],
    ) -> bytes:
        contract = CONTRACTS[
            dataset_type
        ]

        buffer = io.StringIO(
            newline=""
        )

        writer = csv.DictWriter(
            buffer,
            fieldnames=list(
                contract.required_columns
            ),
            extrasaction="raise",
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)

        return buffer.getvalue().encode(
            "utf-8"
        )

    @staticmethod
    def _sha256(
        content: bytes,
    ) -> str:
        return hashlib.sha256(
            content
        ).hexdigest()

    @staticmethod
    def _overall_fingerprint(
        hashes: dict[str, str],
    ) -> str:
        material = "\n".join(
            f"{dataset_type}:{hashes[dataset_type]}"
            for dataset_type in sorted(hashes)
        )

        return hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()

    def create_import(
        self,
        files: Mapping[str, str | Path],
    ) -> ImportResult:
        """
        Validate the entire dataset and create one isolated import.

        Nothing is written until every supplied CSV has passed
        header and row validation.
        """

        sources = self._validate_request(
            files
        )

        # ----------------------------------------------------
        # Phase 1: validate everything before writing anything
        # ----------------------------------------------------

        validated: dict[
            str,
            tuple[
                CSVValidationReport,
                list[dict[str, str]],
            ],
        ] = {}

        serialized: dict[
            str,
            bytes,
        ] = {}

        hashes: dict[
            str,
            str,
        ] = {}

        for dataset_type in sorted(sources):
            report, rows = read_and_normalize_csv(
                dataset_type,
                sources[dataset_type],
            )

            content = self._serialize_normalized_csv(
                dataset_type,
                rows,
            )

            validated[
                dataset_type
            ] = (
                report,
                rows,
            )

            serialized[
                dataset_type
            ] = content

            hashes[
                dataset_type
            ] = self._sha256(
                content
            )

        fingerprint = self._overall_fingerprint(
            hashes
        )

        # ----------------------------------------------------
        # Phase 2: persist atomically into an isolated folder
        # ----------------------------------------------------

        import_id = (
            "imp_"
            + uuid.uuid4().hex[:12]
        )

        self.import_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        staging_path = (
            self.import_root
            / f".tmp_{import_id}"
        )

        final_path = (
            self.import_root
            / import_id
        )

        if staging_path.exists():
            shutil.rmtree(
                staging_path
            )

        if final_path.exists():
            raise RuntimeError(
                f"Import ID collision: {import_id}"
            )

        normalized_path = (
            staging_path
            / "normalized"
        )

        normalized_path.mkdir(
            parents=True,
            exist_ok=False,
        )

        imported_datasets: list[
            ImportedDataset
        ] = []

        try:
            for dataset_type in sorted(
                validated
            ):
                report, rows = validated[
                    dataset_type
                ]

                contract = CONTRACTS[
                    dataset_type
                ]

                output_path = (
                    normalized_path
                    / contract.filename
                )

                output_path.write_bytes(
                    serialized[
                        dataset_type
                    ]
                )

                imported_datasets.append(
                    ImportedDataset(
                        dataset_type=dataset_type,
                        normalized_filename=contract.filename,
                        row_count=len(rows),
                        alias_mappings=dict(
                            report.alias_mappings
                        ),
                        extra_columns=tuple(
                            report.extra_columns
                        ),
                        sha256=hashes[
                            dataset_type
                        ],
                    )
                )

            total_rows = sum(
                dataset.row_count
                for dataset in imported_datasets
            )

            manifest = {
                "import_id": import_id,
                "created_at_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "fingerprint": fingerprint,
                "total_rows": total_rows,
                "datasets": [
                    asdict(dataset)
                    for dataset in imported_datasets
                ],
                "safety": {
                    "demo_dataset_modified": False,
                    "benchmark_fields_allowed": False,
                    "invalid_money_coerced_to_zero": False,
                },
            }

            manifest_path = (
                staging_path
                / "manifest.json"
            )

            manifest_path.write_text(
                json.dumps(
                    manifest,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            staging_path.rename(
                final_path
            )

        except Exception:
            if staging_path.exists():
                shutil.rmtree(
                    staging_path
                )

            raise

        return ImportResult(
            import_id=import_id,
            import_path=str(
                final_path
            ),
            normalized_path=str(
                final_path
                / "normalized"
            ),
            manifest_path=str(
                final_path
                / "manifest.json"
            ),
            total_rows=sum(
                dataset.row_count
                for dataset in imported_datasets
            ),
            fingerprint=fingerprint,
            datasets=tuple(
                imported_datasets
            ),
        )
