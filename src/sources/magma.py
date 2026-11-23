"""MAGMA Indonesia (PVMBG / Badan Geologi ESDM) volcanic activity scraper."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.config import Settings
from src.utils.storage import persist_dataset_json

LEVEL_PATTERNS = [
    (re.compile(r"level\s*iv|awas", re.IGNORECASE), "Level IV (Awas)"),
    (re.compile(r"level\s*iii|siaga", re.IGNORECASE), "Level III (Siaga)"),
    (re.compile(r"level\s*ii|waspada", re.IGNORECASE), "Level II (Waspada)"),
    (re.compile(r"level\s*i\b|normal", re.IGNORECASE), "Level I (Normal)"),
]


def _normalize_level(text: str) -> str:
    for pattern, canonical in LEVEL_PATTERNS:
        if pattern.search(text):
            return canonical
    return "Unknown"


def parse_magma_html(html: str, base_url: str) -> list[dict[str, Any]]:
    """Extract volcano alert records from MAGMA Indonesia tingkat-aktivitas HTML."""
    soup = BeautifulSoup(html, "lxml")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    scraped_at = datetime.now(timezone.utc).isoformat()

    # Strategy 1: Cards/sections grouped by alert level headings
    current_level = "Unknown"
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "tr", "a"]):
        text = " ".join(element.get_text(" ", strip=True).split())
        if not text:
            continue

        if element.name in {"h1", "h2", "h3", "h4", "h5"}:
            detected = _normalize_level(text)
            if detected != "Unknown":
                current_level = detected
            continue

        if element.name == "tr":
            cells = [" ".join(td.get_text(" ", strip=True).split()) for td in element.find_all("td")]
            if len(cells) >= 2:
                volcano_name = cells[0]
                province = cells[1] if len(cells) >= 2 else ""
                level_text = " ".join(cells)
                level = _normalize_level(level_text)
                if level == "Unknown":
                    level = current_level
                link_tag = element.find("a", href=True)
                detail_url = urljoin(base_url, link_tag["href"]) if link_tag else base_url
                key = volcano_name.lower()
                if volcano_name and key not in seen:
                    seen.add(key)
                    records.append(
                        {
                            "volcano_name": volcano_name,
                            "province": province,
                            "activity_level": level,
                            "detail_url": detail_url,
                            "scraped_at_utc": scraped_at,
                        }
                    )
            continue

        if element.name == "a" and element.get("href") and element.find_parent("tr") is None:
            href = str(element["href"])
            if "gunung-api" in href and "tingkat-aktivitas" not in href and len(text) <= 80:
                volcano_name = text
                level = _normalize_level(text)
                if level == "Unknown":
                    level = current_level
                key = volcano_name.lower()
                if key not in seen and level != "Unknown":
                    seen.add(key)
                    records.append(
                        {
                            "volcano_name": volcano_name,
                            "province": "",
                            "activity_level": level,
                            "detail_url": urljoin(base_url, href),
                            "scraped_at_utc": scraped_at,
                        }
                    )

    return records


def fetch_magma_activity(
    session: requests.Session,
    settings: Settings,
    compact_timestamp: str,
) -> dict[str, Any]:
    """Fetch volcanic activity status from MAGMA Indonesia portal."""
    response = session.get(settings.magma_url, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    records = parse_magma_html(response.text, base_url=settings.magma_url)

    payload = {
        "source": "MAGMA Indonesia (PVMBG / Badan Geologi ESDM)",
        "url": settings.magma_url,
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_volcanoes": len(records),
        "records": records,
    }
    latest_path, history_path = persist_dataset_json(
        payload=payload,
        source_dir=settings.data_dir / "magma",
        latest_filename="latest.json",
        history_prefix="magma",
        compact_timestamp=compact_timestamp,
    )
    return {
        "records": len(records),
        "output": latest_path.as_posix(),
        "history_output": history_path.as_posix(),
    }
