"""Open-Meteo Air Quality API ingestion for Indonesian monitoring points."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests

from src.config import MONITORED_LOCATIONS, MonitoredLocation, Settings
from src.utils.storage import persist_dataset_csv

HOURLY_VARS = (
    "pm10",
    "pm2_5",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "us_aqi",
)


def parse_air_quality_response(
    payload: dict[str, Any] | list[dict[str, Any]],
    locations: tuple[MonitoredLocation, ...],
    ingested_at_utc: str,
) -> pd.DataFrame:
    """Normalize Open-Meteo Air Quality JSON into a flat DataFrame."""
    entries = payload if isinstance(payload, list) else [payload]
    rows: list[dict[str, Any]] = []

    for loc, entry in zip(locations, entries, strict=False):
        hourly = entry.get("hourly") or {}
        times = hourly.get("time") or []
        for idx, ts in enumerate(times):
            row: dict[str, Any] = {
                "location": loc.name,
                "province": loc.province,
                "latitude": entry.get("latitude", loc.latitude),
                "longitude": entry.get("longitude", loc.longitude),
                "timestamp_utc": ts,
            }
            for var in HOURLY_VARS:
                values = hourly.get(var) or []
                row[var] = values[idx] if idx < len(values) else None
            row["ingested_at_utc"] = ingested_at_utc
            rows.append(row)

    columns = [
        "location",
        "province",
        "latitude",
        "longitude",
        "timestamp_utc",
        *HOURLY_VARS,
        "ingested_at_utc",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)[columns]
    return df.drop_duplicates(subset=["location", "timestamp_utc"]).reset_index(drop=True)


def fetch_air_quality(
    session: requests.Session,
    settings: Settings,
    compact_timestamp: str,
) -> dict[str, Any]:
    """Fetch hourly air quality data from Open-Meteo for Indonesia."""
    params = {
        "latitude": ",".join(str(loc.latitude) for loc in MONITORED_LOCATIONS),
        "longitude": ",".join(str(loc.longitude) for loc in MONITORED_LOCATIONS),
        "hourly": ",".join(HOURLY_VARS),
        "forecast_days": 1,
        "timezone": "UTC",
    }
    response = session.get(
        settings.open_meteo_air_quality_url,
        params=params,
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    ingested_at_utc = datetime.now(UTC).isoformat()
    df = parse_air_quality_response(
        response.json(),
        locations=MONITORED_LOCATIONS,
        ingested_at_utc=ingested_at_utc,
    )

    latest_path, history_path = persist_dataset_csv(
        df=df,
        source_dir=settings.data_dir / "air_quality",
        latest_filename="latest_air_quality.csv",
        history_prefix="air_quality",
        compact_timestamp=compact_timestamp,
    )
    return {
        "records": int(len(df)),
        "output": latest_path.as_posix(),
        "history_output": history_path.as_posix(),
    }
