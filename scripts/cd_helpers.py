"""Continuous Deployment helpers: manifest validation, staging, blob verification, and summaries."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REQUIRED_SOURCES = ("firms", "magma", "air_quality", "weather", "mcd_burned_scar")
FORBIDDEN_FILENAMES = {".env", ".env.local", "id_rsa", "credentials.json"}


def load_manifest(data_dir: Path) -> dict[str, Any]:
    """Load and return data/manifest.json."""
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def validate_manifest(
    data_dir: Path,
    required_sources: tuple[str, ...] = REQUIRED_SOURCES,
) -> dict[str, Any]:
    """Validate that manifest.json is complete and every required source succeeded."""
    manifest = load_manifest(data_dir)
    if not manifest.get("run_slot"):
        raise ValueError("Manifest is missing 'run_slot'.")

    sources = manifest.get("sources") or {}
    for key in required_sources:
        if key not in sources:
            raise ValueError(f"Required source '{key}' is missing from manifest.")
        entry = sources[key]
        if entry.get("status") != "success":
            raise ValueError(f"Source '{key}' did not succeed: {entry.get('error')}")
        for field in ("output", "history_output"):
            out_path = entry.get(field)
            if not out_path or not Path(out_path).is_file():
                raise FileNotFoundError(f"Missing output file for '{key}' ({field}): {out_path}")

    summary = manifest.get("summary") or {}
    if summary.get("failed", 0) != 0:
        raise ValueError(f"Manifest reports {summary.get('failed')} failed source(s).")

    return manifest


def prepare_staging(data_dir: Path, staging_dir: Path) -> tuple[str, str, list[str]]:
    """Copy validated scraping outputs into staging_dir/runs/<run_slot>/."""
    manifest = load_manifest(data_dir)
    run_slot = str(manifest["run_slot"])
    blob_prefix = f"runs/{run_slot}"
    target_root = staging_dir / blob_prefix

    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    staged_files: list[str] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == ".gitkeep":
            continue
        if path.name in FORBIDDEN_FILENAMES or path.suffix in {".pem", ".key"}:
            raise ValueError(f"Sensitive file detected in data directory: {path}")

        rel_path = path.relative_to(data_dir)
        dest = target_root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        staged_files.append(f"{blob_prefix}/{rel_path.as_posix()}")

    if not staged_files:
        raise ValueError("No files were staged for upload.")

    return run_slot, blob_prefix, staged_files


def verify_uploaded_blobs(
    staging_target_dir: Path,
    blob_prefix: str,
    uploaded_blobs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify every staged file exists in Azure Blob Storage with matching byte size."""
    expected: dict[str, int] = {}
    for path in sorted(staging_target_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(staging_target_dir).as_posix()
            expected[f"{blob_prefix}/{rel}"] = path.stat().st_size

    actual: dict[str, int] = {}
    for blob in uploaded_blobs:
        name = str(blob.get("name", ""))
        props = blob.get("properties") or {}
        size = props.get("contentLength")
        if size is None:
            size = blob.get("contentLength", 0)
        actual[name] = int(size)

    missing = [name for name in expected if name not in actual]
    size_mismatches = [
        {"blob": name, "expected": expected[name], "actual": actual[name]}
        for name in expected
        if name in actual and actual[name] != expected[name]
    ]

    if missing or size_mismatches:
        raise ValueError(
            f"Blob verification failed. Missing={missing}, SizeMismatches={size_mismatches}"
        )

    return {
        "verified_count": len(expected),
        "total_bytes": sum(expected.values()),
        "blob_prefix": blob_prefix,
    }


def render_summary(
    status: str,
    storage_account: str,
    container: str,
    data_dir: Path,
    blob_prefix: str = "",
) -> str:
    """Render a Markdown summary table for GitHub Actions $GITHUB_STEP_SUMMARY."""
    run_slot = "unknown"
    sources_md: list[str] = []
    manifest_path = data_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_slot = str(manifest.get("run_slot", "unknown"))
        for key, info in (manifest.get("sources") or {}).items():
            sources_md.append(
                f"| `{key}` | {info.get('label', key)} | {info.get('status')} | "
                f"{info.get('records', 0)} | {info.get('duration_seconds', 0)}s |"
            )

    lines = [
        "## Continuous Deployment — Azure Blob Storage",
        "",
        "| Item | Nilai |",
        "| --- | --- |",
        f"| Status akhir deployment | **{status}** |",
        f"| Run slot | `{run_slot}` |",
        f"| Storage account | `{storage_account}` |",
        f"| Blob container | `{container}` |",
        f"| Blob prefix | `{blob_prefix or f'runs/{run_slot}'}` |",
        "",
    ]
    if sources_md:
        lines.extend(
            [
                "### Ringkasan Sumber Data",
                "",
                "| Key | Sumber Data | Status | Records | Durasi |",
                "| --- | --- | --- | ---: | ---: |",
                *sources_md,
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CD helper utilities.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate")
    p_val.add_argument("--data-dir", type=Path, default=Path("data"))

    p_stage = sub.add_parser("stage")
    p_stage.add_argument("--data-dir", type=Path, default=Path("data"))
    p_stage.add_argument("--staging-dir", type=Path, default=Path(".staging"))
    p_stage.add_argument("--github-output", type=Path, default=None)

    p_ver = sub.add_parser("verify")
    p_ver.add_argument("--staging-dir", type=Path, required=True)
    p_ver.add_argument("--blob-prefix", type=str, required=True)
    p_ver.add_argument("--uploaded-json", type=Path, required=True)

    p_sum = sub.add_parser("summary")
    p_sum.add_argument("--status", type=str, required=True)
    p_sum.add_argument("--storage-account", type=str, required=True)
    p_sum.add_argument("--container", type=str, required=True)
    p_sum.add_argument("--data-dir", type=Path, default=Path("data"))
    p_sum.add_argument("--blob-prefix", type=str, default="")

    args = parser.parse_args(argv)

    if args.command == "validate":
        manifest = validate_manifest(args.data_dir)
        print(f"Manifest valid for run_slot={manifest['run_slot']}")
        return 0

    if args.command == "stage":
        run_slot, blob_prefix, staged = prepare_staging(args.data_dir, args.staging_dir)
        print(f"Staged {len(staged)} files under {blob_prefix}")
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as fh:
                fh.write(f"run_slot={run_slot}\n")
                fh.write(f"blob_prefix={blob_prefix}\n")
        return 0

    if args.command == "verify":
        blobs = json.loads(args.uploaded_json.read_text(encoding="utf-8"))
        report = verify_uploaded_blobs(args.staging_dir, args.blob_prefix, blobs)
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "summary":
        print(
            render_summary(
                status=args.status,
                storage_account=args.storage_account,
                container=args.container,
                data_dir=args.data_dir,
                blob_prefix=args.blob_prefix,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
