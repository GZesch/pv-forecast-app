import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import duckdb

from backend.models import InstallationCreate, PVForecastResponse


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
                installation_id UUID NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                forecast_start TIMESTAMPTZ NOT NULL,
                forecast_end TIMESTAMPTZ NOT NULL,
                daily_energy_json TEXT NOT NULL,
                peak_power_kw DOUBLE NOT NULL,
                peak_timestamp TIMESTAMPTZ NOT NULL
            )
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
            CREATE TABLE IF NOT EXISTS installations (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                latitude DOUBLE NOT NULL,
                longitude DOUBLE NOT NULL,
                peak_power_kwp DOUBLE NOT NULL,
                azimuth DOUBLE NOT NULL,
                tilt DOUBLE NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


INSTALLATION_COLUMNS = """
    id, name, latitude, longitude, peak_power_kwp, azimuth, tilt, created_at
"""


def _installation_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "latitude": row[2],
        "longitude": row[3],
        "peak_power_kwp": row[4],
        "azimuth": row[5],
        "tilt": row[6],
        "created_at": row[7],
    }


def create_installation(
    data: InstallationCreate, latitude: float, longitude: float
) -> dict[str, Any]:
    installation_id = uuid4()
    created_at = datetime.now()

    with duckdb.connect(str(get_database_path())) as connection:
        connection.execute(
            """
            INSERT INTO installations (
                id, name, latitude, longitude, peak_power_kwp,
                azimuth, tilt, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                installation_id,
                data.name,
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
        "latitude": latitude,
        "longitude": longitude,
        "peak_power_kwp": data.peak_power_kwp,
        "azimuth": data.azimuth,
        "tilt": data.tilt,
        "created_at": created_at,
    }


def list_installations() -> list[dict[str, Any]]:
    with duckdb.connect(str(get_database_path())) as connection:
        rows = connection.execute(
            f"SELECT {INSTALLATION_COLUMNS} FROM installations ORDER BY created_at DESC"
        ).fetchall()

    return [_installation_from_row(row) for row in rows]


def get_installation(installation_id: UUID) -> dict[str, Any] | None:
    with duckdb.connect(str(get_database_path())) as connection:
        row = connection.execute(
            f"SELECT {INSTALLATION_COLUMNS} FROM installations WHERE id = ?",
            [installation_id],
        ).fetchone()

    return _installation_from_row(row) if row else None


def delete_installation(installation_id: UUID) -> bool:
    """Delete an installation and report whether it existed."""
    with duckdb.connect(str(get_database_path())) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
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
                "DELETE FROM installations WHERE id = ? RETURNING id",
                [installation_id],
            ).fetchone()
            connection.execute("COMMIT")
        except duckdb.Error:
            connection.execute("ROLLBACK")
            raise

    return deleted is not None


def save_forecast_run(
    installation_id: UUID, forecast: PVForecastResponse
) -> UUID:
    """Persist one complete forecast run and all of its hourly points."""
    if not forecast.hourly:
        raise ForecastPersistenceError(
            "Eine leere PV-Prognose kann nicht gespeichert werden."
        )

    run_id = uuid4()
    created_at = datetime.now(timezone.utc)
    forecast_start = min(point.timestamp for point in forecast.hourly)
    forecast_end = max(point.timestamp for point in forecast.hourly)
    daily_json = json.dumps(
        [item.model_dump(mode="json") for item in forecast.daily],
        ensure_ascii=False,
    )

    try:
        with duckdb.connect(str(get_database_path())) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute(
                    """
                    INSERT INTO forecast_runs (
                        id, installation_id, created_at, forecast_start,
                        forecast_end, daily_energy_json, peak_power_kw,
                        peak_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_id,
                        installation_id,
                        created_at,
                        forecast_start,
                        forecast_end,
                        daily_json,
                        forecast.metrics.peak_power_kw,
                        forecast.metrics.peak_timestamp,
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
