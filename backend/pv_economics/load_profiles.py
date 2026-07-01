"""Validated input infrastructure for BDEW H25 household load profiles.

The official H25 values and dynamisation coefficients are intentionally not embedded:
no redistributable official value table was available when this module was created.
"""

import csv
from dataclasses import dataclass
from enum import StrEnum
from io import TextIOBase
from math import isfinite


class LoadProfileError(ValueError):
    """Raised when household load-profile inputs are incomplete or invalid."""


class H25DataUnavailableError(LoadProfileError):
    """Raised while the official, redistributable H25 source data is unavailable."""


class DayType(StrEnum):
    """BDEW H25 type-day identifiers."""

    WEEKDAY = "WT"
    SATURDAY = "SA"
    SUNDAY_HOLIDAY = "FT"


@dataclass(frozen=True, slots=True)
class H25Key:
    """One month, type-day and local quarter-hour position."""

    month: int
    day_type: DayType
    quarter_hour: int


@dataclass(frozen=True, slots=True)
class BDEWH25Data:
    """Complete 12 × 3 × 96 H25 type-day matrix from an official source."""

    values: dict[H25Key, float]
    unit: str
    normalization_kwh: float
    source_name: str
    source_version: str
    source_url: str
    source_sha256: str

    def value(self, month: int, day_type: DayType, quarter_hour: int) -> float:
        """Return one source value after construction-time completeness checks."""
        return self.values[H25Key(month, day_type, quarter_hour)]


REQUIRED_COLUMNS = ("month", "day_type", "quarter_hour", "value")
EXPECTED_VALUE_COUNT = 12 * len(DayType) * 96


def parse_bdew_h25_csv(
    source: TextIOBase,
    *,
    unit: str,
    normalization_kwh: float,
    source_name: str,
    source_version: str,
    source_url: str,
    source_sha256: str,
) -> BDEWH25Data:
    """Parse a normalized CSV created reproducibly from an official H25 file.

    Expected columns are ``month,day_type,quarter_hour,value``. Quarter-hour
    positions are zero-based (0..95); values retain the documented source unit.
    """
    if not unit.strip():
        raise LoadProfileError("H25 source unit must be documented.")
    if not isfinite(normalization_kwh) or normalization_kwh <= 0:
        raise LoadProfileError("H25 normalization must be positive and finite.")
    metadata = (source_name, source_version, source_url, source_sha256)
    if any(not item.strip() for item in metadata):
        raise LoadProfileError("H25 source provenance and checksum must be complete.")

    reader = csv.DictReader(source)
    if reader.fieldnames != list(REQUIRED_COLUMNS):
        raise LoadProfileError(
            "H25 CSV columns must be month, day_type, quarter_hour, value."
        )
    values: dict[H25Key, float] = {}
    for line_number, row in enumerate(reader, start=2):
        try:
            key = H25Key(
                month=int(row["month"]),
                day_type=DayType(row["day_type"]),
                quarter_hour=int(row["quarter_hour"]),
            )
            value = float(row["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LoadProfileError(
                f"Invalid H25 value or key on CSV line {line_number}."
            ) from exc
        if not 1 <= key.month <= 12:
            raise LoadProfileError(f"Invalid H25 month on CSV line {line_number}.")
        if not 0 <= key.quarter_hour < 96:
            raise LoadProfileError(
                f"Invalid H25 quarter-hour on CSV line {line_number}."
            )
        if not isfinite(value) or value < 0:
            raise LoadProfileError(
                f"H25 values must be finite and non-negative (line {line_number})."
            )
        if key in values:
            raise LoadProfileError(f"Duplicate H25 key on CSV line {line_number}.")
        values[key] = value

    expected = {
        H25Key(month, day_type, quarter_hour)
        for month in range(1, 13)
        for day_type in DayType
        for quarter_hour in range(96)
    }
    missing = expected - values.keys()
    extra = values.keys() - expected
    if missing or extra or len(values) != EXPECTED_VALUE_COUNT:
        raise LoadProfileError(
            "H25 data must contain all 12 months, three day types, and exactly "
            "96 quarter-hours per type-day."
        )
    return BDEWH25Data(
        values, unit, normalization_kwh, source_name, source_version,
        source_url, source_sha256,
    )


def generate_household_load_profile(*args: object, **kwargs: object) -> None:
    """Report the explicit source-data blocker instead of fabricating H25 values."""
    del args, kwargs
    raise H25DataUnavailableError(
        "The official BDEW H25 value table and its redistribution terms are not "
        "available in this repository; household profiles cannot be generated safely."
    )
