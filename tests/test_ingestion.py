"""Tests for the pipeline orchestrator and manifest generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src import main as pipeline_main
from src.config import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        firms_api_key="dummy-key",
        firms_days=1,
        firms_sensors=("VIIRS_SNPP_NRT",),
        magma_url="https://example.com/magma",
        open_meteo_air_quality_url="https://example.com/aq",
        open_meteo_weather_url="https://example.com/weather",
        mcd_stac_search_url="https://example.com/stac",
        mcd_collection="modis-64A1-061",
        mcd_lookback_days=90,
        mcd_max_items=50,
        request_timeout_seconds=10,
        http_max_retries=1,
        user_agent="pytest",
    )


def test_run_pipeline_writes_manifest_for_all_five_sources(tmp_path: Path, monkeypatch) -> None:
    def _fake_source(name: str):
        def _runner(session, settings: Settings, ts: str):
            out = settings.data_dir / name / "latest.csv"
            hist = settings.data_dir / name / "history" / f"{name}_{ts}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            hist.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("col\n1\n", encoding="utf-8")
            hist.write_text("col\n1\n", encoding="utf-8")
            return {"records": 1, "output": out.as_posix(), "history_output": hist.as_posix()}

        return _runner

    fake_registry = {
        key: (label, _fake_source(key))
        for key, (label, _) in pipeline_main.SOURCE_REGISTRY.items()
    }
    monkeypatch.setattr(pipeline_main, "SOURCE_REGISTRY", fake_registry)

    manifest = pipeline_main.run_pipeline(settings=_make_settings(tmp_path), session=MagicMock())
    assert manifest["summary"]["total_sources"] == 5
    assert manifest["summary"]["succeeded"] == 5
    assert manifest["summary"]["failed"] == 0
    assert "mcd_burned_scar" in manifest["sources"]

    saved = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert saved["summary"]["succeeded"] == 5
