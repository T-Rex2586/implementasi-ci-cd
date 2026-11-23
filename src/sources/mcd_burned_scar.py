"""MODIS MCD64A1 Burned Area / Burned Scar ingestion via Microsoft Planetary Computer STAC API.

Dataset: MODIS/Terra+Aqua Burned Area Monthly L3 Global 500m SIN Grid (MCD64A1 v6.1)
STAC Collection: modis-64A1-061
Access: Public STAC REST API (no API key or NASA Earthdata login required).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import requests

from src.config import INDONESIA_BBOX, Settings
from src.utils.storage import persist_dataset_csv, write_json_atomic

EXPECTED_COLUMNS = [
    "item_id",
    "collection",
    "platform",
    "tile_horizontal",
    "tile_vertical",
    "tile_id",
    "start_datetime",
    "end_datetime",
    "created",
    "bbox_west",
    "bbox_south",
    "bbox_east",
    "bbox_north",
    "burn_date_href",
    "burn_date_uncertainty_href",
    "qa_href",
    "first_day_href",
    "last_day_href",
    "hdf_href",
    "ingested_at_utc",
]


def _asset_href(assets: dict[str, Any], *candidate_keys: str) -> str:
    for key in candidate_keys:
        asset = assets.get(key)
        if isinstance(asset, dict) and asset.get("href"):
            return str(asset["href"])
    return ""


def parse_mcd64a1_stac_response(
    payload: dict[str, Any],
    ingested_at_utc: str,
) -> pd.DataFrame:
    """Parse Planetary Computer STAC search FeatureCollection for MCD64A1 tiles."""
    features = payload.get("features") or []
    rows: list[dict[str, Any]] = []

    for feature in features:
        props = feature.get("properties") or {}
        assets = feature.get("assets") or {}
        bbox = feature.get("bbox") or [None, None, None, None]
        tile_h = props.get("modis:horizontal-tile")
        tile_v = props.get("modis:vertical-tile")
        tile_id = (
            f"h{int(tile_h):02d}v{int(tile_v):02d}"
            if tile_h is not None and tile_v is not None
            else ""
        )

        rows.append(
            {
                "item_id": feature.get("id", ""),
                "collection": feature.get("collection", "modis-64A1-061"),
                "platform": props.get("platform", "terra,aqua"),
                "tile_horizontal": tile_h,
                "tile_vertical": tile_v,
                "tile_id": tile_id,
                "start_datetime": props.get("start_datetime") or props.get("datetime", ""),
                "end_datetime": props.get("end_datetime") or props.get("datetime", ""),
                "created": props.get("created", ""),
                "bbox_west": bbox[0] if len(bbox) >= 4 else None,
                "bbox_south": bbox[1] if len(bbox) >= 4 else None,
                "bbox_east": bbox[2] if len(bbox) >= 4 else None,
                "bbox_north": bbox[3] if len(bbox) >= 4 else None,
                "burn_date_href": _asset_href(assets, "Burn_Date", "Burn Date"),
                "burn_date_uncertainty_href": _asset_href(
                    assets, "Burn_Date_Uncertainty", "Burn Date Uncertainty"
                ),
                "qa_href": _asset_href(assets, "QA"),
                "first_day_href": _asset_href(assets, "First_Day", "First Day"),
                "last_day_href": _asset_href(assets, "Last_Day", "Last Day"),
                "hdf_href": _asset_href(assets, "hdf"),
                "ingested_at_utc": ingested_at_utc,
            }
        )

    if not rows:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    df = pd.DataFrame(rows)[EXPECTED_COLUMNS]
    df = df.drop_duplicates(subset=["item_id"]).sort_values(
        by=["start_datetime", "tile_id"],
        ascending=[False, True],
    )
    return df.reset_index(drop=True)


def fetch_mcd_burned_scar(
    session: requests.Session,
    settings: Settings,
    compact_timestamp: str,
) -> dict[str, Any]:
    """Query latest MODIS MCD64A1 burned area / burned scar tiles over Indonesia."""
    now_utc = datetime.now(UTC)
    start_dt = now_utc - timedelta(days=settings.mcd_lookback_days)
    datetime_range = (
        f"{start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )

    search_body = {
        "collections": [settings.mcd_collection],
        "bbox": list(INDONESIA_BBOX),
        "datetime": datetime_range,
        "limit": settings.mcd_max_items,
    }
    response = session.post(
        settings.mcd_stac_search_url,
        json=search_body,
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()

    # Fallback: if no tiles exist in recent lookback window (monthly product latency),
    # query the latest available tiles without a date filter.
    if not (payload.get("features") or []):
        fallback_body = {
            "collections": [settings.mcd_collection],
            "bbox": list(INDONESIA_BBOX),
            "limit": settings.mcd_max_items,
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        }
        fallback_resp = session.post(
            settings.mcd_stac_search_url,
            json=fallback_body,
            timeout=settings.request_timeout_seconds,
        )
        fallback_resp.raise_for_status()
        payload = fallback_resp.json()

    ingested_at_utc = now_utc.isoformat()
    df = parse_mcd64a1_stac_response(payload, ingested_at_utc=ingested_at_utc)

    source_dir = settings.data_dir / "mcd_burned_scar"
    latest_path, history_path = persist_dataset_csv(
        df=df,
        source_dir=source_dir,
        latest_filename="latest_burned_scar.csv",
        history_prefix="burned_scar",
        compact_timestamp=compact_timestamp,
    )
    write_json_atomic(source_dir / "latest_stac_items.json", payload)

    return {
        "records": int(len(df)),
        "output": latest_path.as_posix(),
        "history_output": history_path.as_posix(),
    }
