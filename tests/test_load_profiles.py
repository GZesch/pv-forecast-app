import inspect
from datetime import date, datetime, timezone

import pytest

from backend.pv_economics import calculate_energy_scenarios
from backend.pv_economics.load_profiles import (
    OFFICIAL_H25_CSV_SHA256, DayType, H25DataUnavailableError,
    LoadProfileError, ProfileKind, _generate_household_load_profile_from_data,
    bdew_dynamisation_factor, classify_day, generate_household_load_profile,
)
from tests.test_bdew_h25_data import artificial_csv, parse


def generate_artificial(annual, state="BE", kind=ProfileKind.H25):
    return _generate_household_load_profile_from_data(
        annual, state, kind, parse(artificial_csv()),
        source_csv_sha256="ARTIFICIAL-TEST-CHECKSUM",
    )


def test_day_classification_weekends_holidays_and_special_days():
    assert classify_day(date(2001, 1, 2), "BE") == DayType.WEEKDAY
    assert classify_day(date(2001, 1, 6), "BE") == DayType.SATURDAY
    assert classify_day(date(2001, 1, 7), "BE") == DayType.SUNDAY_HOLIDAY
    assert classify_day(date(2001, 10, 3), "BE") == DayType.SUNDAY_HOLIDAY
    assert classify_day(date(2001, 3, 8), "BE") == DayType.SUNDAY_HOLIDAY
    assert classify_day(date(2001, 3, 8), "HE") == DayType.WEEKDAY
    assert classify_day(date(2001, 12, 24), "BE") == DayType.SATURDAY
    assert classify_day(date(2001, 12, 31), "BE") == DayType.SATURDAY


def test_dynamisation_reference_values():
    assert bdew_dynamisation_factor(1) == 1.242
    assert bdew_dynamisation_factor(365) == 1.2572


@pytest.mark.parametrize("annual", [1, 3500, 12345.67])
def test_generates_8760_utc_hours_and_exact_annual_energy(annual):
    result = generate_artificial(annual)
    assert len(result.timestamps_utc) == len(result.hourly_consumption_kwh) == 8760
    assert result.timestamps_utc[0] == datetime(2001, 1, 1, tzinfo=timezone.utc)
    assert result.timestamps_utc[-1] == datetime(2001, 12, 31, 23, tzinfo=timezone.utc)
    assert all(stamp.tzinfo == timezone.utc for stamp in result.timestamps_utc)
    assert sum(result.hourly_consumption_kwh) == pytest.approx(annual, abs=1e-9)
    assert min(result.hourly_consumption_kwh) >= 0
    assert result.metadata.source_type == "artificial_test_data"
    assert "Artificial test matrix" in result.metadata.source_name


def test_canonical_axis_covers_dst_without_gaps_or_duplicates():
    result = generate_artificial(3500)
    differences = [(right-left).total_seconds() for left, right in
                   zip(result.timestamps_utc, result.timestamps_utc[1:])]
    assert set(differences) == {3600}


def test_result_is_directly_compatible_with_energy_model():
    load = generate_artificial(3500)
    scenarios = calculate_energy_scenarios(load.hourly_consumption_kwh,
                                           [[0.0] * 8760])
    assert scenarios.without_pv.household_consumption_kwh == pytest.approx(3500)


def test_synthetic_profiles_shift_or_flatten_without_changing_energy():
    base = generate_artificial(3500)
    day = generate_artificial(3500, kind=ProfileKind.DAYTIME)
    evening = generate_artificial(3500, kind=ProfileKind.EVENING)
    flatter = generate_artificial(3500, kind=ProfileKind.FLATTER)
    local_hours = [stamp.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Berlin")).hour
                   for stamp in base.timestamps_utc]
    assert sum(v for v, h in zip(day.hourly_consumption_kwh, local_hours) if 10 <= h <= 16) > sum(v for v, h in zip(base.hourly_consumption_kwh, local_hours) if 10 <= h <= 16)
    assert sum(v for v, h in zip(evening.hourly_consumption_kwh, local_hours) if 17 <= h <= 22) > sum(v for v, h in zip(base.hourly_consumption_kwh, local_hours) if 17 <= h <= 22)
    assert max(flatter.hourly_consumption_kwh) < max(base.hourly_consumption_kwh)
    assert all(sum(item.hourly_consumption_kwh) == pytest.approx(3500)
               for item in (day, evening, flatter))
    assert all("nicht aus deinen Messdaten" in item.profile_name
               for item in (day, evening, flatter))
    assert all(item.metadata.source_type == "exergypulse_synthetic_test_data"
               for item in (day, evening, flatter))


def test_public_function_fails_closed_without_file():
    assert "h25_csv_sha256" not in inspect.signature(
        generate_household_load_profile
    ).parameters
    with pytest.raises(H25DataUnavailableError):
        generate_household_load_profile(3500, "BE")
    with pytest.raises(H25DataUnavailableError, match="not found"):
        generate_household_load_profile(
            3500, "BE", h25_csv_path="definitely-missing-h25.csv"
        )


def test_public_function_rejects_arbitrary_csv_even_when_caller_knows_hash(tmp_path):
    path = tmp_path / "artificial-profile.csv"
    path.write_text(artificial_csv(), encoding="utf-8")
    with pytest.raises(LoadProfileError, match="provenance check failed"):
        generate_household_load_profile(3500, "BE", h25_csv_path=path)


def test_known_official_csv_checksum_is_fixed():
    assert OFFICIAL_H25_CSV_SHA256 == (
        "83A7F47E3A6BDEC28EF49FC56351542B3CBC13493BD988908B15579D7A6D66B8"
    )


def test_invalid_inputs_on_pure_generator():
    data = parse(artificial_csv())
    with pytest.raises(LoadProfileError):
        _generate_household_load_profile_from_data(
            0, "BE", ProfileKind.H25, data, source_csv_sha256="artificial"
        )
    with pytest.raises(LoadProfileError):
        _generate_household_load_profile_from_data(
            3500, "XX", ProfileKind.H25, data, source_csv_sha256="artificial"
        )
    with pytest.raises(LoadProfileError):
        _generate_household_load_profile_from_data(
            3500, "BE", "unknown", data, source_csv_sha256="artificial"
        )
