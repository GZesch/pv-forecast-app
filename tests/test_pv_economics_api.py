import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.main as main_module
import backend.services.pv_economics as service_module
from backend.main import app
from backend.pv_economics.load_profiles import LoadProfileMetadata, LoadProfileResult
from backend.pv_economics.load_profiles import H25DataUnavailableError
from backend.pv_economics.eeg import EEGTariffError
from backend.pv_economics.pvgis import (
    PVGISResponseError, PVGISTemporaryError, PVGISTimeoutError,
)
from backend.pv_economics_api_models import PVEconomicsRequest
from backend.services.pv_economics import PVEconomicsService


def request_payload(**changes):
    payload = {
        "latitude": 52.5, "longitude": 13.4, "federal_state": "BE",
        "annual_consumption_kwh": 8, "profile_kind": "h25",
        "pv_surfaces": [
            {"identifier": "south", "peak_power_kwp": 6, "azimuth_deg": 180,
             "tilt_deg": 30, "inverter_efficiency": .96,
             "system_loss_fraction": .05},
            {"identifier": "west", "peak_power_kwp": 4, "azimuth_deg": 270,
             "tilt_deg": 20, "inverter_efficiency": .96,
             "system_loss_fraction": .05},
        ],
        "battery": {"usable_capacity_kwh": 4},
        "electricity_price_eur_per_kwh": .3,
        "commissioning_date": "2026-03-01",
        "pv_investment_eur": 10, "battery_incremental_investment_eur": 4,
        "assumptions": {"years": 2},
    }
    payload.update(changes)
    return payload


class FakePVGIS:
    calls = 0

    async def fetch(self, latitude, longitude):
        self.calls += 1
        return SimpleNamespace(metadata=SimpleNamespace(
            radiation_database="PVGIS-SARAH3", source_period="2005-2023",
            selected_months=((1, 2008), (2, 2009)),
            retrieved_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            api_endpoint="mock-pvgis", irradiance_time_offset_hours=.5))


def fake_load(*args, **kwargs):
    metadata = LoadProfileMetadata("artificial_test_data", "mock-load", "test",
        "mock", "mock", "mock", "test")
    return LoadProfileResult("mock", "mock", (), (0.0, 8.0), 8.0, metadata)


@pytest.mark.anyio
async def test_service_orchestrates_mocked_adapters_without_hourly_response(monkeypatch):
    def fake_plant(weather, surfaces):
        assert len(surfaces) == 2
        parts = tuple(SimpleNamespace(ac_energy_kwh=(10.0, 0.0)) for _ in surfaces)
        return SimpleNamespace(total_peak_power_kwp=10.0, surfaces=parts)

    monkeypatch.setattr(service_module, "calculate_pv_plant", fake_plant)
    service = PVEconomicsService(
        pvgis_client=FakePVGIS(), load_provider=fake_load,
        h25_csv_path="unused", clock=lambda: datetime(2026, 7, 1, tzinfo=timezone.utc))
    response = await service.calculate(PVEconomicsRequest.model_validate(request_payload()))
    body = response.model_dump(mode="json")
    assert body["metadata"]["weather_source"] == "mock-pvgis"
    assert body["metadata"]["profile"]["source_xlsx_sha256"] == "mock"
    assert body["metadata"]["weather"]["radiation_database"] == "PVGIS-SARAH3"
    assert body["metadata"]["weather"]["irradiance_time_offset_hours"] == .5
    assert body["first_year"]["pv_with_battery"] is not None
    assert body["feed_in_limit_comparison"]["limit_kw"] == 6
    assert body["metadata"]["used_assumptions"]["years"] == 2
    assert "hourly" not in str(body)

    without_battery = request_payload(
        battery=None, battery_incremental_investment_eur=None)
    response = await service.calculate(PVEconomicsRequest.model_validate(without_battery))
    assert response.first_year["pv_with_battery"] is None

    package_only = request_payload(
        pv_investment_eur=None, battery_incremental_investment_eur=None,
        package_investment_eur=14,
        assumptions={"years": 2, "pv_operating_cost_year1_eur": 1})
    response = await service.calculate(PVEconomicsRequest.model_validate(package_only))
    assert response.economics["package"]["metrics"]["available"]
    assert not response.economics["pv"]["metrics"]["available"]


@pytest.mark.anyio
async def test_resolved_pv_investment_drives_default_opex(monkeypatch):
    monkeypatch.setattr(service_module, "calculate_pv_plant", lambda weather, surfaces:
        SimpleNamespace(total_peak_power_kwp=10,
                        surfaces=(SimpleNamespace(ac_energy_kwh=(10.0, 0.0)),)))
    service = PVEconomicsService(pvgis_client=FakePVGIS(), load_provider=fake_load,
                                 h25_csv_path="unused")
    data = request_payload(
        pv_surfaces=[request_payload()["pv_surfaces"][0]],
        pv_investment_eur=None, battery_incremental_investment_eur=5000,
        package_investment_eur=20000)
    response = await service.calculate(PVEconomicsRequest.model_validate(data))
    assert response.metadata["used_assumptions"]["resolved_pv_operating_cost_year1_eur"] == 150
    assert response.economics["pv"]["annual"][0]["operating_cost_eur"] == 150
    assert "PACKAGE_PRICE_NOT_SPLIT" not in {item["code"] for item in response.warnings}


@pytest.mark.anyio
async def test_package_only_requires_explicit_pv_opex(monkeypatch):
    monkeypatch.setattr(service_module, "calculate_pv_plant", lambda weather, surfaces:
        SimpleNamespace(total_peak_power_kwp=10,
                        surfaces=(SimpleNamespace(ac_energy_kwh=(10.0, 0.0)),)))
    service = PVEconomicsService(pvgis_client=FakePVGIS(), load_provider=fake_load,
                                 h25_csv_path="unused")
    data = request_payload(pv_investment_eur=None,
                           battery_incremental_investment_eur=None,
                           package_investment_eur=20000)
    with pytest.raises(Exception, match="operating costs explicitly"):
        await service.calculate(PVEconomicsRequest.model_validate(data))


@pytest.mark.anyio
async def test_missing_h25_prevents_pvgis_call():
    client = FakePVGIS()
    def unavailable(*args, **kwargs):
        raise H25DataUnavailableError("missing")
    service = PVEconomicsService(pvgis_client=client, load_provider=unavailable,
                                 h25_csv_path="missing")
    with pytest.raises(H25DataUnavailableError):
        await service.calculate(PVEconomicsRequest.model_validate(request_payload()))
    assert client.calls == 0


class StubService:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    async def calculate(self, data):
        if self.error:
            raise self.error
        return self.result


def minimal_response():
    return {"metadata": {}, "first_year": {}, "economics": {},
            "feed_in_limit_comparison": {}, "warnings": [], "disclaimers": []}


def test_endpoint_is_stateless_and_requires_no_session(monkeypatch):
    monkeypatch.setattr(main_module, "pv_economics_service",
                        StubService(minimal_response()))
    with TestClient(app) as client:
        response = client.post("/pv-economics/calculate", json=request_payload())
    assert response.status_code == 200
    assert "hourly" not in response.text


@pytest.mark.parametrize(("error", "status"), [
    (PVGISTimeoutError("timeout"), 503),
    (PVGISTemporaryError("overloaded"), 503),
    (PVGISResponseError("schema"), 502),
    (H25DataUnavailableError("missing"), 503),
    (EEGTariffError("unknown tariff period"), 422),
])
def test_endpoint_maps_pvgis_failures(monkeypatch, error, status):
    monkeypatch.setattr(main_module, "pv_economics_service", StubService(error=error))
    with TestClient(app) as client:
        response = client.post("/pv-economics/calculate", json=request_payload())
    assert response.status_code == status
    assert "52.5" not in response.text


def test_invalid_request_returns_422_without_service_call():
    with TestClient(app) as client:
        response = client.post("/pv-economics/calculate", json=request_payload(pv_surfaces=[]))
    assert response.status_code == 422


@pytest.mark.parametrize("assumptions", [
    {"years": 2, "max_feed_in_power_kw": 0, "feed_in_limit_years": 0},
    {"years": 2, "feed_in_limit_years": 1},
    {"years": 2, "max_feed_in_percent": 0, "feed_in_limit_years": 3},
    {"years": 2, "max_feed_in_percent": 60, "max_feed_in_power_kw": 6,
     "feed_in_limit_years": 1},
])
def test_invalid_feed_in_limit_combinations_return_422(assumptions):
    with TestClient(app) as client:
        response = client.post("/pv-economics/calculate",
                               json=request_payload(assumptions=assumptions))
    assert response.status_code == 422


def test_zero_feed_in_limit_with_positive_period_is_valid_transport():
    payload = request_payload(assumptions={
        "years": 2, "max_feed_in_power_kw": 0, "feed_in_limit_years": 1})
    assert PVEconomicsRequest.model_validate(payload).assumptions.max_feed_in_power_kw == 0


@pytest.mark.parametrize("surface_change", [
    {"constant_shading_factor": .2, "shading_matrix": [[0.0] * 24 for _ in range(12)]},
    {"constant_shading_factor": 0, "shading_matrix": [[float("nan")] * 24 for _ in range(12)]},
])
def test_invalid_shading_combinations_return_422(surface_change):
    surface = {**request_payload()["pv_surfaces"][0], **surface_change}
    with TestClient(app) as client:
        payload = request_payload(pv_surfaces=[surface])
        if any(value != value for row in surface_change["shading_matrix"]
               for value in row):
            response = client.post(
                "/pv-economics/calculate", content=json.dumps(payload),
                headers={"content-type": "application/json"})
        else:
            response = client.post("/pv-economics/calculate", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("battery", [
    {"usable_capacity_kwh": 4, "degradation_kind": "standard",
     "warranty_years": 10},
    {"usable_capacity_kwh": 4, "degradation_kind": "warranty",
     "residual_capacity_fraction": .8, "warranty_years": 10},
    {"usable_capacity_kwh": 4, "degradation_kind": "warranty",
     "residual_capacity_fraction": .8, "warranty_years": 10,
     "warranted_efc": 1000, "warranted_throughput_kwh": 5000},
])
def test_invalid_battery_degradation_fields_return_422(battery):
    with TestClient(app) as client:
        response = client.post("/pv-economics/calculate",
                               json=request_payload(battery=battery))
    assert response.status_code == 422
