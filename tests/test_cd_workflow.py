"""Contract tests for GitHub Actions CI and CD workflow YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_workflow(filename: str) -> dict:
    path = ROOT / ".github" / "workflows" / filename
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_ci_workflow_contract() -> None:
    wf = _load_workflow("ci.yml")
    triggers = wf.get("on") or wf.get(True)
    assert "push" in triggers
    assert "pull_request" in triggers
    assert set(triggers["push"]["branches"]) == {"dev", "main"}
    assert "test" in wf["jobs"]
    assert "scrape" in wf["jobs"]


def test_cd_workflow_contract() -> None:
    wf = _load_workflow("ingestion.yml")
    triggers = wf.get("on") or wf.get(True)
    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "0 0 * * *"}]
    assert triggers["push"]["branches"] == ["main"]
    assert wf["permissions"]["id-token"] == "write"
    assert wf["permissions"]["contents"] == "read"
    assert "run_slot" in wf["jobs"]["deploy"]["outputs"]
    assert wf["jobs"]["trigger-silver"]["needs"] == "deploy"
