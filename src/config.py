"""Runtime configuration for the environmental data ingestion pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Indonesia bounding box: [west, south, east, north]
INDONESIA_BBOX: tuple[float, float, float, float] = (95.0, -11.0, 141.0, 6.0)


@dataclass(frozen=True)
class MonitoredLocation:
    """Representative Indonesian monitoring point for weather & air quality."""

    name: str
    province: str
    latitude: float
    longitude: float


MONITORED_LOCATIONS: tuple[MonitoredLocation, ...] = (
    MonitoredLocation("Pekanbaru", "Riau", 0.5071, 101.4478),
    MonitoredLocation("Palembang", "Sumatera Selatan", -2.9761, 104.7754),
    MonitoredLocation("Palangka Raya", "Kalimantan Tengah", -2.2083, 113.9167),
    MonitoredLocation("Pontianak", "Kalimantan Barat", -0.0263, 109.3425),
    MonitoredLocation("Banjarmasin", "Kalimantan Selatan", -3.3186, 114.5944),
    MonitoredLocation("Yogyakarta", "DI Yogyakarta", -7.7956, 110.3695),
    MonitoredLocation("Surabaya", "Jawa Timur", -7.2575, 112.7521),
    MonitoredLocation("Jakarta", "DKI Jakarta", -6.2088, 106.8456),
    MonitoredLocation("Makassar", "Sulawesi Selatan", -5.1477, 119.4327),
    MonitoredLocation("Manado", "Sulawesi Utara", 1.4748, 124.8421),
)


@dataclass(frozen=True)
class Settings:
    """Environment-driven settings for all scrapers and orchestrator."""

    data_dir: Path
    firms_api_key: str | None
    firms_days: int
    firms_sensors: tuple[str, ...]
    magma_url: str
    open_meteo_air_quality_url: str
    open_meteo_weather_url: str
    mcd_stac_search_url: str
    mcd_collection: str
    mcd_lookback_days: int
    mcd_max_items: int
    request_timeout_seconds: int
    http_max_retries: int
    user_agent: str


def get_settings() -> Settings:
    """Load settings from environment variables with sensible defaults."""
    firms_key = os.getenv("FIRMS_API_KEY", "").strip() or None
    return Settings(
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        firms_api_key=firms_key,
        firms_days=int(os.getenv("FIRMS_DAYS", "1")),
        firms_sensors=("VIIRS_SNPP_NRT", "MODIS_NRT"),
        magma_url=os.getenv(
            "MAGMA_URL",
            "https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas",
        ),
        open_meteo_air_quality_url=os.getenv(
            "OPEN_METEO_AIR_QUALITY_URL",
            "https://air-quality-api.open-meteo.com/v1/air-quality",
        ),
        open_meteo_weather_url=os.getenv(
            "OPEN_METEO_WEATHER_URL",
            "https://api.open-meteo.com/v1/forecast",
        ),
        mcd_stac_search_url=os.getenv(
            "MCD_STAC_SEARCH_URL",
            "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        ),
        mcd_collection=os.getenv("MCD_COLLECTION", "modis-64A1-061"),
        mcd_lookback_days=int(os.getenv("MCD_LOOKBACK_DAYS", "90")),
        mcd_max_items=int(os.getenv("MCD_MAX_ITEMS", "50")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        http_max_retries=int(os.getenv("HTTP_MAX_RETRIES", "3")),
        user_agent=os.getenv(
            "HTTP_USER_AGENT",
            "tcba-cicd-ingestion-pipeline/1.0 (+https://github.com)",
        ),
    )


def compute_run_slot(now: datetime | None = None) -> tuple[str, str]:
    """Compute the 6-hour UTC run slot path and compact timestamp.

    Returns:
        Tuple of (run_slot, compact_timestamp), e.g.
        ("2026/11/23/1200", "20261123T120000Z").
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    slot_hour = (current.hour // 6) * 6
    slot_dt = current.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
    run_slot = slot_dt.strftime("%Y/%m/%d/%H00")
    compact = current.strftime("%Y%m%dT%H%M%SZ")
    return run_slot, compact
