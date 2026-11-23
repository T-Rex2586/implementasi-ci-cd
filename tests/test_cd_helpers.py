"""Tests for scripts/cd_helpers.py validation, staging, verification, and summary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.cd_helpers import (
    REQUIRED_SOURCES,
    prepare_staging,
    render_summary,
    validate_manifest,
    verify_uploaded_blobs,
)


def _create_valid_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    sources = {}
    for key in REQUIRED_SOURCES:
        latest = data_dir / key / "latest.csv"
        history = data_dir / key / "history" / f"{key}_20261123T120000Z.csv"
        latest.parent.mkdir(parents=True, exist_ok=True)
        history.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text("a,b\n1,2\n", encoding="utf-8")
        history.write_text("a,b\n1,2\n", encoding="utf-8")
        sources[key] = {
            "label": key,
            "status": "success",
            "records": 1,
            "output": latest.as_posix(),
            "history_output": history.as_posix(),
            "duration_seconds": 0.5,
            "error": None,
        }

    manifest = {
        "run_slot": "2026/11/23/1200",
        "generated_at": "2026-11-23T12:05:00+00:00",
        "summary": {
            "total_sources": len(REQUIRED_SOURCES),
            "succeeded": len(REQUIRED_SOURCES),
            "failed": 0,
        },
        "sources": sources,
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return data_dir


def test_validate_stage_and_verify_roundtrip(tmp_path: Path) -> None:
    data_dir = _create_valid_data_dir(tmp_path)
    manifest = validate_manifest(data_dir)
    assert manifest["run_slot"] == "2026/11/23/1200"

    staging_dir = tmp_path / ".staging"
    run_slot, blob_prefix, staged_files = prepare_staging(data_dir, staging_dir)
    assert run_slot == "2026/11/23/1200"
    assert blob_prefix == "runs/2026/11/23/1200"
    assert len(staged_files) == len(REQUIRED_SOURCES) * 2 + 1

    # Simulate Azure CLI `az storage blob list` JSON output
    uploaded = []
    target_root = staging_dir / blob_prefix
    for path in target_root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(target_root).as_posix()
            uploaded.append(
                {
                    "name": f"{blob_prefix}/{rel}",
                    "properties": {"contentLength": path.stat().st_size},
                }
            )

    report = verify_uploaded_blobs(target_root, blob_prefix, uploaded)
    assert report["verified_count"] == len(staged_files)

    summary_md = render_summary("PASS", "myaccount", "scraping-results", data_dir, blob_prefix)
    assert "PASS" in summary_md
    assert "mcd_burned_scar" in summary_md


def test_prepare_staging_blocks_sensitive_files(tmp_path: Path) -> None:
    data_dir = _create_valid_data_dir(tmp_path)
    (data_dir / ".env").write_text("FIRMS_API_KEY=secret", encoding="utf-8")
    with pytest.raises(ValueError, match="Sensitive file"):
        prepare_staging(data_dir, tmp_path / ".staging")
