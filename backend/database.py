import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import duckdb

from backend.models import (
    InstallationCreate,
    InstallationUpdate,
    PlantCreate,
    PlantUpdate,
    PVForecastResponse,
)


class ForecastPersistenceError(RuntimeError):
    """Raised when forecast history cannot be persisted or loaded."""


def get_database_path() -> Path:
    """Return the configured DuckDB file path."""
    return Path(os.getenv("DATABASE_PATH", "database/pv_forecast.duckdb"))


def initialize_database() -> None:
    """Create the database directory and initial schema."""
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pv_forecasts (
                forecast_time TIMESTAMP PRIMARY KEY,
                power_kw DOUBLE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_runs (
                id UUID PRIMARY KEY,
                installation_id UUID,
                target_type TEXT,
                target_id UUID,
                created_at TIMESTAMPTZ NOT NULL,
                forecast_start TIMESTAMPTZ NOT NULL,
                forecast_end TIMESTAMPTZ NOT NULL,
                hourly_json TEXT,
                daily_energy_json TEXT NOT NULL,
                peak_power_kw DOUBLE NOT NULL,
                peak_timestamp TIMESTAMPTZ NOT NULL,
                source TEXT
            )
            """
        )
        forecast_run_info = connection.execute(
            "PRAGMA table_info('forecast_runs')"
        ).fetchall()
        forecast_run_columns = {row[1] for row in forecast_run_info}
        if "target_type" not in forecast_run_columns:
            connection.execute(
                "ALTER TABLE forecast_runs ADD COLUMN target_type TEXT"
            )
        if "target_id" not in forecast_run_columns:
            connection.execute(
                "ALTER TABLE forecast_runs ADD COLUMN target_id UUID"
            )
        if "hourly_json" not in forecast_run_columns:
            connection.execute(
                "ALTER TABLE forecast_runs ADD COLUMN hourly_json TEXT"
            )
        if "source" not in forecast_run_columns:
            connection.execute(
                "ALTER TABLE forecast_runs ADD COLUMN source TEXT"
            )
        installation_column = next(
            row for row in forecast_run_info if row[1] == "installation_id"
        )
        if installation_column[3]:
            connection.execute(
                "DROP INDEX IF EXISTS forecast_runs_installation_idx"
            )
            connection.execute(
                "ALTER TABLE forecast_runs ALTER COLUMN installation_id DROP NOT NULL"
            )
        connection.execute(
            """
            UPDATE forecast_runs
            SET
                target_type = coalesce(target_type, 'installation'),
                target_id = coalesce(target_id, installation_id),
                source = coalesce(source, 'fresh')
            WHERE target_type IS NULL OR target_id IS NULL OR source IS NULL
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_points (
                run_id UUID NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                predicted_power_kw DOUBLE NOT NULL,
                PRIMARY KEY (run_id, timestamp)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS forecast_runs_installation_idx
            ON forecast_runs (installation_id, created_at)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS forecast_runs_target_idx
            ON forecast_runs (target_type, target_id, created_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS plants (
                id UUID PRIMARY KEY,
                session_id TEXT NOT NULL,
                name TEXT NOT NULL,
                location_label TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS plants_session_idx
            ON plants (session_id, created_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS installations (
                id UUID PRIMARY KEY,
                session_id UUID NOT NULL,
                plant_id UUID,
                name TEXT NOT NULL,
                location_label TEXT,
                latitude DOUBLE NOT NULL,
                longitude DOUBLE NOT NULL,
                peak_power_kwp DOUBLE NOT NULL,
                azimuth DOUBLE NOT NULL,
                tilt DOUBLE NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        installation_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('installations')"
            ).fetchall()
        }
        if "session_id" not in installation_columns:
            connection.execute(
                "ALTER TABLE installations ADD COLUMN session_id UUID"
            )
        if "location_label" not in installation_columns:
            connection.execute(
                "ALTER TABLE installations ADD COLUMN location_label TEXT"
            )
        if "plant_id" not in installation_columns:
            connection.execute(
                "ALTER TABLE installations ADD COLUMN plant_id UUID"
            )
        connection.execute(
            """
            UPDATE installations
            SET location_label = printf('%.2f, %.2f', latitude, longitude)
            WHERE location_label IS NULL OR trim(location_label) = ''
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS installations_plant_idx
            ON installations (plant_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS installations_session_idx
            ON installations (session_id)
            """
        )


INSTALLATION_COLUMNS = """
    id, name, location_label, latitude, longitude,
    peak_power_kwp, azimuth, tilt, created_at, plant_id
"""


def _installation_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "location_label": row[2],
        "latitude": row[3],
        "longitude": row[4],
        "peak_power_kwp": row[5],
        "azimuth": row[6],
        "tilt": row[7],
        "created_at": row[8],
        "plant_id": row[9],
    }


def create_installation(
    data: InstallationCreate,
    latitude: float,
    longitude: float,
    session_id: UUID,
) -> dict[str, Any]:
    installation_id = uuid4()
    created_at = datetime.now()
    # The user's original query is the reliable, human-readable default.
    normalized_location_label = data.location.strip()

    with duckdb.connect(str(get_database_path())) as connection:
        connection.execute(
            """
            INSERT INTO installations (
                id, session_id, name, location_label, latitude, longitude,
                peak_power_kwp, azimuth, tilt, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                installation_id,
                session_id,
                data.name,
                normalized_location_label,
                latitude,
                longitude,
                data.peak_power_kwp,
                data.azimuth,
                data.tilt,
                created_at,
            ],
        )

    return {
        "id": installation_id,
        "name": data.name,
        "location_label": normalized_location_label,
        "latitude": latitude,
        "longitude": longitude,
        "peak_power_kwp": data.peak_power_kwp,
        "azimuth": data.azimuth,
        "tilt": data.tilt,
        "created_at": created_at,
    }


def list_installations(session_id: UUID) -> list[dict[str, Any]]:
    with duckdb.connect(str(get_database_path())) as connection:
        rows = connection.execute(
            f"""
            SELECT {INSTALLATION_COLUMNS}
            FROM installations
            WHERE session_id = ?
            ORDER BY created_at DESC
            """,
            [session_id],
        ).fetchall()

    return [_installation_from_row(row) for row in rows]


def get_installation(
    installation_id: UUID, session_id: UUID
) -> dict[str, Any] | None:
    with duckdb.connect(str(get_database_path())) as connection:
        row = connection.execute(
            f"""
            SELECT {INSTALLATION_COLUMNS}
            FROM installations
            WHERE id = ? AND session_id = ?
            """,
            [installation_id, session_id],
        ).fetchone()

    return _installation_from_row(row) if row else None


def update_installation(
    installation_id: UUID,
    session_id: UUID,
    data: InstallationUpdate,
    latitude: float,
    longitude: float,
) -> dict[str, Any] | None:
    """Update an owned installation and return its current representation."""
    with duckdb.connect(str(get_database_path())) as connection:
        updated = connection.execute(
            """
            UPDATE installations
            SET
                name = ?,
                location_label = ?,
                latitude = ?,
                longitude = ?,
                peak_power_kwp = ?,
                azimuth = ?,
                tilt = ?
            WHERE id = ? AND session_id = ?
            RETURNING id
            """,
            [
                data.name.strip(),
                data.location.strip(),
                latitude,
                longitude,
                data.peak_power_kwp,
                data.azimuth,
                data.tilt,
                installation_id,
                session_id,
            ],
        ).fetchone()

    return get_installation(installation_id, session_id) if updated else None


def delete_installation(installation_id: UUID, session_id: UUID) -> bool:
    """Delete an installation and report whether it existed."""
    with duckdb.connect(str(get_database_path())) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            owned_installation = connection.execute(
                """
                SELECT id FROM installations
                WHERE id = ? AND session_id = ?
                """,
                [installation_id, session_id],
            ).fetchone()
            if owned_installation is None:
                connection.execute("COMMIT")
                return False

            connection.execute(
                """
                DELETE FROM forecast_points
                WHERE run_id IN (
                    SELECT id FROM forecast_runs WHERE installation_id = ?
                )
                """,
                [installation_id],
            )
            connection.execute(
                "DELETE FROM forecast_runs WHERE installation_id = ?",
                [installation_id],
            )
            deleted = connection.execute(
                """
                DELETE FROM installations
                WHERE id = ? AND session_id = ?
                RETURNING id
                """,
                [installation_id, session_id],
            ).fetchone()
            connection.execute("COMMIT")
        except duckdb.Error:
            connection.execute("ROLLBACK")
            raise

    return deleted is not None


def save_forecast_run(
    target_id: UUID,
    forecast: PVForecastResponse,
    *,
    target_type: str = "installation",
    source: str = "fresh",
) -> UUID:
    """Persist one complete forecast run and all of its hourly points."""
    if not forecast.hourly:
        raise ForecastPersistenceError(
            "Eine leere PV-Prognose kann nicht gespeichert werden."
        )
    if target_type not in {"installation", "plant"}:
        raise ValueError("target_type must be installation or plant")
    if source not in {"fresh", "cached"}:
        raise ValueError("source must be fresh or cached")

    run_id = uuid4()
    created_at = datetime.now(timezone.utc)
    forecast_start = min(point.timestamp for point in forecast.hourly)
    forecast_end = max(point.timestamp for point in forecast.hourly)
    daily_json = json.dumps(
        [item.model_dump(mode="json") for item in forecast.daily],
        ensure_ascii=False,
    )
    hourly_json = json.dumps(
        [item.model_dump(mode="json") for item in forecast.hourly],
        ensure_ascii=False,
    )
    installation_id = target_id if target_type == "installation" else None

    try:
        with duckdb.connect(str(get_database_path())) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute(
                    """
                    INSERT INTO forecast_runs (
                        id, installation_id, target_type, target_id, created_at,
                        forecast_start, forecast_end, hourly_json,
                        daily_energy_json, peak_power_kw, peak_timestamp, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_id,
                        installation_id,
                        target_type,
                        target_id,
                        created_at,
                        forecast_start,
                        forecast_end,
                        hourly_json,
                        daily_json,
                        forecast.metrics.peak_power_kw,
                        forecast.metrics.peak_timestamp,
                        source,
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO forecast_points (
                        run_id, timestamp, predicted_power_kw
                    ) VALUES (?, ?, ?)
                    """,
                    [
                        [run_id, point.timestamp, point.predicted_power_kw]
                        for point in forecast.hourly
                    ],
                )
                connection.execute("COMMIT")
            except duckdb.Error:
                connection.execute("ROLLBACK")
                raise
    except duckdb.Error as exc:
        raise ForecastPersistenceError(
            "Die PV-Prognose konnte nicht in DuckDB gespeichert werden."
        ) from exc

    return run_id


def get_latest_forecast_run(
    target_type: str, target_id: UUID
) -> dict[str, Any] | None:
    """Load the newest persisted forecast snapshot for a target."""
    try:
        with duckdb.connect(str(get_database_path())) as connection:
            row = connection.execute(
                """
                SELECT
                    id, created_at, forecast_start, forecast_end,
                    hourly_json, daily_energy_json, peak_power_kw,
                    peak_timestamp, source
                FROM forecast_runs
                WHERE target_type = ? AND target_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [target_type, target_id],
            ).fetchone()
            if row is None:
                return None
            if row[4]:
                hourly = json.loads(row[4])
            else:
                points = connection.execute(
                    """
                    SELECT timestamp, predicted_power_kw
                    FROM forecast_points
                    WHERE run_id = ?
                    ORDER BY timestamp
                    """,
                    [row[0]],
                ).fetchall()
                hourly = [
                    {"timestamp": point[0], "predicted_power_kw": point[1]}
                    for point in points
                ]
            daily = json.loads(row[5])
    except (duckdb.Error, ValueError, TypeError) as exc:
        raise ForecastPersistenceError(
            "Die gespeicherte PV-Prognose konnte nicht geladen werden."
        ) from exc

    return {
        "id": row[0],
        "created_at": row[1],
        "forecast_start": row[2],
        "forecast_end": row[3],
        "hourly": hourly,
        "daily": daily,
        "metrics": {
            "peak_power_kw": row[6],
            "peak_timestamp": row[7],
        },
        "source": row[8] or "fresh",
    }


def list_forecast_runs(
    installation_id: UUID, limit: int = 20
) -> list[dict[str, Any]]:
    """Load the newest persisted forecast runs for an installation."""
    try:
        with duckdb.connect(str(get_database_path())) as connection:
            rows = connection.execute(
                """
                SELECT
                    id, created_at, forecast_start, forecast_end,
                    daily_energy_json, peak_power_kw, peak_timestamp
                FROM forecast_runs
                WHERE installation_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [installation_id, limit],
            ).fetchall()
    except duckdb.Error as exc:
        raise ForecastPersistenceError(
            "Die Forecast-Historie konnte nicht aus DuckDB geladen werden."
        ) from exc

    return [
        {
            "id": row[0],
            "created_at": row[1],
            "forecast_start": row[2],
            "forecast_end": row[3],
            "daily": json.loads(row[4]),
            "peak_power_kw": row[5],
            "peak_timestamp": row[6],
        }
        for row in rows
    ]


PLANT_COLUMNS = "id, name, location_label, created_at"


def _plant_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "location_label": row[2],
        "created_at": row[3],
    }


def create_plant(data: PlantCreate, session_id: UUID) -> dict[str, Any]:
    plant_id = uuid4()
    created_at = datetime.now()
    location_label = (
        data.location_label.strip() if data.location_label else None
    ) or None

    with duckdb.connect(str(get_database_path())) as connection:
        connection.execute(
            """
            INSERT INTO plants (
                id, session_id, name, location_label, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [plant_id, str(session_id), data.name.strip(), location_label, created_at],
        )

    return {
        "id": plant_id,
        "name": data.name.strip(),
        "location_label": location_label,
        "created_at": created_at,
    }


def list_plants(session_id: UUID) -> list[dict[str, Any]]:
    with duckdb.connect(str(get_database_path())) as connection:
        rows = connection.execute(
            f"""
            SELECT {PLANT_COLUMNS}
            FROM plants
            WHERE session_id = ?
            ORDER BY created_at DESC
            """,
            [str(session_id)],
        ).fetchall()
    return [_plant_from_row(row) for row in rows]


def get_plant(plant_id: UUID, session_id: UUID) -> dict[str, Any] | None:
    with duckdb.connect(str(get_database_path())) as connection:
        row = connection.execute(
            f"""
            SELECT {PLANT_COLUMNS}
            FROM plants
            WHERE id = ? AND session_id = ?
            """,
            [plant_id, str(session_id)],
        ).fetchone()
    return _plant_from_row(row) if row else None


def update_plant(
    plant_id: UUID, session_id: UUID, data: PlantUpdate
) -> dict[str, Any] | None:
    location_label = (
        data.location_label.strip() if data.location_label else None
    ) or None
    with duckdb.connect(str(get_database_path())) as connection:
        row = connection.execute(
            f"""
            UPDATE plants
            SET name = ?, location_label = ?
            WHERE id = ? AND session_id = ?
            RETURNING {PLANT_COLUMNS}
            """,
            [data.name, location_label, plant_id, str(session_id)],
        ).fetchone()
    return _plant_from_row(row) if row else None


def delete_plant(plant_id: UUID, session_id: UUID) -> bool:
    with duckdb.connect(str(get_database_path())) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            owned_plant = connection.execute(
                "SELECT id FROM plants WHERE id = ? AND session_id = ?",
                [plant_id, str(session_id)],
            ).fetchone()
            if owned_plant is None:
                connection.execute("COMMIT")
                return False
            connection.execute(
                """
                DELETE FROM forecast_points
                WHERE run_id IN (
                    SELECT id FROM forecast_runs
                    WHERE target_type = 'plant' AND target_id = ?
                )
                """,
                [plant_id],
            )
            connection.execute(
                """
                DELETE FROM forecast_runs
                WHERE target_type = 'plant' AND target_id = ?
                """,
                [plant_id],
            )
            connection.execute(
                "UPDATE installations SET plant_id = NULL WHERE plant_id = ?",
                [plant_id],
            )
            connection.execute("DELETE FROM plants WHERE id = ?", [plant_id])
            connection.execute("COMMIT")
        except duckdb.Error:
            connection.execute("ROLLBACK")
            raise
    return True


def assign_installation_to_plant(
    plant_id: UUID, installation_id: UUID, session_id: UUID
) -> bool:
    with duckdb.connect(str(get_database_path())) as connection:
        plant_exists = connection.execute(
            "SELECT 1 FROM plants WHERE id = ? AND session_id = ?",
            [plant_id, str(session_id)],
        ).fetchone()
        installation_exists = connection.execute(
            "SELECT 1 FROM installations WHERE id = ? AND session_id = ?",
            [installation_id, session_id],
        ).fetchone()
        if plant_exists is None or installation_exists is None:
            return False
        connection.execute(
            "UPDATE installations SET plant_id = ? WHERE id = ?",
            [plant_id, installation_id],
        )
    return True


def remove_installation_from_plant(
    plant_id: UUID, installation_id: UUID, session_id: UUID
) -> bool:
    with duckdb.connect(str(get_database_path())) as connection:
        removed = connection.execute(
            """
            UPDATE installations
            SET plant_id = NULL
            WHERE id = ? AND plant_id = ? AND session_id = ?
            RETURNING id
            """,
            [installation_id, plant_id, session_id],
        ).fetchone()
    return removed is not None


def list_plant_installations(
    plant_id: UUID, session_id: UUID
) -> list[dict[str, Any]]:
    with duckdb.connect(str(get_database_path())) as connection:
        rows = connection.execute(
            f"""
            SELECT {INSTALLATION_COLUMNS}
            FROM installations
            WHERE plant_id = ? AND session_id = ?
            ORDER BY created_at
            """,
            [plant_id, session_id],
        ).fetchall()
    return [_installation_from_row(row) for row in rows]
