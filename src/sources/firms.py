"""NASA FIRMS active fire hotspot ingestion (MODIS & VIIRS)."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests

from src.config import INDONESIA_BBOX, Settings
from src.utils.storage import persist_dataset_csv

FIRMS_AREA_URL_TEMPLATE = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{sensor}/{bbox}/{days}"
)

EXPECTED_COLUMNS = [
    "sensor",
    "latitude",
    "longitude",
    "brightness",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "frp",
    "daynight",
    "ingested_at_utc",
]


def parse_firms_csv(csv_text: str, sensor: str, ingested_at_utc: str) -> pd.DataFrame:
    """Parse raw NASA FIRMS CSV response into a normalized DataFrame."""
    stripped = csv_text.strip()
    if not stripped:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    lower_head = stripped[:200].lower()
    if (
        "invalid map_key" in lower_head
        or lower_head.startswith("<!doctype html")
        or lower_head.startswith("<html")
    ):
        raise ValueError(f"NASA FIRMS returned an error response for {sensor}: {stripped[:160]}")

    df = pd.read_csv(io.StringIO(stripped))
    if df.empty:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    # Normalize brightness column name across MODIS (brightness) and VIIRS (bright_ti4)
    if "brightness" not in df.columns and "bright_ti4" in df.columns:
        df["brightness"] = df["bright_ti4"]

    df["sensor"] = sensor
    df["ingested_at_utc"] = ingested_at_utc

    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[EXPECTED_COLUMNS].copy()
    df["acq_time"] = df["acq_time"].astype(str).str.zfill(4)
    return df


def fetch_firms_hotspots(
    session: requests.Session,
    settings: Settings,
    compact_timestamp: str,
) -> dict[str, Any]:
    """Fetch NASA FIRMS hotspots for Indonesia across configured sensors."""
    if not settings.firms_api_key:
        raise RuntimeError(
            "FIRMS_API_KEY is not set. Register a free MAP_KEY at "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/"
        )

    bbox_str = ",".join(str(coord) for coord in INDONESIA_BBOX)
    ingested_at_utc = datetime.now(UTC).isoformat()
    frames: list[pd.DataFrame] = []

    for sensor in settings.firms_sensors:
        url = FIRMS_AREA_URL_TEMPLATE.format(
            map_key=settings.firms_api_key,
            sensor=sensor,
            bbox=bbox_str,
            days=settings.firms_days,
        )
        response = session.get(url, timeout=settings.request_timeout_seconds)
        response.raise_for_status()
        parsed = parse_firms_csv(response.text, sensor=sensor, ingested_at_utc=ingested_at_utc)
        if not parsed.empty:
            frames.append(parsed)

    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["sensor", "latitude", "longitude", "acq_date", "acq_time"]
        ).reset_index(drop=True)
    else:
        combined = pd.DataFrame(columns=EXPECTED_COLUMNS)

    latest_path, history_path = persist_dataset_csv(
        df=combined,
        source_dir=settings.data_dir / "firms",
        latest_filename="latest_hotspots.csv",
        history_prefix="hotspots",
        compact_timestamp=compact_timestamp,
    )
    return {
        "records": int(len(combined)),
        "output": latest_path.as_posix(),
        "history_output": history_path.as_posix(),
    }
