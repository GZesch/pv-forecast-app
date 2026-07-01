from datetime import date

import pytest

from backend.pv_economics.eeg import (
    EEG_SOURCE_URL, EEGTariffError, annual_feed_in_tariffs,
    eeg_payment_end, resolve_eeg_surplus_tariff,
)


@pytest.mark.parametrize(("power", "expected_cents"), [
    (5, 7.78), (10, 7.78),
    (15, (10*7.78 + 5*6.73)/15),
    (40, (10*7.78 + 30*6.73)/40),
    (50, (10*7.78 + 30*6.73 + 10*5.50)/50),
    (100, (10*7.78 + 30*6.73 + 60*5.50)/100),
])
def test_capacity_weighted_tariff(power, expected_cents):
    result = resolve_eeg_surplus_tariff(power, date(2026, 2, 1))
    assert result.rate_eur_per_kwh == pytest.approx(expected_cents / 100)
    assert not result.manual_override
    assert result.source_url == EEG_SOURCE_URL
    assert result.data_version == "BNetzA-2026-02-01"


def test_tariff_period_boundaries_and_unsupported_values():
    resolve_eeg_surplus_tariff(10, date(2026, 7, 31))
    with pytest.raises(EEGTariffError, match="No published"):
        resolve_eeg_surplus_tariff(10, date(2026, 8, 1))
    with pytest.raises(EEGTariffError):
        resolve_eeg_surplus_tariff(101, date(2026, 2, 1))


def test_manual_override_is_explicit():
    result = resolve_eeg_surplus_tariff(
        15, date(2030, 1, 1), manual_override_eur_per_kwh=.04)
    assert result.rate_eur_per_kwh == .04
    assert result.manual_override
    assert result.data_version == "user-input"


def test_payment_duration_and_post_eeg_series():
    commissioning = date(2026, 2, 1)
    result = resolve_eeg_surplus_tariff(10, commissioning)
    assert eeg_payment_end(commissioning) == date(2046, 12, 31)
    rates = annual_feed_in_tariffs(result, commissioning, 22)
    assert rates[:20] == (result.rate_eur_per_kwh,) * 20
    assert 0 < rates[20] < result.rate_eur_per_kwh
    assert rates[21] == 0
