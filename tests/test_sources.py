"""Unit tests for all 5 data source parsers and fetchers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config import MONITORED_LOCATIONS, Settings
from src.sources.firms import parse_firms_csv
from src.sources.magma import parse_magma_html
from src.sources.mcd_burned_scar import fetch_mcd_burned_scar, parse_mcd64a1_stac_response
from src.sources.open_meteo_air_quality import parse_air_quality_response
from src.sources.open_meteo_weather import parse_weather_response

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_firms_csv_normalizes_viirs_and_modis() -> None:
    viirs_csv = (
        "latitude,longitude,bright_ti4,acq_date,acq_time,satellite,instrument,confidence,frp,daynight\n"
        "-2.15,113.91,330.5,2026-11-23,512,N,VIIRS,n,12.4,D\n"
    )
    df = parse_firms_csv(viirs_csv, sensor="VIIRS_SNPP_NRT", ingested_at_utc="2026-11-23T12:00:00Z")
    assert len(df) == 1
    assert df.loc[0, "sensor"] == "VIIRS_SNPP_NRT"
    assert df.loc[0, "brightness"] == 330.5
    assert df.loc[0, "acq_time"] == "0512"


def test_parse_firms_csv_raises_on_invalid_key() -> None:
    with pytest.raises(ValueError, match="error response"):
        parse_firms_csv("Invalid MAP_KEY.", sensor="MODIS_NRT", ingested_at_utc="2026-11-23T12:00:00Z")


def test_parse_magma_html_extracts_volcanoes() -> None:
    html = (FIXTURES_DIR / "magma_sample.html").read_text(encoding="utf-8")
    records = parse_magma_html(html, base_url="https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas")
    names = {r["volcano_name"]: r["activity_level"] for r in records}
    assert names["Merapi"] == "Level III (Siaga)"
    assert names["Lewotobi Laki-laki"] == "Level IV (Awas)"
    assert names["Semeru"] == "Level II (Waspada)"


def test_parse_air_quality_response() -> None:
    payload = [
        {
            "latitude": 0.5071,
            "longitude": 101.4478,
            "hourly": {
                "time": ["2026-11-23T00:00", "2026-11-23T01:00"],
                "pm10": [22.1, 25.4],
                "pm2_5": [14.0, 16.2],
                "carbon_monoxide": [210.0, 220.0],
                "nitrogen_dioxide": [5.1, 6.0],
                "sulphur_dioxide": [2.2, 2.5],
                "ozone": [34.0, 36.0],
                "us_aqi": [55, 60],
            },
        }
    ]
    df = parse_air_quality_response(payload, MONITORED_LOCATIONS[:1], "2026-11-23T12:00:00Z")
    assert len(df) == 2
    assert list(df["location"].unique()) == ["Pekanbaru"]
    assert df.loc[0, "pm2_5"] == 14.0


def test_parse_weather_response() -> None:
    payload = [
        {
            "latitude": 0.5071,
            "longitude": 101.4478,
            "hourly": {
                "time": ["2026-11-23T00:00"],
                "temperature_2m": [28.4],
                "relative_humidity_2m": [78],
                "precipitation": [0.2],
                "wind_speed_10m": [8.5],
                "wind_direction_10m": [145],
                "surface_pressure": [1010.2],
            },
        }
    ]
    df = parse_weather_response(payload, MONITORED_LOCATIONS[:1], "2026-11-23T12:00:00Z")
    assert len(df) == 1
    assert df.loc[0, "wind_speed_10m"] == 8.5


def test_parse_mcd64a1_stac_response() -> None:
    payload = json.loads((FIXTURES_DIR / "mcd64a1_stac_sample.json").read_text(encoding="utf-8"))
    df = parse_mcd64a1_stac_response(payload, ingested_at_utc="2026-11-23T12:00:00Z")
    assert len(df) == 1
    assert df.loc[0, "tile_id"] == "h28v09"
    assert df.loc[0, "collection"] == "modis-64A1-061"
    assert df.loc[0, "burn_date_href"].endswith("Burn_Date.tif")


def test_fetch_mcd_burned_scar_persists_csv_and_stac_json(tmp_path: Path) -> None:
    payload = json.loads((FIXTURES_DIR / "mcd64a1_stac_sample.json").read_text(encoding="utf-8"))
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp

    settings = Settings(
        data_dir=tmp_path,
        firms_api_key="test-key",
        firms_days=1,
        firms_sensors=("VIIRS_SNPP_NRT",),
        magma_url="https://example.com/magma",
        open_meteo_air_quality_url="https://example.com/aq",
        open_meteo_weather_url="https://example.com/weather",
        mcd_stac_search_url="https://planetarycomputer.microsoft.com/api/stac/v1/search",
        mcd_collection="modis-64A1-061",
        mcd_lookback_days=90,
        mcd_max_items=50,
        request_timeout_seconds=10,
        http_max_retries=1,
        user_agent="pytest",
    )

    result = fetch_mcd_burned_scar(mock_session, settings, compact_timestamp="20261123T120000Z")
    assert result["records"] == 1
    assert Path(result["output"]).is_file()
    assert Path(result["history_output"]).is_file()
    assert (tmp_path / "mcd_burned_scar" / "latest_stac_items.json").is_file()
