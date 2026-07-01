"""Pure degradation models for multi-year PV and battery projections."""

from dataclasses import dataclass
from math import isfinite


class DegradationError(ValueError):
    """Raised for invalid or non-physical degradation assumptions."""


@dataclass(frozen=True, slots=True)
class PVDegradation:
    """Geometric PV degradation; operating year one starts at factor 1."""

    annual_rate: float = 0.005

    def factor(self, operating_year: int) -> float:
        _validate_year_and_rate(operating_year, self.annual_rate)
        return _factor((1 - self.annual_rate) ** (operating_year - 1))


@dataclass(frozen=True, slots=True)
class GeometricBatteryDegradation:
    """Geometric usable-capacity loss without power or efficiency degradation."""

    annual_rate: float = 0.02

    def capacity_factor(
        self, operating_year: int, cumulative_throughput_kwh: float,
        cumulative_efc: float,
    ) -> float:
        del cumulative_throughput_kwh, cumulative_efc
        _validate_year_and_rate(operating_year, self.annual_rate)
        return _factor((1 - self.annual_rate) ** (operating_year - 1))


@dataclass(frozen=True, slots=True)
class WarrantyBatteryDegradation:
    """Conservative extrapolation of a warranty boundary, not a forecast.

    Calendar and throughput ageing are not added or multiplied. Temperature,
    state of charge, depth of discharge, C-rate and chemistry are not modelled;
    power and efficiency remain constant and no replacement is implied.
    """

    residual_capacity_fraction: float
    warranty_years: float
    warranted_throughput_kwh: float | None = None
    warranted_efc: float | None = None

    def __post_init__(self) -> None:
        values = (self.residual_capacity_fraction, self.warranty_years)
        if any(not isfinite(value) for value in values):
            raise DegradationError("Battery warranty values must be finite.")
        if not 0 <= self.residual_capacity_fraction <= 1:
            raise DegradationError("Warranty residual capacity must be between 0 and 1.")
        if self.warranty_years <= 0:
            raise DegradationError("Warranty duration must be positive.")
        if (self.warranted_throughput_kwh is None) == (self.warranted_efc is None):
            raise DegradationError("Specify exactly one warranted throughput or EFC value.")
        limit = (self.warranted_throughput_kwh if self.warranted_throughput_kwh is not None
                 else self.warranted_efc)
        if limit is None or not isfinite(limit) or limit <= 0:
            raise DegradationError("Warranted throughput or EFC must be positive and finite.")

    def capacity_factor(
        self, operating_year: int, cumulative_throughput_kwh: float,
        cumulative_efc: float,
    ) -> float:
        if operating_year < 1:
            raise DegradationError("Operating year must be at least 1.")
        if any(not isfinite(value) or value < 0 for value in
               (cumulative_throughput_kwh, cumulative_efc)):
            raise DegradationError("Cumulative battery use must be finite and non-negative.")
        loss = 1 - self.residual_capacity_fraction
        calendar = max(0.0, 1 - loss * (operating_year - 1) / self.warranty_years)
        use = (cumulative_throughput_kwh if self.warranted_throughput_kwh is not None
               else cumulative_efc)
        limit = (self.warranted_throughput_kwh if self.warranted_throughput_kwh is not None
                 else self.warranted_efc)
        throughput = max(0.0, 1 - loss * use / float(limit))
        return _factor(min(calendar, throughput))


def _validate_year_and_rate(year: int, rate: float) -> None:
    if year < 1:
        raise DegradationError("Operating year must be at least 1.")
    if not isfinite(rate) or not 0 <= rate < 1:
        raise DegradationError("Annual degradation rate must be finite and in [0, 1).")


def _factor(value: float) -> float:
    if not isfinite(value) or value < 0:
        raise DegradationError("Degradation produced an invalid factor.")
    return value
