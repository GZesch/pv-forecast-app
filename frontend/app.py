import os
from html import escape

import httpx
import streamlit as st

from api_errors import response_error_message
from forecast_response import forecast_warning
from installation_display import format_installation_location, location_columns
from plant_display import calculate_total_peak_power
from time_display import (
    FORECAST_VIEW_DAYS,
    create_hourly_energy_chart,
    create_hourly_chart,
    filter_component_series_by_days,
    filter_forecast_rows_by_days,
    format_german_date,
    format_german_datetime,
    summarize_daily_power,
    tick_interval_for_view_days,
)
from session_identity import DEFAULT_USER_CODE, stable_session_id_from_code

st.set_page_config(page_title="PV Forecast", page_icon="☀️", layout="wide")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 5.0

if "user_code" not in st.session_state:
    st.session_state["user_code"] = DEFAULT_USER_CODE

with st.sidebar:
    st.subheader("Projekt-/Nutzercode")
    user_code_input = st.text_input(
        "Code",
        value=st.session_state["user_code"],
        help="Mit diesem Code findest du deine Anlagen später wieder.",
    )
    st.caption(
        "Mit diesem Code findest du deine Anlagen später wieder. "
        "Er ist kein Passwort und ersetzt kein Login."
    )

normalized_session_id = stable_session_id_from_code(user_code_input)
st.session_state["user_code"] = user_code_input
st.session_state["session_id"] = str(normalized_session_id)


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


def api_put(
    path: str, *, json: dict, timeout: float = REQUEST_TIMEOUT
) -> httpx.Response:
    return httpx.put(
        f"{API_BASE_URL}{path}",
        json=json,
        headers=api_headers(),
        timeout=timeout,
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
updated_name = st.session_state.pop("updated_installation_name", None)
if updated_name:
    st.success(f"Anlage „{updated_name}“ wurde aktualisiert.")
updated_plant_name = st.session_state.pop("updated_plant_name", None)
if updated_plant_name:
    st.success(f"Kraftwerk „{updated_plant_name}“ wurde aktualisiert.")

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
def confirm_installation_delete(installation: dict, table_key: str) -> None:
    st.warning(f"Soll die Anlage „{installation['name']}“ wirklich gelöscht werden?")
    cancel_column, delete_column = st.columns(2)
    with cancel_column:
        if st.button("Abbrechen", use_container_width=True):
            st.session_state.pop(table_key, None)
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
                "pv_forecast_warning",
                "pv_forecast_target_key",
            ):
                st.session_state.pop(key, None)
            st.session_state["deleted_installation_name"] = installation["name"]
            st.session_state.pop(table_key, None)
            st.rerun()


@st.dialog("Anlage bearbeiten")
def edit_installation_dialog(installation: dict, table_key: str) -> None:
    installation_id = installation["id"]
    name = st.text_input(
        "Name",
        value=installation["name"],
        key=f"edit-name-{installation_id}",
    )
    location = st.text_input(
        "Standort / Ort",
        value=format_installation_location(installation),
        key=f"edit-location-{installation_id}",
        help="Bei einer Änderung wird der neue Standort erneut geocodiert.",
    )
    peak_power_kwp = st.number_input(
        "Leistung (kWp)",
        min_value=0.01,
        value=float(installation["peak_power_kwp"]),
        step=0.1,
        key=f"edit-power-{installation_id}",
    )
    current_orientation = orientation_from_azimuth(installation["azimuth"])
    orientation = st.selectbox(
        "Ausrichtung",
        options=list(ORIENTATIONS),
        index=list(ORIENTATIONS).index(current_orientation),
        key=f"edit-orientation-{installation_id}",
    )
    tilt = st.slider(
        "Neigung (°)",
        min_value=0,
        max_value=90,
        value=int(round(installation["tilt"])),
        key=f"edit-tilt-{installation_id}",
    )

    azimuth = ORIENTATIONS[orientation]
    latitude = None
    longitude = None
    if expert_mode:
        st.markdown("**Expertenwerte**")
        latitude_column, longitude_column = st.columns(2)
        with latitude_column:
            latitude = st.number_input(
                "Breitengrad",
                min_value=-90.0,
                max_value=90.0,
                value=float(installation["latitude"]),
                format="%.6f",
                key=f"edit-latitude-{installation_id}",
            )
        with longitude_column:
            longitude = st.number_input(
                "Längengrad",
                min_value=-180.0,
                max_value=180.0,
                value=float(installation["longitude"]),
                format="%.6f",
                key=f"edit-longitude-{installation_id}",
            )
        override_azimuth = st.checkbox(
            "Numerischen Azimut verwenden",
            key=f"edit-override-azimuth-{installation_id}",
        )
        numeric_azimuth = st.number_input(
            "Azimut in Grad",
            min_value=0.0,
            max_value=360.0,
            value=float(installation["azimuth"]),
            step=0.5,
            disabled=not override_azimuth,
            key=f"edit-azimuth-{installation_id}",
        )
        if override_azimuth:
            azimuth = numeric_azimuth

    cancel_column, save_column = st.columns(2)
    with cancel_column:
        if st.button("Abbrechen", key=f"cancel-edit-{installation_id}"):
            st.session_state.pop(table_key, None)
            st.rerun()
    with save_column:
        if st.button(
            "Änderungen speichern",
            type="primary",
            key=f"save-edit-{installation_id}",
        ):
            if not name.strip() or not location.strip():
                st.error("Name und Standort dürfen nicht leer sein.")
                return
            payload = {
                "name": name.strip(),
                "location": location.strip(),
                "peak_power_kwp": peak_power_kwp,
                "azimuth": azimuth,
                "tilt": float(tilt),
            }
            if expert_mode:
                payload["latitude"] = latitude
                payload["longitude"] = longitude
            try:
                response = api_put(
                    f"/installations/{installation_id}", json=payload
                )
                response.raise_for_status()
                updated = response.json()
            except httpx.HTTPStatusError as exc:
                st.error(
                    response_error_message(
                        exc.response, "Die Anlage konnte nicht aktualisiert werden."
                    )
                )
                return
            except (httpx.RequestError, ValueError):
                st.error("Das Backend ist beim Aktualisieren nicht erreichbar.")
                return

            st.session_state["updated_installation_name"] = updated["name"]
            for key in (
                "weather_forecast",
                "weather_installation_id",
                "pv_forecast",
                "pv_daily_energy",
                "pv_forecast_metrics",
                "pv_forecast_components",
                "pv_forecast_warning",
                "pv_forecast_target_key",
            ):
                st.session_state.pop(key, None)
            st.session_state.pop(table_key, None)
            st.rerun()


@st.fragment
def render_installation_table(items: list[dict], show_expert_columns: bool) -> None:
    """Render local table selections without rerunning forecast sections."""
    table_rows = []
    for installation in items:
        displayed_location = location_columns(
            installation, expert_mode=show_expert_columns
        )
        table_row = {
            "Name": installation["name"],
            "Ort": displayed_location["Ort"],
            "Leistung": f"{installation['peak_power_kwp']:.2f} kWp",
            "Ausrichtung": orientation_from_azimuth(installation["azimuth"]),
            "Neigung": f"{installation['tilt']:.1f}°",
            "Erstellt am": format_german_datetime(installation["created_at"]),
        }
        if show_expert_columns:
            table_row.update(
                {
                    "Breitengrad": displayed_location["Breitengrad"],
                    "Längengrad": displayed_location["Längengrad"],
                    "Azimut": f"{installation['azimuth']:.1f}°",
                }
            )
        table_rows.append(table_row)

    mode = "expert" if show_expert_columns else "standard"
    table_key = f"installation-table-scroll-{mode}"
    columns = list(table_rows[0])
    column_widths = {
        column: max(
            len(column),
            *(len(str(row[column])) for row in table_rows),
        )
        + 1
        for column in columns
    }

    st.html(
        f"""
        <style>
        .st-key-{table_key} {{
            overflow-x: auto;
            padding-bottom: 0.25rem;
        }}
        .st-key-{table_key} [data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap;
            inline-size: max-content;
            align-items: center;
        }}
        .st-key-{table_key} .installation-cell {{
            box-sizing: content-box;
            white-space: nowrap;
            overflow: visible;
            line-height: 1.75;
        }}
        .st-key-{table_key} .installation-header {{
            font-weight: 600;
        }}
        .st-key-{table_key} button {{
            padding: 0.15rem 0.4rem;
            min-height: unset;
        }}
        </style>
        """
    )

    def render_cell(value: object, column: str, *, header: bool = False) -> None:
        header_class = " installation-header" if header else ""
        st.html(
            f'<div class="installation-cell{header_class}" '
            f'style="inline-size:{column_widths[column]}ch">'
            f"{escape(str(value))}</div>",
            width="content",
        )

    selected: list[dict] = []
    with st.container(key=table_key):
        with st.container(horizontal=True, gap="small"):
            for column in columns:
                render_cell(column, column, header=True)
            st.html('<div class="installation-header">✏️</div>', width="content")
            st.html('<div class="installation-header">🗑️</div>', width="content")

        for installation, table_row in zip(items, table_rows, strict=True):
            with st.container(
                horizontal=True,
                vertical_alignment="center",
                gap="small",
            ):
                for column in columns:
                    render_cell(table_row[column], column)
                if st.button(
                    "✏️",
                    key=f"edit-installation-{mode}-{installation['id']}",
                    help=f"{installation['name']} bearbeiten",
                ):
                    edit_installation_dialog(installation, table_key)
                delete_key = f"delete-installation-{mode}-{installation['id']}"
                if st.checkbox(
                    "Löschen",
                    key=delete_key,
                    help=f"{installation['name']} zum Löschen auswählen",
                    label_visibility="collapsed",
                ):
                    selected.append(installation)

    if selected:
        st.warning(
            f"Ausgewählte Anlagen löschen? ({len(selected)} ausgewählt)"
        )
        cancel_column, delete_column = st.columns(2)
        with cancel_column:
            if st.button("Abbrechen", key=f"cancel-delete-{mode}"):
                for installation in items:
                    st.session_state.pop(
                        f"delete-installation-{mode}-{installation['id']}", None
                    )
                st.rerun(scope="fragment")
        with delete_column:
            if st.button(
                "Ausgewählte löschen",
                type="primary",
                key=f"delete-selected-{mode}",
            ):
                try:
                    for installation in selected:
                        response = api_delete(f"/installations/{installation['id']}")
                        response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    st.error(
                        response_error_message(
                            exc.response,
                            "Die ausgewählten Anlagen konnten nicht gelöscht werden.",
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
                    "pv_forecast_warning",
                    "pv_forecast_target_key",
                ):
                    st.session_state.pop(key, None)
                st.session_state["deleted_installation_name"] = ", ".join(
                    installation["name"] for installation in selected
                )
                for installation in items:
                    st.session_state.pop(
                        f"delete-installation-{mode}-{installation['id']}", None
                    )
                st.rerun()


with management_right:
    st.header("Vorhandene Anlagen")
    if installations:
        render_installation_table(installations, expert_mode)
    else:
        st.info("Noch keine PV-Anlagen vorhanden.")


@st.dialog("Kraftwerk bearbeiten")
def edit_plant_dialog(plant: dict) -> None:
    plant_id = plant["id"]
    name = st.text_input(
        "Name des Kraftwerks",
        value=plant["name"],
        key=f"edit-plant-name-{plant_id}",
    )
    location = st.text_input(
        "Ort des Kraftwerks",
        value=plant.get("location_label") or "",
        key=f"edit-plant-location-{plant_id}",
    )
    cancel_column, save_column = st.columns(2)
    with cancel_column:
        if st.button("Abbrechen", key=f"cancel-edit-plant-{plant_id}"):
            st.rerun()
    with save_column:
        if st.button(
            "Änderungen speichern",
            type="primary",
            key=f"save-edit-plant-{plant_id}",
        ):
            if not name.strip():
                st.error("Der Name des Kraftwerks darf nicht leer sein.")
                return
            try:
                response = api_put(
                    f"/plants/{plant_id}",
                    json={
                        "name": name.strip(),
                        "location_label": location.strip() or None,
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                st.error(
                    response_error_message(
                        exc.response, "Das Kraftwerk konnte nicht aktualisiert werden."
                    )
                )
                return
            except httpx.RequestError:
                st.error("Das Backend ist beim Aktualisieren nicht erreichbar.")
                return
            st.session_state["updated_plant_name"] = name.strip()
            st.rerun()


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
        header_name, header_location, header_power, header_edit, header_delete = st.columns(
            [1.25, 1.1, 0.85, 0.42, 0.42], gap="small"
        )
        header_name.caption("Name")
        header_location.caption("Ort")
        header_power.caption("Gesamtleistung")
        header_edit.caption("Edit")
        header_delete.caption("Löschen")
        for plant in plants:
            total_peak_power = calculate_total_peak_power(
                plant["id"], installations
            )
            name_column, location_column, power_column, edit_column, delete_column = st.columns(
                [1.25, 1.1, 0.85, 0.42, 0.42], gap="small"
            )
            name_column.write(plant["name"])
            location_column.write(plant.get("location_label") or "Ort nicht angegeben")
            power_column.write(f"{total_peak_power:.2f} kWp")
            if edit_column.button(
                "✏️",
                key=f"edit-plant-{plant['id']}",
                help=f"Kraftwerk {plant['name']} bearbeiten",
                use_container_width=True,
            ):
                edit_plant_dialog(plant)
            if delete_column.button(
                "🗑️",
                key=f"delete-plant-{plant['id']}",
                help=f"Kraftwerk {plant['name']} löschen",
                use_container_width=True,
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
                            "pv_forecast_warning",
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
    with st.form(f"plant-assignment-{assignment_plant_id}"):
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
        save_assignment = st.form_submit_button(
            "Zuordnung speichern", type="primary"
        )

    if save_assignment:
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
    st.session_state.pop("pv_forecast_warning", None)
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
            warning = forecast_warning(forecast_payload)
            if warning:
                st.session_state["pv_forecast_warning"] = warning
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
        if st.session_state.get("pv_forecast_warning"):
            st.session_state.pop("weather_forecast", None)
            st.session_state.pop("weather_installation_id", None)
            st.session_state.pop("weather_details_error", None)
        elif forecast_target_type != "Einzelanlage":
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
    forecast_warning_message = st.session_state.get("pv_forecast_warning")
    if forecast_warning_message:
        st.warning(forecast_warning_message)
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

    st.subheader("PV-Ertrag pro Stunde")
    view_label = st.radio(
        "Zeitraum",
        options=list(FORECAST_VIEW_DAYS),
        index=list(FORECAST_VIEW_DAYS).index("7 Tage"),
        horizontal=True,
    )
    view_days = FORECAST_VIEW_DAYS[view_label]
    visible_forecast = filter_forecast_rows_by_days(pv_forecast, view_days)
    # Plotly-Relayoutdaten aus manuellem Zoom werden in Streamlit nicht
    # zuverlässig serverseitig ausgewertet. Deshalb steuert diese Auswahl die
    # Tick-Dichte bewusst explizit.
    visible_component_series = (
        filter_component_series_by_days(
            st.session_state.get("pv_forecast_components", []), view_days
        )
        if expert_mode and forecast_target_type == "Kraftwerk"
        else []
    )
    st.plotly_chart(
        create_hourly_energy_chart(
            visible_forecast,
            trace_name="Gesamtertrag" if forecast_target_type == "Kraftwerk" else "Ertrag pro Stunde",
            component_series=visible_component_series,
            stack_components=expert_mode and forecast_target_type == "Kraftwerk",
            tick_interval_hours=tick_interval_for_view_days(view_days),
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
