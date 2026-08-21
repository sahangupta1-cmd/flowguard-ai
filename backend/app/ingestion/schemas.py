from __future__ import annotations

from pydantic import Field

from backend.app.api.schemas import StrictAPIModel


class ImportDatasetResponse(StrictAPIModel):
    dataset_type: str = Field(
        min_length=1,
    )

    normalized_filename: str = Field(
        min_length=1,
    )

    row_count: int = Field(
        ge=0,
    )

    alias_mappings: dict[str, str] = Field(
        default_factory=dict,
    )

    extra_columns: list[str] = Field(
        default_factory=list,
    )

    sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )


class ImportSafetyResponse(StrictAPIModel):
    demo_dataset_modified: bool
    benchmark_fields_allowed: bool
    invalid_money_coerced_to_zero: bool


class ImportManifestResponse(StrictAPIModel):
    """
    Public operational import response.

    Filesystem paths are intentionally not exposed.
    """

    import_id: str = Field(
        pattern=r"^imp_[0-9a-f]{12}$",
    )

    created_at_utc: str

    fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )

    total_rows: int = Field(
        ge=0,
    )

    datasets: list[ImportDatasetResponse] = Field(
        default_factory=list,
    )

    safety: ImportSafetyResponse
