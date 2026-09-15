from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tomllib

from executive_docs.domain import JobStatus, ProjectState
from executive_docs.main import healthz
from executive_docs.presentation import public_state
from executive_docs.version import VERSION


def test_health_check_is_versioned_uncached_and_contains_no_job_data(monkeypatch):
    monkeypatch.setenv("APP_REVISION", "a" * 40)
    monkeypatch.setattr("executive_docs.main.repository.list", lambda *args: (_ for _ in ()).throw(AssertionError("Do not read jobs")))
    response = asyncio.run(healthz())
    assert response.headers["cache-control"] == "no-store"
    assert json.loads(response.body) == {"status": "ok", "version": VERSION, "revision": "a" * 40}
    monkeypatch.setenv("APP_REVISION", "invalid/private/path")
    assert json.loads(asyncio.run(healthz()).body)["revision"] == "development"


def test_release_versions_match_package_lock_and_api():
    root = Path(__file__).resolve().parents[1]
    assert tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"] == VERSION
    lock = tomllib.loads((root / "uv.lock").read_text())
    assert next(p["version"] for p in lock["package"] if p["name"] == "executive-docs-agent") == VERSION


def test_limit_failure_is_actionable_without_exposing_raw_diagnostics():
    state = ProjectState(job_id="limit-test", operator_name="test", status=JobStatus.FAILED_ANALYSIS,
                         error="private raw model/SDK payload", failure_code="context_limit")
    view = public_state(state)
    assert "не помещаются" in view.error and "Повтор без" in view.error
    assert "private" not in view.error
    state.failure_code = "model_budget"
    assert "Этот запрос не отправлен" in public_state(state).error
    assert "лимит" in public_state(state).error
    state.failure_code = None
    assert "private" not in public_state(state).error
