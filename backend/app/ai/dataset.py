from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.ai.context import (
    build_evidence_index,
    build_llm_context_payload,
    build_trusted_evidence,
)
from backend.app.ai.guardrails import validate_llm_context_payload
from backend.app.ai.models import (
    AIDataProvenance,
    AskFlowGuardRequest,
    TrustedEvidence,
)
from backend.app.api.schemas import CFOIntelligenceOverviewResponse
from backend.app.ingestion.schemas import ImportManifestResponse
from backend.app.intelligence.service import CFOIntelligenceService


DEFAULT_DEMO_RAW_DIR = Path("data/raw")
DEFAULT_IMPORT_ROOT = Path("data/imports")

IMPORT_ID_PATTERN = re.compile(
    r"^imp_[0-9a-f]{12}$"
)


@dataclass(frozen=True)
class ResolvedAIDataset:
    """
    Internal dataset resolution result.

    raw_dir is server-internal and must never be returned through
    the public Ask FlowGuard API.
    """

    raw_dir: Path

    provenance: AIDataProvenance


@dataclass(frozen=True)
class AIFinanceContext:
    """
    Trusted operational context supplied to Ask FlowGuard.

    The language model receives only the sanitized payload.
    Filesystem paths remain server-side.
    """

    provenance: AIDataProvenance

    overview: CFOIntelligenceOverviewResponse

    evidence: tuple[TrustedEvidence, ...]

    evidence_index: dict[str, TrustedEvidence]

    llm_payload: dict[str, Any]


def _money_string(
    value: Decimal,
) -> str:
    """
    Canonical two-decimal representation used in AI provenance.
    """

    return format(
        value,
        ".2f",
    )


def _load_import_manifest(
    manifest_path: Path,
) -> ImportManifestResponse:
    """
    Read and strictly validate one operational import manifest.
    """

    try:
        payload = json.loads(
            manifest_path.read_text(
                encoding="utf-8",
            )
        )

        return ImportManifestResponse(
            **payload
        )

    except (
        OSError,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        raise RuntimeError(
            "Operational import manifest is invalid or unreadable."
        ) from exc


def _validate_manifest_safety(
    manifest: ImportManifestResponse,
) -> None:
    """
    Require the same safety guarantees used by the ingestion layer.

    Ask FlowGuard must never operate on an import that claims benchmark
    fields are allowed, that the demo dataset was modified, or that
    invalid financial values were silently converted to zero.
    """

    safety = manifest.safety

    if safety.demo_dataset_modified:
        raise RuntimeError(
            "Unsafe import: bundled demo data was modified."
        )

    if safety.benchmark_fields_allowed:
        raise RuntimeError(
            "Unsafe import: benchmark fields are not permitted "
            "in operational AI context."
        )

    if safety.invalid_money_coerced_to_zero:
        raise RuntimeError(
            "Unsafe import: invalid financial values were "
            "coerced to zero."
        )


def resolve_ai_dataset(
    request: AskFlowGuardRequest,
    *,
    demo_raw_dir: Path = DEFAULT_DEMO_RAW_DIR,
    import_root: Path = DEFAULT_IMPORT_ROOT,
) -> ResolvedAIDataset:
    """
    Resolve the exact operational dataset Ask FlowGuard must use.

    No import ID:
        bundled deterministic demo dataset

    Valid import ID:
        that isolated import's normalized operational dataset

    User-controlled filesystem paths are never accepted.
    """

    if request.import_id is None:
        demo_path = Path(
            demo_raw_dir
        )

        if not demo_path.is_dir():
            raise FileNotFoundError(
                "Bundled operational demo dataset was not found."
            )

        return ResolvedAIDataset(
            raw_dir=demo_path.resolve(),
            provenance=AIDataProvenance(
                source_type="demo",
                as_of_date=request.as_of_date,
                import_id=None,
                fingerprint=None,
                opening_cash_balance=_money_string(
                    request.opening_cash_balance
                ),
                horizon_days=request.horizon_days,
            ),
        )

    import_id = request.import_id

    if not IMPORT_ID_PATTERN.fullmatch(
        import_id
    ):
        raise ValueError(
            "Invalid operational import ID."
        )

    root = Path(
        import_root
    ).resolve()

    import_path = (
        root
        / import_id
    )

    if not import_path.is_dir():
        raise FileNotFoundError(
            "Operational import was not found."
        )

    import_path = import_path.resolve()

    if not import_path.is_relative_to(
        root
    ):
        raise RuntimeError(
            "Unsafe operational import path."
        )

    manifest_path = (
        import_path
        / "manifest.json"
    )

    normalized_path = (
        import_path
        / "normalized"
    )

    if not manifest_path.is_file():
        raise FileNotFoundError(
            "Operational import manifest was not found."
        )

    if not normalized_path.is_dir():
        raise FileNotFoundError(
            "Normalized operational import dataset was not found."
        )

    normalized_real = (
        normalized_path.resolve()
    )

    if not normalized_real.is_relative_to(
        import_path
    ):
        raise RuntimeError(
            "Unsafe normalized operational dataset path."
        )

    manifest = _load_import_manifest(
        manifest_path
    )

    if manifest.import_id != import_id:
        raise RuntimeError(
            "Operational import manifest ID does not match "
            "the requested import."
        )

    _validate_manifest_safety(
        manifest
    )

    return ResolvedAIDataset(
        raw_dir=normalized_real,
        provenance=AIDataProvenance(
            source_type="uploaded_import",
            as_of_date=request.as_of_date,
            import_id=manifest.import_id,
            fingerprint=manifest.fingerprint,
            opening_cash_balance=_money_string(
                request.opening_cash_balance
            ),
            horizon_days=request.horizon_days,
        ),
    )


def build_ai_finance_context(
    request: AskFlowGuardRequest,
    *,
    demo_raw_dir: Path = DEFAULT_DEMO_RAW_DIR,
    import_root: Path = DEFAULT_IMPORT_ROOT,
) -> AIFinanceContext:
    """
    Build the complete trusted finance context for one AI request.

    FlowGuard reconstructs finance intelligence server-side rather than
    trusting financial numbers supplied by the browser.
    """

    resolved = resolve_ai_dataset(
        request,
        demo_raw_dir=demo_raw_dir,
        import_root=import_root,
    )

    intelligence = CFOIntelligenceService(
        raw_dir=resolved.raw_dir,
        as_of_date=request.as_of_date,
    )

    overview_dict = intelligence.build_overview(
        opening_cash_balance=(
            request.opening_cash_balance
        ),
        horizon_days=request.horizon_days,
    )

    overview = CFOIntelligenceOverviewResponse(
        **overview_dict
    )

    evidence_list = build_trusted_evidence(
        overview
    )

    evidence_index = build_evidence_index(
        evidence_list
    )

    llm_payload = build_llm_context_payload(
        provenance=resolved.provenance,
        evidence=evidence_list,
    )

    # Defense in depth immediately before anything can be sent
    # across the future model-provider boundary.
    validate_llm_context_payload(
        llm_payload
    )

    return AIFinanceContext(
        provenance=resolved.provenance,
        overview=overview,
        evidence=tuple(
            evidence_list
        ),
        evidence_index=evidence_index,
        llm_payload=llm_payload,
    )
