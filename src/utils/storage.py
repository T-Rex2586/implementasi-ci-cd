"""Atomic file writing and history snapshot helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_parent_dir(path: Path) -> None:
    """Ensure parent directories exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text_atomic(path: Path, content: str, encoding: str = "utf-8") -> Path:
    """Write text content atomically to prevent partial files on failure."""
    ensure_parent_dir(path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(content)
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    return path


def write_json_atomic(path: Path, payload: Any) -> Path:
    """Serialize JSON with stable formatting and write atomically."""
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return write_text_atomic(path, serialized)


def write_dataframe_atomic(path: Path, df: pd.DataFrame) -> Path:
    """Write a pandas DataFrame to CSV atomically."""
    csv_text = df.to_csv(index=False)
    return write_text_atomic(path, csv_text)


def persist_dataset_csv(
    df: pd.DataFrame,
    source_dir: Path,
    latest_filename: str,
    history_prefix: str,
    compact_timestamp: str,
) -> tuple[Path, Path]:
    """Persist both the latest CSV and a timestamped history snapshot."""
    latest_path = source_dir / latest_filename
    history_path = source_dir / "history" / f"{history_prefix}_{compact_timestamp}.csv"
    write_dataframe_atomic(latest_path, df)
    write_dataframe_atomic(history_path, df)
    return latest_path, history_path


def persist_dataset_json(
    payload: Any,
    source_dir: Path,
    latest_filename: str,
    history_prefix: str,
    compact_timestamp: str,
) -> tuple[Path, Path]:
    """Persist both the latest JSON and a timestamped history snapshot."""
    latest_path = source_dir / latest_filename
    history_path = source_dir / "history" / f"{history_prefix}_{compact_timestamp}.json"
    write_json_atomic(latest_path, payload)
    write_json_atomic(history_path, payload)
    return latest_path, history_path
