from __future__ import annotations

from ..models import NormalizedCompany
from .base import IngestionError


class ValidationError(IngestionError):
    """Raised when normalized data fails business validation."""


def validate_normalized(data: NormalizedCompany) -> None:
    """Validate normalized dataset before database persistence."""
    if not data.company.ticker:
        raise ValidationError("Company ticker is required")

    if not data.company.name:
        raise ValidationError("Company name is required")

    if not data.financials and not data.prices and not data.shareholding:
        raise ValidationError("No financial, price, or shareholding rows were parsed")
