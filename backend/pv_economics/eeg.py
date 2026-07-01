"""Versioned German EEG surplus feed-in tariffs for the supported MVP case."""

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite

EEG_SOURCE_URL = "https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/ErneuerbareEnergien/EEG_Foerderung/start.html"
EEG_DURATION_SOURCE_URL = "https://www.gesetze-im-internet.de/eeg_2014/__25.html"


class EEGTariffError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EEGTariffPeriod:
    valid_from: date
    valid_to: date
    tiers_ct_per_kwh: tuple[tuple[float, float], ...]
    data_version: str


@dataclass(frozen=True, slots=True)
class EEGTariffResult:
    rate_eur_per_kwh: float
    manual_override: bool
    valid_from: date | None
    valid_to: date | None
    data_version: str
    source_url: str


PUBLISHED_TARIFFS = (
    EEGTariffPeriod(
        date(2026, 2, 1), date(2026, 7, 31),
        ((10.0, 7.78), (40.0, 6.73), (100.0, 5.50)),
        "BNetzA-2026-02-01",
    ),
)


def resolve_eeg_surplus_tariff(
    installed_power_kw: float, commissioning_date: date, *,
    manual_override_eur_per_kwh: float | None = None,
) -> EEGTariffResult:
    """Return the capacity-weighted building-system surplus tariff."""
    if not isfinite(installed_power_kw) or not 0 < installed_power_kw <= 100:
        raise EEGTariffError("Installed PV power must be greater than 0 and at most 100 kW.")
    if manual_override_eur_per_kwh is not None:
        if (not isfinite(manual_override_eur_per_kwh)
                or manual_override_eur_per_kwh < 0):
            raise EEGTariffError("Manual feed-in tariff must be finite and non-negative.")
        return EEGTariffResult(manual_override_eur_per_kwh, True, None, None,
                               "user-input", EEG_SOURCE_URL)
    period = next((item for item in PUBLISHED_TARIFFS
                   if item.valid_from <= commissioning_date <= item.valid_to), None)
    if period is None:
        raise EEGTariffError(
            "No published EEG surplus tariff is available for the commissioning date; "
            "provide an explicit manual tariff."
        )
    remaining, previous, weighted = installed_power_kw, 0.0, 0.0
    for upper, cents in period.tiers_ct_per_kwh:
        share = min(remaining, upper - previous)
        weighted += share * cents / 100
        remaining -= share
        previous = upper
        if remaining <= 0:
            break
    return EEGTariffResult(weighted / installed_power_kw, False,
                           period.valid_from, period.valid_to,
                           period.data_version, EEG_SOURCE_URL)


def eeg_payment_end(commissioning_date: date) -> date:
    """Model §25 as ending on 31 December after twenty payment years."""
    return date(commissioning_date.year + 20, 12, 31)


def annual_feed_in_tariffs(
    result: EEGTariffResult, commissioning_date: date, years: int, *,
    post_eeg_value_eur_per_kwh: float = 0.0,
) -> tuple[float, ...]:
    """Create annual rates; a partial final entitlement year is day-weighted."""
    if years <= 0 or not isfinite(post_eeg_value_eur_per_kwh) or post_eeg_value_eur_per_kwh < 0:
        raise EEGTariffError("Tariff horizon and post-EEG value must be valid.")
    end = eeg_payment_end(commissioning_date)
    rates = []
    for offset in range(years):
        start = _add_years(commissioning_date, offset)
        stop = _add_years(commissioning_date, offset + 1)
        eligible_stop = min(stop, end + timedelta(days=1))
        fraction = max(0, (eligible_stop - start).days) / (stop - start).days
        rates.append(result.rate_eur_per_kwh * fraction
                     + post_eeg_value_eur_per_kwh * (1 - fraction))
    return tuple(rates)


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)
