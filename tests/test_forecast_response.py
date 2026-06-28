from frontend.forecast_response import forecast_warning


def test_frontend_extracts_forecast_warning() -> None:
    warning = (
        "Der Wetterdienst hat heute sein Tageslimit erreicht. "
        "Es wird die zuletzt gespeicherte Prognose angezeigt."
    )

    assert forecast_warning({"warning": f"  {warning}  "}) == warning
    assert forecast_warning({"warning": None}) is None
    assert forecast_warning({}) is None
