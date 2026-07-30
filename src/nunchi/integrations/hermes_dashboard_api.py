"""Thin authenticated HTTP API for the Hermes dashboard extension.

Hermes imports this module inside its dashboard process and mounts ``router``
under ``/api/plugins/nunchi``. Authentication remains owned by Hermes.
Configuration validation and storage live in the dependency-free store module.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from nunchi.errors import ValidationError
from nunchi.integrations.hermes_dashboard_store import (
    DashboardConfigConflict,
    DashboardConfigError,
    DashboardConfigReadOnly,
    active_hermes_profile,
    channel_directory,
    discord_runtime_status,
    read_dashboard_snapshot,
    read_receipts,
    write_config_document,
)


router = APIRouter()


def _profile(value: Any) -> str:
    if value is None:
        value = active_hermes_profile()
    if not isinstance(value, str):
        raise DashboardConfigError("invalid Hermes profile")
    selected = value.strip()
    if not selected or len(selected) > 128:
        raise DashboardConfigError("invalid Hermes profile")
    return selected


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DashboardConfigConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DashboardConfigReadOnly):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (DashboardConfigError, ValidationError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=503, detail="Nunchi dashboard is unavailable")


def _config_response(profile: str) -> dict[str, Any]:
    snapshot = read_dashboard_snapshot(profile, allow_invalid=True)
    result = snapshot.response()
    result["channels"] = channel_directory()
    result["discord_runtime"] = discord_runtime_status(snapshot)
    result["restart_endpoint"] = (
        f"/api/gateway/restart?profile={quote(profile, safe='')}"
    )
    return result


@router.get("/health")
def get_health(profile: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        selected = _profile(profile)
        snapshot = read_dashboard_snapshot(selected, allow_invalid=True)
    except Exception as exc:
        raise _http_error(exc) from exc
    return {
        "ok": True,
        "api_version": "2",
        "profile": selected,
        "config_sha256": snapshot.sha256,
        "config_revision": snapshot.revision,
        "bootstrap_required": snapshot.bootstrap_required,
        "bootstrap_recovery": snapshot.bootstrap_recovery,
        "update_recovery": snapshot.update_recovery,
        "dashboard_writable": snapshot.source.dashboard_writable,
        "configuration_valid": snapshot.config is not None,
        "configuration_loadable": (
            snapshot.config is not None and not snapshot.bootstrap_required
        ),
        "validation_error": snapshot.validation_error,
    }


@router.get("/config")
def get_config(profile: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        selected = _profile(profile)
        return _config_response(selected)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/config")
def put_config(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) - {
        "profile",
        "expected_revision",
        "expected_sha256",
        "document",
    }:
        raise HTTPException(
            status_code=422,
            detail="config request contains an unexpected field",
        )
    expected_revision = payload.get("expected_revision")
    legacy_expected = payload.get("expected_sha256")
    document = payload.get("document")
    if expected_revision is not None and legacy_expected is not None:
        raise HTTPException(
            status_code=422,
            detail="provide expected_revision or expected_sha256, not both",
        )
    expected = expected_revision if expected_revision is not None else legacy_expected
    if not isinstance(expected, str) or not expected:
        raise HTTPException(
            status_code=422,
            detail="expected_revision is required",
        )
    if not isinstance(document, dict):
        raise HTTPException(
            status_code=422,
            detail="document must be a JSON object",
        )
    try:
        selected = _profile(payload.get("profile"))
        write_config_document(
            selected,
            document=document,
            expected_revision=expected,
        )
        result = _config_response(selected)
    except Exception as exc:
        raise _http_error(exc) from exc
    result["saved"] = True
    return result


@router.get("/receipts")
def get_receipts(
    profile: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    try:
        selected = _profile(profile)
        result = read_receipts(selected, limit=limit)
    except Exception as exc:
        raise _http_error(exc) from exc
    result["profile"] = selected
    return result
