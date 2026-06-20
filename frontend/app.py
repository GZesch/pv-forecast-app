import os

import httpx
import streamlit as st

from time_display import (
    create_hourly_chart,
    format_german_date,
    format_german_datetime,
    summarize_daily_power,
)


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 5.0

ORIENTATIONS = {
    "Nord": 0.0,
    "Nordnordost": 22.5,
    "Nordost": 45.0,
    "Ostnordost": 67.5,
    "Ost": 90.0,
    "Ostsüdost": 112.5,
    "Südost": 135.0,
    "Südsüdost": 157.5,
    "Süd": 180.0,
    "Südsüdwest": 202.5,
    "Südwest": 225.0,
    "Westsüdwest": 247.5,
    "West": 270.0,
    "Westnordwest": 292.5,
    "Nordwest": 315.0,
    "Nordnordwest": 337.5,
}
UNFAVORABLE_ORIENTATIONS = {
    "Westnordwest",
    "Nordwest",
    "Nordnordwest",
    "Nord",
    "Nordnordost",
    "Nordost",
}


def response_error_message(response: httpx.Response, fallback: str) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    return detail or fallback


def orientation_from_azimuth(azimuth: float) -> str:
    return min(
        ORIENTATIONS,
        key=lambda name: min(
            abs(ORIENTATIONS[name] - azimuth),
            360.0 - abs(ORIENTATIONS[name] - azimuth),
        ),
    )


st.set_page_config(page_title="PV Forecast", page_icon="☀️", layout="wide")
st.title("☀️ PV Forecast")
st.subheader("PV-Anlagen verwalten und Leistung prognostizieren")

try:
    health_response = httpx.get(f"{API_BASE_URL}/health", timeout=REQUEST_TIMEOUT)
    health_response.raise_for_status()
    backend_available = health_response.json().get("status") == "ok"
except (httpx.HTTPError, ValueError):
    backend_available = False

if not backend_available:
    st.error("Das Backend ist derzeit nicht erreichbar.")
    st.stop()

deleted_name = st.session_state.pop("deleted_installation_name", None)
if deleted_name:
    st.success(f"Anlage „{deleted_name}“ wurde gelöscht.")

expert_mode = st.toggle(
    "Expertenmodus",
    help="Zeigt technische Eingaben, Wetterdetails und API-Rohdaten an.",
)

st.header("Neue Anlage anlegen")
with st.container(border=True):
    name = st.text_input("Name", placeholder="z. B. Hausdach Süd")
    location = st.text_input(
        "Standort",
        placeholder="z. B. München oder Marienplatz 1, München",
        help="Der Standort wird über OpenStreetMap automatisch in Koordinaten umgewandelt.",
    )
    st.caption(
        "Geocoding: [© OpenStreetMap-Mitwirkende](https://www.openstreetmap.org/copyright)"
    )

    orientation_column, tilt_column, power_column = st.columns(3)
    with orientation_column:
        orientation = st.selectbox(
            "Ausrichtung",
            options=list(ORIENTATIONS),
            index=list(ORIENTATIONS).index("Süd"),
            help="Himmelsrichtung, in die die Modulfläche zeigt.",
        )
        if orientation in UNFAVORABLE_ORIENTATIONS:
            st.caption(
                "⚠️ Diese Ausrichtung ist für PV meist ungünstig. "
                "Die Prognose wird trotzdem berechnet."
            )
    with tilt_column:
        tilt = st.slider(
            "Neigung (°)",
            min_value=0,
            max_value=90,
            value=30,
            help="0° = flach · 30–40° = typisches Schrägdach · 90° = senkrecht",
        )
    with power_column:
        peak_power_kwp = st.number_input(
            "Spitzenleistung (kWp)", min_value=0.01, value=10.0, step=0.1
        )

    mapped_azimuth = ORIENTATIONS[orientation]
    azimuth = mapped_azimuth
    if expert_mode:
        st.markdown("**Technische Ausrichtung**")
        override_azimuth = st.checkbox("Azimut in Grad überschreiben")
        numeric_azimuth = st.number_input(
            "Azimut in Grad",
            min_value=0.0,
            max_value=360.0,
            value=float(mapped_azimuth),
            step=0.5,
            disabled=not override_azimuth,
            help="Nord = 0°, Ost = 90°, Süd = 180°, West = 270°",
        )
        azimuth = numeric_azimuth if override_azimuth else mapped_azimuth
        st.caption(f"Verwendete Neigung: {tilt}°")

    if st.button("Anlage speichern", type="primary"):
        if not name.strip() or not location.strip():
            st.error("Bitte Name und Standort der Anlage eingeben.")
        else:
            try:
                create_response = httpx.post(
                    f"{API_BASE_URL}/installations",
                    json={
                        "name": name.strip(),
                        "location": location.strip(),
                        "peak_power_kwp": peak_power_kwp,
                        "azimuth": azimuth,
                        "tilt": float(tilt),
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                create_response.raise_for_status()
                st.success(f"Anlage „{name.strip()}“ wurde angelegt.")
            except httpx.HTTPStatusError as exc:
                st.error(
                    response_error_message(
                        exc.response, "Die Anlage konnte nicht gespeichert werden."
                    )
                )
            except httpx.RequestError:
                st.error("Das Backend ist beim Speichern nicht erreichbar.")

try:
    installations_response = httpx.get(
        f"{API_BASE_URL}/installations", timeout=REQUEST_TIMEOUT
    )
    installations_response.raise_for_status()
    installations = installations_response.json()
except (httpx.HTTPError, ValueError) as exc:
    st.error(f"Die Anlagen konnten nicht geladen werden: {exc}")
    installations = []


@st.dialog("Anlage löschen")
def confirm_installation_delete(installation: dict) -> None:
    st.warning(f"Soll die Anlage „{installation['name']}“ wirklich gelöscht werden?")
    cancel_column, delete_column = st.columns(2)
    with cancel_column:
        if st.button("Abbrechen", use_container_width=True):
            st.rerun()
    with delete_column:
        if st.button("Endgültig löschen", type="primary", use_container_width=True):
            try:
                response = httpx.delete(
                    f"{API_BASE_URL}/installations/{installation['id']}",
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                st.error(
                    response_error_message(
                        exc.response, "Die Anlage konnte nicht gelöscht werden."
                    )
                )
                return
            except httpx.RequestError:
                st.error("Das Backend ist beim Löschen nicht erreichbar.")
                return

            for key in (
                "weather_forecast",
                "weather_installation_id",
                "pv_forecast",
                "pv_daily_energy",
                "pv_forecast_metrics",
                "pv_forecast_installation_id",
            ):
                st.session_state.pop(key, None)
            st.session_state["deleted_installation_name"] = installation["name"]
            st.rerun()


st.header("Vorhandene Anlagen")
if installations:
    column_widths = [1.6, 1, 1, 1, 0.8, 0.8, 1.5, 0.35]
    headers = st.columns(column_widths)
    for column, label in zip(
        headers,
        (
            "Name",
            "Breitengrad",
            "Längengrad",
            "Leistung",
            "Azimut" if expert_mode else "Ausrichtung",
            "Neigung",
            "Erstellt am",
            "",
        ),
        strict=True,
    ):
        column.markdown(f"**{label}**")

    for installation in installations:
        row = st.columns(column_widths)
        row[0].write(installation["name"])
        row[1].write(f"{installation['latitude']:.5f}")
        row[2].write(f"{installation['longitude']:.5f}")
        row[3].write(f"{installation['peak_power_kwp']:.2f} kWp")
        row[4].write(
            f"{installation['azimuth']:.1f}°"
            if expert_mode
            else orientation_from_azimuth(installation["azimuth"])
        )
        row[5].write(f"{installation['tilt']:.1f}°")
        row[6].write(format_german_datetime(installation["created_at"]))
        if row[7].button(
            "🗑️",
            key=f"delete-{installation['id']}",
            help=f"Anlage {installation['name']} löschen",
        ):
            confirm_installation_delete(installation)
else:
    st.info("Noch keine PV-Anlagen vorhanden.")

st.divider()
st.header("PV-Prognose")

if not installations:
    st.info("Bitte zuerst eine PV-Anlage anlegen, um eine Prognose zu berechnen.")
    st.stop()

installations_by_id = {item["id"]: item for item in installations}
selected_installation_id = st.selectbox(
    "Anlage auswählen",
    options=list(installations_by_id),
    format_func=lambda item_id: installations_by_id[item_id]["name"],
)

if st.button("Prognose berechnen", type="primary"):
    try:
        with st.spinner("Prognose wird berechnet …"):
            forecast_response = httpx.get(
                f"{API_BASE_URL}/installations/"
                f"{selected_installation_id}/pv-forecast",
                timeout=30.0,
            )
            forecast_response.raise_for_status()
            forecast_payload = forecast_response.json()
            if not isinstance(forecast_payload, dict):
                raise ValueError("Unerwartetes Prognoseformat")
            st.session_state["pv_forecast"] = forecast_payload.get("hourly", [])
            st.session_state["pv_daily_energy"] = forecast_payload.get("daily", [])
            st.session_state["pv_forecast_metrics"] = forecast_payload.get(
                "metrics", {}
            )
            st.session_state["pv_forecast_installation_id"] = (
                selected_installation_id
            )
    except httpx.HTTPStatusError as exc:
        st.error(
            response_error_message(
                exc.response, "Die PV-Prognose konnte nicht berechnet werden."
            )
        )
    except ValueError:
        st.error("Das Backend hat ein unerwartetes Prognoseformat geliefert.")
    except httpx.RequestError:
        st.error("Das Backend ist beim Berechnen der Prognose nicht erreichbar.")
    else:
        try:
            weather_response = httpx.get(
                f"{API_BASE_URL}/installations/"
                f"{selected_installation_id}/weather-forecast",
                timeout=20.0,
            )
            weather_response.raise_for_status()
            st.session_state["weather_forecast"] = weather_response.json()
            st.session_state["weather_installation_id"] = selected_installation_id
            st.session_state.pop("weather_details_error", None)
        except (httpx.HTTPError, ValueError):
            st.session_state["weather_details_error"] = (
                "Technische Wetterdetails konnten nicht zusätzlich geladen werden."
            )

pv_forecast = st.session_state.get("pv_forecast", [])
forecast_installation_id = st.session_state.get("pv_forecast_installation_id")
forecast_is_selected = (
    pv_forecast and forecast_installation_id == selected_installation_id
)

if forecast_is_selected:
    daily_summaries = summarize_daily_power(pv_forecast)
    labels = ("Heute", "Morgen", "Übermorgen")
    columns = st.columns(3)
    for column, label, summary in zip(columns, labels, daily_summaries, strict=True):
        with column:
            with st.container(border=True):
                st.markdown(f"### {label}")
                st.caption(format_german_date(summary["date"]))
                energy = summary["energy_kwh"]
                peak = summary["peak_power_kw"]
                peak_time = summary["peak_timestamp"]
                st.metric("Ertrag", f"{energy:.1f} kWh" if energy is not None else "—")
                st.metric("Peak", f"{peak:.1f} kW" if peak is not None else "—")
                st.metric(
                    "Peak-Zeit",
                    peak_time.strftime("%H:%M") if peak_time is not None else "—",
                )

    st.subheader("Prognostizierte PV-Leistung")
    st.plotly_chart(
        create_hourly_chart(
            pv_forecast,
            value_key="predicted_power_kw",
            trace_name="PV-Leistung",
            y_axis_title="Leistung (kW)",
        ),
        use_container_width=True,
        config={"displayModeBar": False},
    )
else:
    st.info("Wähle eine Anlage aus und berechne ihre Prognose.")

if expert_mode:
    with st.expander("Technische Details anzeigen", expanded=False):
        selected_installation = installations_by_id[selected_installation_id]
        st.write(
            f"Azimut: {selected_installation['azimuth']:.1f}° · "
            f"Neigung: {selected_installation['tilt']:.1f}°"
        )
        weather_forecast = st.session_state.get("weather_forecast", [])
        weather_installation_id = st.session_state.get("weather_installation_id")
        if weather_forecast and weather_installation_id == selected_installation_id:
            weather_table = [
                {
                    "Zeitpunkt": format_german_datetime(row["timestamp"]),
                    "Temperatur (°C)": row["temperature_2m"],
                    "Bewölkung (%)": row["cloud_cover"],
                    "Direktstrahlung (W/m²)": row["direct_radiation"],
                    "Diffusstrahlung (W/m²)": row["diffuse_radiation"],
                    "Wind 10 m (km/h)": row["wind_speed_10m"],
                }
                for row in weather_forecast
            ]
            st.markdown("#### Wettertabelle")
            st.dataframe(weather_table, use_container_width=True, hide_index=True)
            st.markdown("#### Direktstrahlung")
            st.plotly_chart(
                create_hourly_chart(
                    weather_forecast,
                    value_key="direct_radiation",
                    trace_name="Direktstrahlung",
                    y_axis_title="Direktstrahlung (W/m²)",
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        elif st.session_state.get("weather_details_error"):
            st.warning(st.session_state["weather_details_error"])
        else:
            st.info("Technische Wetterdetails erscheinen nach der Prognoseberechnung.")

        if forecast_is_selected:
            st.markdown("#### Rohdaten")
            st.json(
                {
                    "forecast": {
                        "hourly": pv_forecast,
                        "daily": st.session_state.get("pv_daily_energy", []),
                        "metrics": st.session_state.get("pv_forecast_metrics", {}),
                    },
                    "weather": weather_forecast,
                },
                expanded=False,
            )

st.divider()
st.subheader("Forecast-Historie")
try:
    history_response = httpx.get(
        f"{API_BASE_URL}/installations/"
        f"{selected_installation_id}/forecast-history",
        timeout=REQUEST_TIMEOUT,
    )
    history_response.raise_for_status()
    forecast_history = history_response.json()
except httpx.HTTPStatusError as exc:
    st.error(
        response_error_message(
            exc.response, "Die Forecast-Historie konnte nicht geladen werden."
        )
    )
    forecast_history = []
except (httpx.RequestError, ValueError):
    st.error("Das Backend ist beim Laden der Forecast-Historie nicht erreichbar.")
    forecast_history = []

if forecast_history:
    history_table = []
    for run in forecast_history:
        daily_yields = " · ".join(
            f"{format_german_date(day['date'])}: {day['daily_energy_kwh']:.2f} kWh"
            for day in run["daily"]
        )
        history_table.append(
            {
                "Erstellungszeitpunkt": format_german_datetime(run["created_at"]),
                "Prognosezeitraum": (
                    f"{format_german_datetime(run['forecast_start'])} – "
                    f"{format_german_datetime(run['forecast_end'])}"
                ),
                "Tagesertrag": daily_yields,
                "Peak-Leistung (kW)": run["peak_power_kw"],
            }
        )
    st.dataframe(history_table, use_container_width=True, hide_index=True)
else:
    st.info("Für diese Anlage sind noch keine Forecasts gespeichert.")
