"""OpenAI Structured Outputs integration.

Uses OpenAI's Structured Outputs feature for guaranteed schema compliance.
Requires defining Pydantic models for the expected response structure.

This module provides simplified schemas for key extraction batches.
For full schema support, we'd need to define all 17 tables which is complex.

Fallback: Uses json_object mode which still guarantees valid JSON.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Simplified schema for a single field extraction
SIMPLE_FIELD_SCHEMA = {
    "name": "extracted_field",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "value": {
                "type": ["string", "number", "boolean", "null"],
                "description": "The extracted value"
            },
            "source_url": {
                "type": ["string", "null"],
                "description": "URL where value was found"
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score between 0 and 1"
            }
        },
        "required": ["value", "source_url", "confidence"],
        "additionalProperties": False
    }
}


# Schema for batch extraction (subset of fields for testing)
BATCH_SCHEMA_EXAMPLE = {
    "name": "company_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "companies": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "website": {"type": "string"},
                    "founded_year": {"type": "integer"},
                    "description": {"type": "string"},
                    "hq_country": {"type": "string"},
                    "hq_city": {"type": "string"},
                    "employee_count_range": {"type": "string"},
                },
                "required": ["company_name", "website"],
                "additionalProperties": False
            }
        },
        "required": ["companies"],
        "additionalProperties": False
    }
}


def get_structured_output_response_schema(batch_name: str) -> dict[str, Any] | None:
    """Get the appropriate structured output schema for a batch.

    For now, returns None to use standard json_object mode.
    To enable full structured outputs, define Pydantic models for each batch.

    Args:
        batch_name: Name of the extraction batch

    Returns:
        Structured output schema or None for json_object mode
    """
    # Future: Define proper schemas for each batch
    # For now, use json_object mode which already guarantees valid JSON
    return None


def supports_structured_outputs(provider_name: str) -> bool:
    """Check if a provider supports structured outputs.

    Args:
        provider_name: Name of the LLM provider

    Returns:
        True if provider supports structured outputs
    """
    return provider_name.lower() in ["openai"]


def should_use_structured_outputs(batch_name: str, provider_name: str) -> bool:
    """Determine if we should use structured outputs for this request.

    Structured outputs provide stronger guarantees but require schema definitions.
    Use them when:
    1. Provider supports it (OpenAI)
    2. We have a schema defined for this batch
    3. Environment variable enables it

    Args:
        batch_name: Name of the extraction batch
        provider_name: Name of the LLM provider

    Returns:
        True if structured outputs should be used
    """
    import os

    # Check env opt-in
    if os.getenv("USE_STRUCTURED_OUTPUTS", "").lower() != "true":
        return False

    # Check provider support
    if not supports_structured_outputs(provider_name):
        return False

    # Check if we have a schema
    return get_structured_output_response_schema(batch_name) is not None


def get_response_format(provider_name: str, batch_name: str) -> dict[str, str] | dict[str, Any]:
    """Get the appropriate response_format for an API call.

    Args:
        provider_name: Name of the LLM provider
        batch_name: Name of the extraction batch

    Returns:
        response_format dict for the API call
    """
    # Check if we should use structured outputs
    if should_use_structured_outputs(batch_name, provider_name):
        schema = get_structured_output_response_schema(batch_name)
        return {"type": "json_schema", "json_schema": schema}

    # Default to json_object mode (guarantees valid JSON)
    return {"type": "json_object"}
