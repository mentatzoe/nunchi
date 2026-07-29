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
    read_config_snapshot,
    read_receipts,
    write_config_document,
)


router = APIRouter()


def _profile(value: str | None) -> str:
    selected = (value or active_hermes_profile()).strip()
    if not selected or len(selected) > 128:
        raise HTTPException(status_code=422, detail="invalid Hermes profile")
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
    snapshot = read_config_snapshot(profile)
    result = snapshot.response()
    result["channels"] = channel_directory()
    result["restart_endpoint"] = (
        f"/api/gateway/restart?profile={quote(profile, safe='')}"
    )
    return result


@router.get("/health")
def get_health(profile: str | None = Query(default=None)) -> dict[str, Any]:
    selected = _profile(profile)
    try:
        snapshot = read_config_snapshot(selected)
    except Exception as exc:
        raise _http_error(exc) from exc
    return {
        "ok": True,
        "api_version": "2",
        "profile": selected,
        "config_sha256": snapshot.sha256,
        "dashboard_writable": snapshot.source.dashboard_writable,
    }


@router.get("/config")
def get_config(profile: str | None = Query(default=None)) -> dict[str, Any]:
    selected = _profile(profile)
    try:
        return _config_response(selected)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/config")
def put_config(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) - {"profile", "expected_sha256", "document"}:
        raise HTTPException(
            status_code=422,
            detail="config request contains an unexpected field",
        )
    selected = _profile(payload.get("profile"))
    expected = payload.get("expected_sha256")
    document = payload.get("document")
    if not isinstance(expected, str) or not expected:
        raise HTTPException(
            status_code=422,
            detail="expected_sha256 is required",
        )
    if not isinstance(document, dict):
        raise HTTPException(
            status_code=422,
            detail="document must be a JSON object",
        )
    try:
        write_config_document(
            selected,
            document=document,
            expected_sha256=expected,
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
    selected = _profile(profile)
    try:
        result = read_receipts(selected, limit=limit)
    except Exception as exc:
        raise _http_error(exc) from exc
    result["profile"] = selected
    return result
