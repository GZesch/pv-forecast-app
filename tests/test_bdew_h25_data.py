from io import StringIO

import pytest

from backend.pv_economics.load_profiles import (
    BDEWH25Data,
    DayType,
    H25DataUnavailableError,
    LoadProfileError,
    generate_household_load_profile,
    parse_bdew_h25_csv,
)


def complete_csv(*, omitted=None, duplicate=None, replacement=None):
    rows = ["month,day_type,quarter_hour,value"]
    for month in range(1, 13):
        for day_type in DayType:
            for quarter_hour in range(96):
                key = (month, day_type.value, quarter_hour)
                if key == omitted:
                    continue
                value = replacement if key == (1, "WT", 0) and replacement is not None else 1
                rows.append(f"{month},{day_type.value},{quarter_hour},{value}")
                if key == duplicate:
                    rows.append(f"{month},{day_type.value},{quarter_hour},{value}")
    return "\n".join(rows)


def parse(text):
    return parse_bdew_h25_csv(
        StringIO(text), unit="W", normalization_kwh=1_000_000,
        source_name="Official BDEW H25 test fixture", source_version="2025-03-17",
        source_url="https://www.bdew.de/official-file.xlsx", source_sha256="a" * 64,
    )


def test_parser_accepts_complete_twelve_by_three_by_ninety_six_matrix():
    data = parse(complete_csv())
    assert isinstance(data, BDEWH25Data)
    assert len(data.values) == 12 * 3 * 96
    assert {key.month for key in data.values} == set(range(1, 13))
    assert {key.day_type for key in data.values} == set(DayType)
    assert all(sum(key.month == month and key.day_type == day_type
                   for key in data.values) == 96
               for month in range(1, 13) for day_type in DayType)
    assert data.value(12, DayType.SUNDAY_HOLIDAY, 95) == 1


def test_parser_rejects_incomplete_source_data():
    with pytest.raises(LoadProfileError, match="all 12 months"):
        parse(complete_csv(omitted=(12, "FT", 95)))


def test_parser_rejects_duplicate_keys():
    with pytest.raises(LoadProfileError, match="Duplicate"):
        parse(complete_csv(duplicate=(1, "WT", 0)))


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "not-a-number"])
def test_parser_rejects_invalid_values(value):
    with pytest.raises(LoadProfileError):
        parse(complete_csv(replacement=value))


def test_parser_requires_source_provenance_and_unit():
    with pytest.raises(LoadProfileError, match="unit"):
        parse_bdew_h25_csv(
            StringIO(complete_csv()), unit="", normalization_kwh=1_000_000,
            source_name="BDEW", source_version="2025", source_url="official",
            source_sha256="a" * 64,
        )


def test_generation_fails_transparently_without_official_values():
    with pytest.raises(H25DataUnavailableError, match="cannot be generated safely"):
        generate_household_load_profile(
            annual_consumption_kwh=3500, federal_state="BE", profile_kind="h25"
        )
