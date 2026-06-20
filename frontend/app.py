import os
from uuid import uuid4

import httpx
import streamlit as st

from api_errors import response_error_message
from installation_display import location_columns
from time_display import (
    create_hourly_chart,
    format_german_date,
    format_german_datetime,
    summarize_daily_power,
)

st.set_page_config(page_title="PV Forecast", page_icon="☀️", layout="wide")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 5.0

if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid4())


def api_headers() -> dict[str, str]:
    return {"X-Session-ID": st.session_state["session_id"]}


def api_get(path: str, *, timeout: float = REQUEST_TIMEOUT) -> httpx.Response:
    return httpx.get(
        f"{API_BASE_URL}{path}", headers=api_headers(), timeout=timeout
    )


def api_post(
    path: str, *, json: dict | None = None, timeout: float = REQUEST_TIMEOUT
) -> httpx.Response:
    return httpx.post(
        f"{API_BASE_URL}{path}",
        json=json,
        headers=api_headers(),
        timeout=timeout,
    )


def api_delete(path: str, *, timeout: float = REQUEST_TIMEOUT) -> httpx.Response:
    return httpx.delete(
        f"{API_BASE_URL}{path}", headers=api_headers(), timeout=timeout
    )

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


def orientation_from_azimuth(azimuth: float) -> str:
    return min(
        ORIENTATIONS,
        key=lambda name: min(
            abs(ORIENTATIONS[name] - azimuth),
            360.0 - abs(ORIENTATIONS[name] - azimuth),
        ),
    )


st.title("☀️ PV Forecast")
st.subheader("PV-Anlagen verwalten und Leistung prognostizieren")

try:
    health_response = api_get("/health")
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

management_left, management_right = st.columns(2, gap="large")

with management_left:
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

        tilt = st.slider(
            "Neigung (°)",
            min_value=0,
            max_value=90,
            value=30,
            help="0° = flach · 30–40° = typisches Schrägdach · 90° = senkrecht",
        )
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
                    create_response = api_post(
                        "/installations",
                        json={
                            "name": name.strip(),
                            "location": location.strip(),
                            "peak_power_kwp": peak_power_kwp,
                            "azimuth": azimuth,
                            "tilt": float(tilt),
                        },
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
    installations_response = api_get("/installations")
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
                response = api_delete(
                    f"/installations/{installation['id']}"
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
                "pv_forecast_components",
                "pv_forecast_target_key",
            ):
                st.session_state.pop(key, None)
            st.session_state["deleted_installation_name"] = installation["name"]
            st.rerun()


with management_right:
    st.header("Vorhandene Anlagen")
    if installations:
        standard_labels = [
            "Name",
            "Ort",
            "Leistung",
            "Ausrichtung",
            "Neigung",
            "Erstellt am",
            "",
        ]
        standard_widths = [1.3, 1.3, 0.9, 1.1, 0.7, 1.4, 0.35]
        if expert_mode:
            labels = standard_labels[:-1] + [
                "Breitengrad",
                "Längengrad",
                "Azimut",
                "",
            ]
            widths = standard_widths[:-1] + [0.9, 0.9, 0.7, 0.35]
        else:
            labels = standard_labels
            widths = standard_widths

        headers = st.columns(widths)
        for column, label in zip(headers, labels, strict=True):
            column.markdown(f"**{label}**")

        for installation in installations:
            row = st.columns(widths)
            displayed_location = location_columns(
                installation, expert_mode=expert_mode
            )
            values = [
                installation["name"],
                displayed_location["Ort"],
                f"{installation['peak_power_kwp']:.2f} kWp",
                orientation_from_azimuth(installation["azimuth"]),
                f"{installation['tilt']:.1f}°",
                format_german_datetime(installation["created_at"]),
            ]
            if expert_mode:
                values.extend(
                    [
                        displayed_location["Breitengrad"],
                        displayed_location["Längengrad"],
                        f"{installation['azimuth']:.1f}°",
                    ]
                )
            for column, value in zip(row, values, strict=False):
                column.write(value)
            if row[-1].button(
                "🗑️",
                key=f"delete-{installation['id']}",
                help=f"Anlage {installation['name']} löschen",
            ):
                confirm_installation_delete(installation)
    else:
        st.info("Noch keine PV-Anlagen vorhanden.")

st.divider()
st.header("Kraftwerke")
plant_left, plant_right = st.columns(2, gap="large")

with plant_left:
    st.subheader("Kraftwerk anlegen")
    plant_name = st.text_input(
        "Name des Kraftwerks", placeholder="z. B. Wohnhaus Gesamt"
    )
    plant_location = st.text_input(
        "Ort des Kraftwerks (optional)", placeholder="z. B. Stockholm"
    )
    if st.button("Kraftwerk speichern"):
        if not plant_name.strip():
            st.error("Bitte einen Namen für das Kraftwerk eingeben.")
        else:
            try:
                response = api_post(
                    "/plants",
                    json={
                        "name": plant_name.strip(),
                        "location_label": plant_location.strip() or None,
                    },
                )
                response.raise_for_status()
                st.success(f"Kraftwerk „{plant_name.strip()}“ wurde angelegt.")
            except httpx.HTTPStatusError as exc:
                st.error(
                    response_error_message(
                        exc.response, "Das Kraftwerk konnte nicht angelegt werden."
                    )
                )
            except httpx.RequestError:
                st.error("Das Backend ist beim Anlegen des Kraftwerks nicht erreichbar.")

try:
    plants_response = api_get("/plants")
    plants_response.raise_for_status()
    plants = plants_response.json()
except (httpx.HTTPError, ValueError) as exc:
    st.error(f"Die Kraftwerke konnten nicht geladen werden: {exc}")
    plants = []

with plant_right:
    st.subheader("Vorhandene Kraftwerke")
    if plants:
        for plant in plants:
            name_column, location_column, action_column = st.columns([1.5, 1.2, 0.35])
            name_column.write(plant["name"])
            location_column.write(plant.get("location_label") or "Ort nicht angegeben")
            if action_column.button(
                "🗑️",
                key=f"delete-plant-{plant['id']}",
                help=f"Kraftwerk {plant['name']} löschen",
            ):
                try:
                    response = api_delete(f"/plants/{plant['id']}")
                    response.raise_for_status()
                    if st.session_state.get("pv_forecast_target_key") == f"plant:{plant['id']}":
                        for key in (
                            "pv_forecast",
                            "pv_daily_energy",
                            "pv_forecast_metrics",
                            "pv_forecast_components",
                            "pv_forecast_target_key",
                        ):
                            st.session_state.pop(key, None)
                    st.rerun()
                except httpx.HTTPStatusError as exc:
                    st.error(
                        response_error_message(
                            exc.response, "Das Kraftwerk konnte nicht gelöscht werden."
                        )
                    )
                except httpx.RequestError:
                    st.error("Das Backend ist beim Löschen nicht erreichbar.")
    else:
        st.info("Noch keine Kraftwerke vorhanden.")

if plants and installations:
    st.subheader("Anlagen zuordnen")
    plants_by_id = {plant["id"]: plant for plant in plants}
    assignment_plant_id = st.selectbox(
        "Kraftwerk auswählen",
        options=list(plants_by_id),
        format_func=lambda plant_id: plants_by_id[plant_id]["name"],
        key="assignment_plant_id",
    )
    assignment_values: dict[str, bool] = {}
    for installation in installations:
        assigned_plant_id = installation.get("plant_id")
        label = installation["name"]
        if assigned_plant_id and assigned_plant_id != assignment_plant_id:
            other_plant = plants_by_id.get(assigned_plant_id)
            if other_plant:
                label += f" (aktuell: {other_plant['name']})"
        assignment_values[installation["id"]] = st.checkbox(
            label,
            value=assigned_plant_id == assignment_plant_id,
            key=f"assign-{assignment_plant_id}-{installation['id']}",
        )

    if st.button("Zuordnung speichern", type="primary"):
        try:
            for installation in installations:
                installation_id = installation["id"]
                assigned_plant_id = installation.get("plant_id")
                should_be_assigned = assignment_values[installation_id]
                if should_be_assigned and assigned_plant_id != assignment_plant_id:
                    response = api_post(
                        f"/plants/{assignment_plant_id}/installations/"
                        f"{installation_id}"
                    )
                    response.raise_for_status()
                elif not should_be_assigned and assigned_plant_id == assignment_plant_id:
                    response = api_delete(
                        f"/plants/{assignment_plant_id}/installations/"
                        f"{installation_id}"
                    )
                    response.raise_for_status()
            st.success("Die Anlagenzuordnung wurde gespeichert.")
            st.rerun()
        except httpx.HTTPStatusError as exc:
            st.error(
                response_error_message(
                    exc.response, "Die Zuordnung konnte nicht gespeichert werden."
                )
            )
        except httpx.RequestError:
            st.error("Das Backend ist beim Speichern der Zuordnung nicht erreichbar.")

st.divider()
st.header("PV-Prognose")

if not installations:
    st.info("Bitte zuerst eine PV-Anlage anlegen, um eine Prognose zu berechnen.")
    st.stop()

installations_by_id = {item["id"]: item for item in installations}
forecast_target_type = (
    st.radio(
        "Prognose für",
        options=("Einzelanlage", "Kraftwerk"),
        horizontal=True,
    )
    if plants
    else "Einzelanlage"
)

selected_installation_id = None
selected_plant_id = None
if forecast_target_type == "Einzelanlage":
    selected_installation_id = st.selectbox(
        "Anlage auswählen",
        options=list(installations_by_id),
        format_func=lambda item_id: installations_by_id[item_id]["name"],
    )
    forecast_path = f"/installations/{selected_installation_id}/pv-forecast"
    forecast_target_key = f"installation:{selected_installation_id}"
    forecast_button_label = "Prognose berechnen"
else:
    plants_by_id = {plant["id"]: plant for plant in plants}
    selected_plant_id = st.selectbox(
        "Kraftwerk auswählen",
        options=list(plants_by_id),
        format_func=lambda plant_id: plants_by_id[plant_id]["name"],
    )
    forecast_path = f"/plants/{selected_plant_id}/pv-forecast"
    forecast_target_key = f"plant:{selected_plant_id}"
    forecast_button_label = "Gesamtprognose berechnen"

if st.button(forecast_button_label, type="primary"):
    try:
        with st.spinner("Prognose wird berechnet …"):
            forecast_response = api_get(
                forecast_path,
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
            st.session_state["pv_forecast_components"] = forecast_payload.get(
                "components", []
            )
            st.session_state["pv_forecast_target_key"] = forecast_target_key
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
        if forecast_target_type != "Einzelanlage":
            st.session_state.pop("weather_forecast", None)
            st.session_state.pop("weather_installation_id", None)
            st.session_state.pop("weather_details_error", None)
        else:
            try:
                weather_response = api_get(
                    f"/installations/{selected_installation_id}/weather-forecast",
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
stored_forecast_target_key = st.session_state.get("pv_forecast_target_key")
forecast_is_selected = (
    bool(pv_forecast) and stored_forecast_target_key == forecast_target_key
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

    st.subheader(
        "Summierte PV-Leistung"
        if forecast_target_type == "Kraftwerk"
        else "Prognostizierte PV-Leistung"
    )
    component_series = (
        st.session_state.get("pv_forecast_components", [])
        if expert_mode and forecast_target_type == "Kraftwerk"
        else []
    )
    st.plotly_chart(
        create_hourly_chart(
            pv_forecast,
            value_key="predicted_power_kw",
            trace_name="Gesamtleistung" if forecast_target_type == "Kraftwerk" else "PV-Leistung",
            y_axis_title="Leistung (kW)",
            additional_series=component_series,
        ),
        use_container_width=True,
        config={"displayModeBar": False},
    )
else:
    st.info("Wähle ein Prognoseziel aus und berechne seine Prognose.")

if expert_mode:
    with st.expander("Technische Details anzeigen", expanded=False):
        if forecast_target_type == "Einzelanlage":
            selected_installation = installations_by_id[selected_installation_id]
            st.write(
                f"Azimut: {selected_installation['azimuth']:.1f}° · "
                f"Neigung: {selected_installation['tilt']:.1f}°"
            )
        else:
            component_names = [
                component["name"]
                for component in st.session_state.get("pv_forecast_components", [])
            ]
            st.write(
                "Enthaltene Anlagen: "
                + (", ".join(component_names) if component_names else "noch nicht geladen")
            )

        weather_forecast = st.session_state.get("weather_forecast", [])
        weather_installation_id = st.session_state.get("weather_installation_id")
        if (
            forecast_target_type == "Einzelanlage"
            and weather_forecast
            and weather_installation_id == selected_installation_id
        ):
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
        elif forecast_target_type == "Einzelanlage" and st.session_state.get("weather_details_error"):
            st.warning(st.session_state["weather_details_error"])

        if forecast_is_selected:
            st.markdown("#### Rohdaten")
            st.json(
                {
                    "forecast": {
                        "hourly": pv_forecast,
                        "daily": st.session_state.get("pv_daily_energy", []),
                        "metrics": st.session_state.get("pv_forecast_metrics", {}),
                        "components": st.session_state.get("pv_forecast_components", []),
                    },
                    "weather": weather_forecast,
                },
                expanded=False,
            )

if expert_mode and forecast_target_type == "Einzelanlage":
    st.divider()
    with st.expander("Forecast-Historie", expanded=False):
        try:
            history_response = api_get(
                f"/installations/{selected_installation_id}/forecast-history",
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
                    f"{format_german_date(day['date'])}: "
                    f"{day['daily_energy_kwh']:.2f} kWh"
                    for day in run["daily"]
                )
                history_table.append(
                    {
                        "Erstellungszeitpunkt": format_german_datetime(
                            run["created_at"]
                        ),
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
