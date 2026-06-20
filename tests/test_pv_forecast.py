from backend.models import PVForecastRow, WeatherForecastRow
from backend.services.pv_forecast import PVForecastService


def test_pv_forecast_produces_daytime_power_and_zero_at_night() -> None:
    weather = [
        WeatherForecastRow(
            timestamp="2026-03-20T00:00:00Z",
            temperature_2m=15.0,
            cloud_cover=0.0,
            direct_radiation=0.0,
            diffuse_radiation=0.0,
            wind_speed_10m=2.0,
        ),
        WeatherForecastRow(
            timestamp="2026-03-20T12:00:00Z",
            temperature_2m=25.0,
            cloud_cover=5.0,
            direct_radiation=800.0,
            diffuse_radiation=100.0,
            wind_speed_10m=2.0,
        ),
    ]

    result = PVForecastService().calculate(
        latitude=0.0,
        longitude=0.0,
        peak_power_kwp=10.0,
        azimuth=180.0,
        tilt=10.0,
        weather=weather,
    )

    assert len(result) == 2
    assert result[0].predicted_power_kw == 0.0
    assert 0.0 < result[1].predicted_power_kw <= 10.0


def test_daily_energy_sums_hourly_power_by_date() -> None:
    hourly = [
        PVForecastRow(
            timestamp="2026-06-20T10:00:00Z", predicted_power_kw=2.5
        ),
        PVForecastRow(
            timestamp="2026-06-20T11:00:00Z", predicted_power_kw=3.0
        ),
        PVForecastRow(
            timestamp="2026-06-21T10:00:00Z", predicted_power_kw=1.25
        ),
    ]

    daily = PVForecastService.calculate_daily_energy(hourly)

    assert [row.model_dump(mode="json") for row in daily] == [
        {"date": "2026-06-20", "daily_energy_kwh": 5.5},
        {"date": "2026-06-21", "daily_energy_kwh": 1.25},
    ]


def test_forecast_metrics_return_peak_and_first_peak_timestamp() -> None:
    hourly = [
        PVForecastRow(
            timestamp="2026-06-20T10:00:00Z", predicted_power_kw=3.5
        ),
        PVForecastRow(
            timestamp="2026-06-20T11:00:00Z", predicted_power_kw=7.25
        ),
        PVForecastRow(
            timestamp="2026-06-20T12:00:00Z", predicted_power_kw=7.25
        ),
    ]

    metrics = PVForecastService.calculate_metrics(hourly)

    assert metrics.peak_power_kw == 7.25
    assert metrics.peak_timestamp.isoformat() == "2026-06-20T11:00:00+00:00"
