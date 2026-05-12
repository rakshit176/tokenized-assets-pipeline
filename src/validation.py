"""Per-field validation for extracted data.

Provides validation rules for specific fields to catch common errors:
- URL format validation
- Email format validation
- Year ranges (founded_year can't be in future)
- Status enum validation
- Number ranges (employee counts, funding amounts)
- Date format validation
"""
import re
import logging
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ValidationResult:
    """Result of a field validation."""
    def __init__(self, is_valid: bool, error: str = "", normalized_value: Any = None):
        self.is_valid = is_valid
        self.error = error
        self.normalized_value = normalized_value


def validate_url(value: Any) -> ValidationResult:
    """Validate URL format."""
    if not value or str(value).strip() in ["", "null", "N/A", "Unknown"]:
        return ValidationResult(True)  # Empty is OK (will be null)

    url_str = str(value).strip()

    # Add protocol if missing
    if not url_str.startswith(("http://", "https://")):
        if "." in url_str:
            url_str = "https://" + url_str
        else:
            return ValidationResult(False, f"Invalid URL format: {value}")

    try:
        parsed = urlparse(url_str)
        if not parsed.netloc or "." not in parsed.netloc:
            return ValidationResult(False, f"Invalid URL: {value}")
        return ValidationResult(True, normalized_value=url_str)
    except Exception:
        return ValidationResult(False, f"Invalid URL: {value}")


def validate_email(value: Any) -> ValidationResult:
    """Validate email format."""
    if not value or str(value).strip() in ["", "null", "N/A", "Unknown"]:
        return ValidationResult(True)

    email_str = str(value).strip()
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(pattern, email_str):
        return ValidationResult(False, f"Invalid email: {value}")

    return ValidationResult(True, normalized_value=email_str.lower())


def validate_year(value: Any, field_name: str = "year") -> ValidationResult:
    """Validate year is in reasonable range."""
    if not value or str(value).strip() in ["", "null", "N/A", "Unknown"]:
        return ValidationResult(True)

    try:
        # Handle various year formats
        if isinstance(value, str):
            # Handle "2023", "2023-", etc
            value = re.sub(r'[^0-9]', '', str(value))

        year = int(value)
        current_year = datetime.now().year

        if year < 1990:  # Tokenization didn't exist before 1990
            return ValidationResult(False, f"{field_name} {year} is too early (pre-1990)")

        if year > current_year + 1:  # Allow next year for recent startups
            return ValidationResult(False, f"{field_name} {year} is in the future")

        return ValidationResult(True, normalized_value=year)
    except (ValueError, TypeError):
        return ValidationResult(False, f"Invalid year format: {value}")


def validate_funding_amount(value: Any) -> ValidationResult:
    """Validate funding amount is reasonable."""
    if not value or str(value).strip() in ["", "null", "N/A", "Unknown"]:
        return ValidationResult(True)

    try:
        # Extract number from various formats
        if isinstance(value, str):
            # Handle "$1.2M", "1.2 billion", etc.
            value = value.lower().replace("$", "").replace(" ", "").replace(",", "")

            multipliers = {"b": 1_000_000_000, "m": 1_000_000, "k": 1_000}
            for suffix, mult in multipliers.items():
                if value.endswith(suffix):
                    return ValidationResult(True, normalized_value=float(value[:-1]) * mult)

            amount = float(value)
        else:
            amount = float(value)

        # Tokenization funding rounds are usually $100K - $1B
        if amount < 1000:
            return ValidationResult(False, f"Funding amount too small: ${amount:,.0f}")
        if amount > 5_000_000_000:  # $5B max
            return ValidationResult(False, f"Funding amount too large: ${amount:,.0f}")

        return ValidationResult(True, normalized_value=int(amount))
    except (ValueError, TypeError):
        return ValidationResult(False, f"Invalid funding amount: {value}")


def validate_employee_count(value: Any) -> ValidationResult:
    """Validate employee count is reasonable."""
    if not value or str(value).strip() in ["", "null", "N/A", "Unknown"]:
        return ValidationResult(True)

    try:
        # Handle ranges like "10-50", "100+", etc.
        if isinstance(value, str):
            # Extract first number from range
            match = re.search(r'\d+', value)
            if match:
                count = int(match.group())
            else:
                return ValidationResult(False, f"Invalid employee count: {value}")
        else:
            count = int(value)

        # Startup employee counts
        if count < 1:
            return ValidationResult(False, f"Employee count too small: {count}")
        if count > 10_000:
            return ValidationResult(False, f"Employee count too large: {count}")

        return ValidationResult(True, normalized_value=count)
    except (ValueError, TypeError):
        return ValidationResult(False, f"Invalid employee count: {value}")


def validate_status(value: Any, valid_statuses: list[str]) -> ValidationResult:
    """Validate status against allowed values."""
    if not value or str(value).strip() in ["", "null", "N/A", "Unknown"]:
        return ValidationResult(True)

    value_str = str(value).strip().lower()

    # Check if value matches any valid status (case-insensitive)
    for valid in valid_statuses:
        if value_str == valid.lower():
            return ValidationResult(True, normalized_value=valid)

    # Check partial matches
    for valid in valid_statuses:
        if valid.lower() in value_str or value_str in valid.lower():
            return ValidationResult(True, normalized_value=valid)

    return ValidationResult(
        False,
        f"Invalid status: {value}. Must be one of: {', '.join(valid_statuses)}"
    )


# Field-specific validation rules
FIELD_VALIDATORS = {
    # URLs
    "website": validate_url,
    "logo_url": validate_url,
    "source_url": validate_url,
    "certificate_url": validate_url,
    "documentation_url": validate_url,
    "public_url": validate_url,

    # Emails (not in current schema but useful)
    "email": validate_email,

    # Years
    "founded_year": lambda v: validate_year(v, "founded_year"),
    "launch_date": lambda v: validate_year(v, "launch_date"),
    "issued_date": lambda v: validate_year(v, "issued_date"),
    "expiry_date": lambda v: validate_year(v, "expiry_date"),
    "announced_date": lambda v: validate_year(v, "announced_date"),
    "completion_date": lambda v: validate_year(v, "completion_date"),

    # Money
    "amount_usd": validate_funding_amount,
    "valuation_usd": validate_funding_amount,
    "total_funding_usd": validate_funding_amount,
    "treasury_runway_months": lambda v: ValidationResult(
        True, normalized_value=int(str(v)) if str(v).isdigit() else v
    ) if v else ValidationResult(True),

    # Counts
    "total_employees": validate_employee_count,
    "follower_count": lambda v: ValidationResult(
        True, normalized_value=int(str(v)) if str(v).replace(',', '').isdigit() else v
    ) if v else ValidationResult(True),  # Social followers can be any size
    "number_of_clients": validate_employee_count,
    "number_of_issuances": validate_employee_count,
    "number_of_active_tokens": validate_employee_count,

    # Status enums
    "operational_status": lambda v: validate_status(
        v, ["Active", "Inactive", "Acquired", "Shutdown", "In Steatlh"]
    ),
    "is_active": lambda v: ValidationResult(True),  # Boolean handled elsewhere
    "mainnet_live": lambda v: ValidationResult(True),

    # Platform/chain (common values)
    "chains_supported": lambda v: ValidationResult(
        True,
        normalized_value=str(v).strip().title()
    ) if v else ValidationResult(True),
}


def validate_field(field_name: str, value: Any) -> ValidationResult:
    """Validate a single field value.

    Args:
        field_name: Name of the field to validate
        value: Value to validate

    Returns:
        ValidationResult with is_valid flag and optional normalized value
    """
    # Skip None/empty values
    if value is None:
        return ValidationResult(True)

    # Strip strings
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in ["null", "n/a", "unknown", "none"]:
            return ValidationResult(True)

    # Get validator for this field
    validator = FIELD_VALIDATORS.get(field_name)

    if validator:
        try:
            return validator(value)
        except Exception as e:
            logger.warning(f"Validation error for {field_name}={value}: {e}")
            return ValidationResult(False, f"Validation error: {str(e)[:100]}")

    # No validator defined, assume valid
    return ValidationResult(True)


def validate_company_data(data: dict) -> dict[str, list[str]]:
    """Validate all fields in extracted company data.

    Args:
        data: Extracted data dictionary

    Returns:
        Dict mapping table_name to list of validation errors
    """
    errors = {}

    for table_name, table_data in data.items():
        table_errors = []

        if isinstance(table_data, dict) and "rows" in table_data:
            # Repeating table
            for row_idx, row in enumerate(table_data["rows"]):
                for field_name, field_value in row.items():
                    if isinstance(field_value, dict):
                        # CitedValue - validate the value inside
                        value = field_value.get("value")
                        result = validate_field(field_name, value)
                        if not result.is_valid:
                            table_errors.append(
                                f"Row {row_idx}, {field_name}: {result.error}"
                            )
                        elif result.normalized_value is not None:
                            # Update with normalized value
                            field_value["value"] = result.normalized_value
        elif isinstance(table_data, dict):
            # Single-row table
            for field_name, field_value in table_data.items():
                if isinstance(field_value, dict):
                    value = field_value.get("value")
                    result = validate_field(field_name, value)
                    if not result.is_valid:
                        table_errors.append(f"{field_name}: {result.error}")
                    elif result.normalized_value is not None:
                        field_value["value"] = result.normalized_value

        if table_errors:
            errors[table_name] = table_errors

    return errors
