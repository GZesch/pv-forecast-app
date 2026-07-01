from io import StringIO

import pytest

from backend.pv_economics.load_profiles import (
    BDEWH25Data, DayType, LoadProfileError, parse_bdew_h25_csv,
)


def artificial_csv(*, omitted=None, duplicate=None, replacement=None):
    """Clearly synthetic parser fixture; these are not BDEW H25 values."""
    rows = ["month,day_type,quarter_hour,value"]
    for month in range(1, 13):
        for day_type in DayType:
            for quarter in range(96):
                key = (month, day_type.value, quarter)
                if key == omitted:
                    continue
                value = replacement if key == (1, "WT", 0) and replacement else 1
                rows.append(f"{month},{day_type.value},{quarter},{value}")
                if key == duplicate:
                    rows.append(f"{month},{day_type.value},{quarter},{value}")
    return "\n".join(rows)


def parse(text):
    return parse_bdew_h25_csv(
        StringIO(text), unit="kWh", normalization_kwh=1_000_000,
        source_name="Artificial test matrix – not H25", source_version="test",
        source_url="https://invalid.example/test", source_sha256="a" * 64,
    )


def test_parser_accepts_complete_artificial_matrix():
    data = parse(artificial_csv())
    assert isinstance(data, BDEWH25Data)
    assert len(data.values) == 3456
    assert data.value(12, DayType.SUNDAY_HOLIDAY, 95) == 1


def test_parser_rejects_incomplete_and_duplicate_data():
    with pytest.raises(LoadProfileError, match="all 12 months"):
        parse(artificial_csv(omitted=(12, "FT", 95)))
    with pytest.raises(LoadProfileError, match="Duplicate"):
        parse(artificial_csv(duplicate=(1, "WT", 0)))


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "not-a-number"])
def test_parser_rejects_invalid_values(value):
    with pytest.raises(LoadProfileError):
        parse(artificial_csv(replacement=value))
