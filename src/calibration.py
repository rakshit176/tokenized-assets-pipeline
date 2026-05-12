"""Confidence calibration for extracted data.

Improves confidence scores based on:
- Source reliability patterns
- Field-specific accuracy history
- Cross-validation consistency
- Extraction method reliability
"""
import logging
from typing import Any
from collections import defaultdict

logger = logging.getLogger(__name__)


# Source reliability scores (based on historical accuracy)
SOURCE_RELIABILITY = {
    # Direct company sources (highest reliability)
    "company website": 1.0,
    "official docs": 0.95,
    "api documentation": 0.95,

    # High-quality third-party (good but may be outdated)
    "wikipedia": 0.85,
    "crunchbase": 0.85,
    "linkedin": 0.80,
    "pitchbook": 0.85,

    # News sources (variable reliability)
    "techcrunch": 0.75,
    "bloomberg": 0.80,
    "reuters": 0.80,
    "coindesk": 0.75,
    "the block": 0.75,

    # Aggregated/search (lower reliability)
    "google search": 0.65,
    "search results": 0.60,
    "unknown": 0.50,
}


# Extraction method reliability
METHOD_RELIABILITY = {
    "direct_match": 1.0,      # Exact string match in page
    "structured_data": 0.95,  # From structured JSON/API
    "llm_primary": 0.85,       # LLM extraction from primary source
    "llm_secondary": 0.70,    # LLM from secondary source
    "llm_knowledge": 0.50,     # LLM internal knowledge only
}


def get_source_reliability(url: str | None, context: str = "") -> float:
    """Determine source reliability score from URL or context.

    Args:
        url: Source URL
        context: Additional context about the source

    Returns:
        Reliability score between 0 and 1
    """
    if not url:
        return SOURCE_RELIABILITY.get("unknown", 0.5)

    url_lower = url.lower()
    context_lower = context.lower()

    # Check for company website (domain match)
    if context and context.lower() in url_lower:
        return SOURCE_RELIABILITY.get("company website", 1.0)

    # Check known patterns
    patterns = {
        "wikipedia.org": "wikipedia",
        "crunchbase.com": "crunchbase",
        "linkedin.com": "linkedin",
        "pitchbook.com": "pitchbook",
        "techcrunch.com": "techcrunch",
        "bloomberg.com": "bloomberg",
        "reuters.com": "reuters",
        "coindesk.com": "coindesk",
        "theblock.co": "the block",
        "docs.": "api documentation",
        "developer.": "api documentation",
    }

    for pattern, source in patterns.items():
        if pattern in url_lower:
            return SOURCE_RELIABILITY.get(source, 0.7)

    return SOURCE_RELIABILITY.get("unknown", 0.5)


def calibrate_confidence(
    value: Any,
    source_url: str | None,
    base_confidence: float,
    extraction_method: str = "llm_primary",
    field_name: str = "",
) -> float:
    """Calibrate confidence score based on multiple factors.

    Args:
        value: The extracted value
        source_url: URL where value was found
        base_confidence: Original confidence from LLM
        extraction_method: How the value was extracted
        field_name: Name of the field (for field-specific adjustment)

    Returns:
        Calibrated confidence score between 0 and 1
    """
    if value is None or str(value).strip() in ["", "null", "N/A", "Unknown"]:
        return 0.0

    # Start with base confidence
    calibrated = base_confidence

    # Adjust by source reliability
    source_reliability = get_source_reliability(source_url, field_name)
    calibrated = (calibrated + source_reliability) / 2

    # Adjust by extraction method
    method_score = METHOD_RELIABILITY.get(extraction_method, 0.7)
    calibrated = (calibrated + method_score) / 2

    # Field-specific adjustments
    calibrated = _apply_field_adjustments(calibrated, field_name, value)

    # Ensure within bounds
    return max(0.0, min(1.0, calibrated))


def _apply_field_adjustments(confidence: float, field_name: str, value: Any) -> float:
    """Apply field-specific confidence adjustments."""
    field_lower = field_name.lower().replace("_", "")

    # Company name and domain should be very high confidence if found
    if "name" in field_lower or "domain" in field_lower:
        if confidence > 0.7:
            return min(1.0, confidence + 0.1)

    # URLs should have high confidence if format is valid
    if "url" in field_lower or "website" in field_lower:
        if str(value).startswith(("http://", "https://")):
            return min(0.95, confidence + 0.1)

    # Founding year decreases confidence if outside reasonable range
    if "year" in field_lower or "founded" in field_lower:
        try:
            year = int(str(value).replace(":", "").replace("-", "").strip())
            if year < 2000 or year > 2026:
                return max(0.3, confidence - 0.2)
        except (ValueError, TypeError):
            pass

    # Boolean fields should be high confidence if clearly stated
    if field_lower.startswith("is_") or field_lower.startswith("has_"):
        if isinstance(value, bool) or str(value).lower() in ["true", "false"]:
            return min(0.95, confidence + 0.1)

    return confidence


def calibrate_company_data(data: dict) -> dict:
    """Calibrate all confidence scores in extracted data.

    Args:
        data: Extracted company data dictionary

    Returns:
        Same data with calibrated confidence scores
    """
    for table_name, table_data in data.items():
        if not isinstance(table_data, dict):
            continue

        if "rows" in table_data:
            # Repeating table
            for row in table_data["rows"]:
                _calibrate_row(row, table_name)
        else:
            # Single-row table
            _calibrate_row(table_data, table_name)

    return data


def _calibrate_row(row: dict, table_name: str) -> None:
    """Calibrate confidence scores in a single row."""
    for field_name, field_value in row.items():
        if not isinstance(field_value, dict):
            continue

        if "value" not in field_value:
            continue

        # Get source URL and base confidence
        source_url = field_value.get("source_url")
        base_confidence = field_value.get("confidence", 0.5)

        # Determine extraction method from context
        extraction_method = "llm_primary"
        if base_confidence > 0.9:
            extraction_method = "direct_match"
        elif base_confidence < 0.5:
            extraction_method = "llm_knowledge"

        # Calibrate
        calibrated = calibrate_confidence(
            field_value["value"],
            source_url,
            base_confidence,
            extraction_method,
            field_name,
        )

        # Update
        field_value["confidence"] = round(calibrated, 2)


# Calibration statistics tracking
class CalibrationTracker:
    """Tracks accuracy of confidence predictions for calibration improvement."""

    def __init__(self):
        self._predictions: list[tuple[float, bool]] = []  # (confidence, was_correct)
        self._field_accuracy: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        self._source_accuracy: dict[str, list[tuple[float, bool]]] = defaultdict(list)

    def record(self, confidence: float, was_correct: bool, field: str = "", source: str = ""):
        """Record a prediction outcome."""
        self._predictions.append((confidence, was_correct))
        if field:
            self._field_accuracy[field].append((confidence, was_correct))
        if source:
            self._source_accuracy[source].append((confidence, was_correct))

    def get_calibration_stats(self) -> dict:
        """Get calibration statistics.

        Returns:
            Dict with calibration metrics
        """
        if not self._predictions:
            return {"status": "no_data"}

        # Group by confidence buckets
        buckets = {0.1: [], 0.3: [], 0.5: [], 0.7: [], 0.9: []}
        for conf, correct in self._predictions:
            bucket_key = min(buckets.keys(), key=lambda b: abs(b - conf))
            buckets[bucket_key].append(correct)

        bucket_accuracy = {}
        for bucket, outcomes in buckets.items():
            if outcomes:
                bucket_accuracy[f"{bucket:.1f}"] = sum(outcomes) / len(outcomes)

        return {
            "total_predictions": len(self._predictions),
            "overall_accuracy": sum(c for _, c in self._predictions) / len(self._predictions),
            "bucket_accuracy": bucket_accuracy,
        }


_global_tracker: CalibrationTracker | None = None


def get_tracker() -> CalibrationTracker:
    """Get global calibration tracker."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CalibrationTracker()
    return _global_tracker
