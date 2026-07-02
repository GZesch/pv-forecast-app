from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.pv_economics.pvgis import (
    PVGISError,
    PVGISResponseError,
    PVGISTMYClient,
    PVGISTemporaryError,
    PVGISTimeoutError,
    parse_pvgis_tmy,
)
from backend.pv_economics.weather import WeatherDataError


def payload():
    start = datetime(2001, 1, 1)
    rows = []
    for index in range(8760):
        stamp = start + timedelta(hours=index)
        # Demonstrate that source months may originate in distinct years.
        source_year = 2009 if stamp.month <= 6 else 2010
        rows.append({"time": stamp.replace(year=source_year).strftime("%Y%m%d:%H%M"),
                     "G(h)": -0.01, "Gb(n)": 0, "Gd(h)": 0,
                     "T2m": -2, "WS10m": 3})
    return {
        "inputs": {
            "location": {"latitude": 52.5, "longitude": 13.4,
                         "irradiance_time_offset": 0.5},
            "meteo_data": {"radiation_db": "PVGIS-SARAH3",
                           "year_min": 2005, "year_max": 2023},
        },
        "outputs": {"tmy_hourly": rows,
                    "months_selected": [
                        {"month": month, "year": 2009 if month <= 6 else 2010}
                        for month in range(1, 13)
                    ]},
    }


def use_timestamp_field(data, field):
    for row in data["outputs"]["tmy_hourly"]:
        row[field] = row.pop("time")
    return data


def test_parse_normalizes_complete_tmy_and_retains_metadata():
    retrieved = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = parse_pvgis_tmy(payload(), 52.5, 13.4, retrieved_at=retrieved)
    assert len(result.hours) == 8760
    assert result.hours[0].timestamp == datetime(2001, 1, 1, tzinfo=timezone.utc)
    assert result.hours[-1].timestamp == datetime(2001, 12, 31, 23, tzinfo=timezone.utc)
    assert result.hours[0].ghi_w_m2 == 0
    assert result.metadata.radiation_database == "PVGIS-SARAH3"
    assert result.metadata.source_period == "2005-2023"
    assert result.metadata.selected_months == tuple(
        (month, 2009 if month <= 6 else 2010) for month in range(1, 13)
    )
    assert result.metadata.irradiance_time_offset_hours == 0.5
    assert result.metadata.retrieved_at == retrieved


def test_accepts_documented_time_field():
    result = parse_pvgis_tmy(payload(), 50, 8)
    assert len(result.hours) == 8760


def test_accepts_observed_time_utc_field():
    result = parse_pvgis_tmy(use_timestamp_field(payload(), "time(UTC)"), 50, 8)
    assert len(result.hours) == 8760


def test_accepts_identical_supported_timestamp_fields():
    data = payload()
    for row in data["outputs"]["tmy_hourly"]:
        row["time(UTC)"] = row["time"]
    result = parse_pvgis_tmy(data, 50, 8)
    assert len(result.hours) == 8760


def test_rejects_conflicting_supported_timestamp_fields():
    data = payload()
    data["outputs"]["tmy_hourly"][0]["time(UTC)"] = "20090101:0100"
    with pytest.raises(WeatherDataError, match="conflicting"):
        parse_pvgis_tmy(data, 50, 8)


def test_rejects_missing_supported_timestamp_field():
    data = payload()
    del data["outputs"]["tmy_hourly"][0]["time"]
    with pytest.raises(WeatherDataError, match="no supported timestamp"):
        parse_pvgis_tmy(data, 50, 8)


def test_rejects_non_string_timestamp():
    data = payload()
    data["outputs"]["tmy_hourly"][0]["time"] = 200901010000
    with pytest.raises(WeatherDataError, match="must be a string"):
        parse_pvgis_tmy(data, 50, 8)


def test_rejects_invalid_timestamp_format():
    data = payload()
    data["outputs"]["tmy_hourly"][0]["time"] = "2009-01-01T00:00"
    with pytest.raises(WeatherDataError, match="missing or invalid fields"):
        parse_pvgis_tmy(data, 50, 8)


@pytest.mark.parametrize("mutation", ["gap", "duplicate", "out_of_order"])
def test_timestamp_sequence_validation_remains_strict(mutation):
    data = payload()
    rows = data["outputs"]["tmy_hourly"]
    if mutation == "gap":
        rows[1]["time"] = "20090101:0130"
    elif mutation == "duplicate":
        rows[1]["time"] = rows[0]["time"]
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(WeatherDataError, match="duplicated|gaps"):
        parse_pvgis_tmy(data, 50, 8)


@pytest.mark.anyio
async def test_adapter_sends_only_required_coordinates_and_parameters():
    async def handler(request):
        assert request.url.path == "/tmy"
        assert request.url.params["lat"] == "52.5"
        assert request.url.params["lon"] == "13.4"
        assert request.url.params["raddatabase"] == "PVGIS-SARAH3"
        assert request.url.params["usehorizon"] == "1"
        assert request.url.params["outputformat"] == "json"
        assert "ExergyPulse" in request.headers["user-agent"]
        return httpx.Response(200, json=payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await PVGISTMYClient(base_url="https://example.test/tmy", client=client).fetch(52.5, 13.4)
    assert len(result.hours) == 8760


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("late", request=request)), PVGISTimeoutError),
        (lambda request: (_ for _ in ()).throw(httpx.ConnectError("down", request=request)), PVGISError),
        (lambda request: httpx.Response(500), PVGISError),
        (lambda request: httpx.Response(529), PVGISTemporaryError),
        (lambda request: httpx.Response(200, content=b"not-json"), PVGISResponseError),
        (lambda request: httpx.Response(200, json={}), PVGISResponseError),
    ],
)
async def test_adapter_maps_external_failures(handler, error):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error):
            await PVGISTMYClient(client=client).fetch(50, 8)


def test_rejects_incomplete_and_invalid_weather():
    incomplete = payload()
    incomplete["outputs"]["tmy_hourly"].pop()
    with pytest.raises(WeatherDataError, match="8,760"):
        parse_pvgis_tmy(incomplete, 50, 8)
    invalid = payload()
    invalid["outputs"]["tmy_hourly"][0]["G(h)"] = -1
    with pytest.raises(WeatherDataError, match="negative"):
        parse_pvgis_tmy(invalid, 50, 8)


def test_clamps_tiny_negative_wind_but_rejects_material_negative_wind():
    data = payload()
    data["outputs"]["tmy_hourly"][0]["WS10m"] = -0.08
    assert parse_pvgis_tmy(data, 50, 8).hours[0].wind_speed_m_s == 0

    data["outputs"]["tmy_hourly"][0]["WS10m"] = -0.11
    with pytest.raises(WeatherDataError, match="materially negative"):
        parse_pvgis_tmy(data, 50, 8)


@pytest.mark.parametrize("months", [
    [{"month": month, "year": 2010} for month in range(1, 12)],
    ([{"month": month, "year": 2010} for month in range(1, 12)]
     + [{"month": 11, "year": 2011}]),
    ([{"month": month, "year": 2010} for month in range(1, 12)]
     + [{"month": 13, "year": 2011}]),
])
def test_rejects_incomplete_duplicate_or_invalid_selected_months(months):
    data = payload()
    data["outputs"]["months_selected"] = months
    with pytest.raises(WeatherDataError, match="every month exactly once"):
        parse_pvgis_tmy(data, 50, 8)


def test_missing_radiation_database_is_not_invented():
    data = payload()
    del data["inputs"]["meteo_data"]["radiation_db"]
    assert parse_pvgis_tmy(data, 50, 8).metadata.radiation_database is None
