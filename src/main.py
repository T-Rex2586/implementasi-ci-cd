"""CLI orchestrator for the 5-source environmental data ingestion pipeline."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from src.config import Settings, compute_run_slot, get_settings
from src.sources.firms import fetch_firms_hotspots
from src.sources.magma import fetch_magma_activity
from src.sources.mcd_burned_scar import fetch_mcd_burned_scar
from src.sources.open_meteo_air_quality import fetch_air_quality
from src.sources.open_meteo_weather import fetch_weather
from src.utils.http import build_http_session
from src.utils.storage import write_json_atomic

SourceFunc = Callable[[requests.Session, Settings, str], dict[str, Any]]

SOURCE_REGISTRY: dict[str, tuple[str, SourceFunc]] = {
    "firms": ("NASA FIRMS", fetch_firms_hotspots),
    "magma": ("MAGMA Indonesia", fetch_magma_activity),
    "air_quality": ("Open-Meteo Air Quality", fetch_air_quality),
    "weather": ("Open-Meteo Weather", fetch_weather),
    "mcd_burned_scar": ("MODIS MCD64A1 Burned Scar", fetch_mcd_burned_scar),
}


def run_pipeline(
    settings: Settings | None = None,
    selected_sources: list[str] | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Execute all selected data sources and persist data/manifest.json."""
    active_settings = settings or get_settings()
    active_settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_slot, compact_timestamp = compute_run_slot()

    source_keys = selected_sources or list(SOURCE_REGISTRY.keys())
    unknown = [k for k in source_keys if k not in SOURCE_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")

    owns_session = session is None
    http_session = session or build_http_session(
        max_retries=active_settings.http_max_retries,
        user_agent=active_settings.user_agent,
    )

    pipeline_start = time.perf_counter()
    results: dict[str, Any] = {}
    succeeded = 0
    failed = 0

    try:
        for key in source_keys:
            label, fn = SOURCE_REGISTRY[key]
            started = time.perf_counter()
            try:
                outcome = fn(http_session, active_settings, compact_timestamp)
                elapsed = round(time.perf_counter() - started, 2)
                results[key] = {
                    "label": label,
                    "status": "success",
                    "records": outcome["records"],
                    "output": outcome["output"],
                    "history_output": outcome["history_output"],
                    "duration_seconds": elapsed,
                    "error": None,
                }
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                elapsed = round(time.perf_counter() - started, 2)
                results[key] = {
                    "label": label,
                    "status": "failed",
                    "records": 0,
                    "output": None,
                    "history_output": None,
                    "duration_seconds": elapsed,
                    "error": str(exc),
                }
                failed += 1
    finally:
        if owns_session:
            http_session.close()

    total_elapsed = round(time.perf_counter() - pipeline_start, 2)
    manifest: dict[str, Any] = {
        "run_slot": run_slot,
        "generated_at": datetime.now(UTC).isoformat(),
        "duration_seconds": total_elapsed,
        "github": {
            "repository": os.getenv("GITHUB_REPOSITORY", "local"),
            "run_id": os.getenv("GITHUB_RUN_ID", "local"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "1"),
            "sha": os.getenv("GITHUB_SHA", "local"),
            "ref": os.getenv("GITHUB_REF", "local"),
            "actor": os.getenv("GITHUB_ACTOR", "local"),
        },
        "summary": {
            "total_sources": len(source_keys),
            "succeeded": succeeded,
            "failed": failed,
        },
        "sources": results,
    }

    write_json_atomic(active_settings.data_dir / "manifest.json", manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run the Indonesian environmental data scraping pipeline."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=list(SOURCE_REGISTRY.keys()),
        help="Optional subset of sources to execute.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Override output data directory.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status if any selected source fails.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    settings = get_settings()
    if args.data_dir is not None:
        settings = replace(settings, data_dir=args.data_dir)

    manifest = run_pipeline(settings=settings, selected_sources=args.sources)
    summary = manifest["summary"]
    print(
        f"Pipeline finished for run_slot={manifest['run_slot']}: "
        f"{summary['succeeded']}/{summary['total_sources']} succeeded, "
        f"{summary['failed']} failed."
    )
    if args.strict and summary["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
