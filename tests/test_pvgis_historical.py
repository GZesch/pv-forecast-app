from datetime import datetime, timedelta, timezone
from math import inf

import httpx
import pytest

from backend.pv_economics.pvgis import (
    PVGISError, PVGISHistoricalClient, PVGISResponseError,
    PVGISTemporaryError, PVGISTimeoutError, parse_pvgis_historical,
    pvgis_series_azimuth,
)
from backend.pv_economics.weather import WeatherDataError


def payload(start_year=2019, end_year=2019):
    rows = []
    start = datetime(start_year, 1, 1)
    end = datetime(end_year + 1, 1, 1)
    stamp = start
    while stamp < end:
        rows.append({"time": stamp.strftime("%Y%m%d:%H%M"), "Gb(i)": 400,
                     "Gd(i)": 80, "Gr(i)": 10, "T2m": 15, "WS10m": 2})
        stamp += timedelta(hours=1)
    return {"inputs": {"meteo_data": {"radiation_db": "PVGIS-SARAH3",
            "year_min": start_year, "year_max": end_year}},
            "outputs": {"hourly": rows}}


@pytest.mark.parametrize(("model", "pvgis"),
    [(0, -180), (90, -90), (180, 0), (270, 90), (360, -180)])
def test_seriescalc_azimuth_conversion(model, pvgis):
    assert pvgis_series_azimuth(model) == pvgis


@pytest.mark.anyio
async def test_adapter_uses_surface_specific_seriescalc_parameters():
    async def handler(request):
        assert request.url.path == "/seriescalc"
        assert request.url.params["raddatabase"] == "PVGIS-SARAH3"
        assert request.url.params["pvcalculation"] == "0"
        assert request.url.params["components"] == "1"
        assert request.url.params["angle"] == "30"
        assert request.url.params["aspect"] == "-90.0"
        assert request.url.params["startyear"] == "2019"
        assert request.url.params["endyear"] == "2019"
        return httpx.Response(200, json=payload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await PVGISHistoricalClient(
            base_url="https://example.test/seriescalc", client=client,
            start_year=2019, end_year=2019,
        ).fetch(52.5, 13.4, tilt_deg=30, azimuth_deg=90)
    assert result.metadata.radiation_database == "PVGIS-SARAH3"
    assert result.metadata.api_endpoint.endswith("/seriescalc")
    assert [year.source_year for year in result.years] == [2019]
    assert (result.metadata.source_start_year,
            result.metadata.source_end_year) == (2019, 2019)


@pytest.mark.anyio
async def test_adapter_rejects_truncated_requested_period():
    async def handler(request):
        return httpx.Response(200, json=payload(2019, 2019))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PVGISResponseError, match="exact requested period"):
            await PVGISHistoricalClient(
                client=client, start_year=2019, end_year=2020,
            ).fetch(50, 8, tilt_deg=30, azimuth_deg=180)


@pytest.mark.anyio
async def test_adapter_rejects_metadata_actual_year_contradiction():
    data = payload(2019, 2019)
    data["inputs"]["meteo_data"]["year_max"] = 2020
    async def handler(request):
        return httpx.Response(200, json=data)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PVGISResponseError, match="omits"):
            await PVGISHistoricalClient(
                client=client, start_year=2019, end_year=2020,
            ).fetch(50, 8, tilt_deg=30, azimuth_deg=180)


@pytest.mark.anyio
@pytest.mark.parametrize(("handler", "error"), [
    (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("late", request=request)), PVGISTimeoutError),
    (lambda request: (_ for _ in ()).throw(httpx.ConnectError("down", request=request)), PVGISError),
    (lambda request: httpx.Response(529), PVGISTemporaryError),
    (lambda request: httpx.Response(200, content=b"invalid"), PVGISResponseError),
    (lambda request: httpx.Response(200, json={}), PVGISResponseError),
])
async def test_adapter_fails_closed(handler, error):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error):
            await PVGISHistoricalClient(client=client).fetch(
                50, 8, tilt_deg=30, azimuth_deg=180)


def test_normal_and_leap_year_are_normalized_to_8760_hours():
    result = parse_pvgis_historical(payload(2019, 2020), 50, 8,
                                    retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert [len(year.hours) for year in result.years] == [8760, 8760]
    leap = result.years[1]
    assert not any(hour.timestamp.month == 2 and hour.timestamp.day == 29
                   for hour in leap.hours)
    assert leap.hours[-1].timestamp == datetime(2001, 12, 31, 23, tzinfo=timezone.utc)
    assert result.metadata.source_period == "2019-2020"
    assert "29 February" in result.metadata.leap_day_normalization


@pytest.mark.parametrize("mutate", [
    lambda rows: rows.pop(10),
    lambda rows: rows.insert(10, dict(rows[10])),
])
def test_gaps_and_duplicates_are_rejected(mutate):
    data = payload()
    mutate(data["outputs"]["hourly"])
    with pytest.raises(WeatherDataError, match="incomplete or duplicated"):
        parse_pvgis_historical(data, 50, 8)


@pytest.mark.parametrize(("field", "value"),
    [("Gb(i)", -1), ("Gd(i)", inf), ("Gr(i)", -1), ("WS10m", -1)])
def test_invalid_physical_values_are_rejected(field, value):
    data = payload()
    data["outputs"]["hourly"][0][field] = value
    with pytest.raises(WeatherDataError):
        parse_pvgis_historical(data, 50, 8)


def test_missing_hourly_field_is_rejected():
    data = payload()
    del data["outputs"]["hourly"][0]["Gb(i)"]
    with pytest.raises(WeatherDataError, match="missing or invalid"):
        parse_pvgis_historical(data, 50, 8)


@pytest.mark.anyio
async def test_adapter_rejects_invalid_coordinates_before_request():
    async def handler(request):
        raise AssertionError("No request expected")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PVGISError, match="Coordinates"):
            await PVGISHistoricalClient(client=client).fetch(
                91, 8, tilt_deg=30, azimuth_deg=180)
