from datetime import date, datetime, timezone

import pytest

from backend.pv_economics import calculate_energy_scenarios
from backend.pv_economics.load_profiles import (
    DayType, H25DataUnavailableError, LoadProfileError, ProfileKind,
    bdew_dynamisation_factor, classify_day, generate_household_load_profile,
    sha256_file,
)
from tests.test_bdew_h25_data import artificial_csv


def external_artificial_csv(tmp_path):
    path = tmp_path / "artificial-profile.csv"
    path.write_text(artificial_csv(), encoding="utf-8")
    return path, sha256_file(path)


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
def test_generates_8760_utc_hours_and_exact_annual_energy(tmp_path, annual):
    path, checksum = external_artificial_csv(tmp_path)
    result = generate_household_load_profile(annual, "BE", h25_csv_path=path,
                                             h25_csv_sha256=checksum)
    assert len(result.timestamps_utc) == len(result.hourly_consumption_kwh) == 8760
    assert result.timestamps_utc[0] == datetime(2001, 1, 1, tzinfo=timezone.utc)
    assert result.timestamps_utc[-1] == datetime(2001, 12, 31, 23, tzinfo=timezone.utc)
    assert all(stamp.tzinfo == timezone.utc for stamp in result.timestamps_utc)
    assert sum(result.hourly_consumption_kwh) == pytest.approx(annual, abs=1e-9)
    assert min(result.hourly_consumption_kwh) >= 0


def test_canonical_axis_covers_dst_without_gaps_or_duplicates(tmp_path):
    path, checksum = external_artificial_csv(tmp_path)
    result = generate_household_load_profile(3500, "BE", h25_csv_path=path,
                                             h25_csv_sha256=checksum)
    differences = [(right-left).total_seconds() for left, right in
                   zip(result.timestamps_utc, result.timestamps_utc[1:])]
    assert set(differences) == {3600}


def test_result_is_directly_compatible_with_energy_model(tmp_path):
    path, checksum = external_artificial_csv(tmp_path)
    load = generate_household_load_profile(3500, "BE", h25_csv_path=path,
                                           h25_csv_sha256=checksum)
    scenarios = calculate_energy_scenarios(load.hourly_consumption_kwh,
                                           [[0.0] * 8760])
    assert scenarios.without_pv.household_consumption_kwh == pytest.approx(3500)


def test_synthetic_profiles_shift_or_flatten_without_changing_energy(tmp_path):
    path, checksum = external_artificial_csv(tmp_path)
    base = generate_household_load_profile(3500, "BE", h25_csv_path=path,
                                           h25_csv_sha256=checksum)
    day = generate_household_load_profile(3500, "BE", ProfileKind.DAYTIME,
        h25_csv_path=path, h25_csv_sha256=checksum)
    evening = generate_household_load_profile(3500, "BE", ProfileKind.EVENING,
        h25_csv_path=path, h25_csv_sha256=checksum)
    flatter = generate_household_load_profile(3500, "BE", ProfileKind.FLATTER,
        h25_csv_path=path, h25_csv_sha256=checksum)
    local_hours = [stamp.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Berlin")).hour
                   for stamp in base.timestamps_utc]
    assert sum(v for v, h in zip(day.hourly_consumption_kwh, local_hours) if 10 <= h <= 16) > sum(v for v, h in zip(base.hourly_consumption_kwh, local_hours) if 10 <= h <= 16)
    assert sum(v for v, h in zip(evening.hourly_consumption_kwh, local_hours) if 17 <= h <= 22) > sum(v for v, h in zip(base.hourly_consumption_kwh, local_hours) if 17 <= h <= 22)
    assert max(flatter.hourly_consumption_kwh) < max(base.hourly_consumption_kwh)
    assert all(sum(item.hourly_consumption_kwh) == pytest.approx(3500)
               for item in (day, evening, flatter))
    assert all("nicht aus deinen Messdaten" in item.profile_name
               for item in (day, evening, flatter))


def test_fail_closed_and_invalid_inputs(tmp_path):
    with pytest.raises(H25DataUnavailableError):
        generate_household_load_profile(3500, "BE")
    path, checksum = external_artificial_csv(tmp_path)
    with pytest.raises(LoadProfileError):
        generate_household_load_profile(0, "BE", h25_csv_path=path,
                                        h25_csv_sha256=checksum)
    with pytest.raises(LoadProfileError):
        generate_household_load_profile(3500, "XX", h25_csv_path=path,
                                        h25_csv_sha256=checksum)
    with pytest.raises(LoadProfileError):
        generate_household_load_profile(3500, "BE", "unknown",
                                        h25_csv_path=path, h25_csv_sha256=checksum)
    with pytest.raises(LoadProfileError, match="SHA-256"):
        generate_household_load_profile(3500, "BE", h25_csv_path=path,
                                        h25_csv_sha256="0" * 64)
