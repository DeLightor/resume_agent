"""US-37 投递追踪 HTTP API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from resume_agent.api.response import error, success
from resume_agent.services.application_tracker import (
    ApplicationError,
    create_application,
    delete_application,
    get_application,
    list_applications,
    restore_application,
    update_application,
)

router = APIRouter(prefix="/applications", tags=["applications"])


def _failure(exc: ApplicationError) -> JSONResponse:
    detail = error(exc.code, exc.message)
    if exc.details:
        detail["error"] |= exc.details
    return JSONResponse(status_code=exc.status_code, content=detail)


@router.post("", status_code=201, response_model=None)
def create(payload: dict[str, Any]) -> Any:
    try:
        return success(create_application(payload))
    except ApplicationError as exc:
        return _failure(exc)


@router.get("", response_model=None)
def list_records(status: str | None = None, deleted: str = "exclude") -> Any:
    try:
        return success(list_applications(status, deleted))
    except ApplicationError as exc:
        return _failure(exc)


@router.get("/{application_id}", response_model=None)
def detail(application_id: str) -> Any:
    try:
        return success(get_application(application_id))
    except ApplicationError as exc:
        return _failure(exc)


@router.put("/{application_id}", response_model=None)
def update(application_id: str, payload: dict[str, Any]) -> Any:
    try:
        return success(update_application(application_id, payload))
    except ApplicationError as exc:
        return _failure(exc)


@router.delete("/{application_id}", response_model=None)
def delete(application_id: str, payload: dict[str, Any]) -> Any:
    try:
        return success(delete_application(application_id, payload.get("expected_version")))
    except ApplicationError as exc:
        return _failure(exc)


@router.post("/{application_id}/restore", response_model=None)
def restore(application_id: str, payload: dict[str, Any]) -> Any:
    try:
        return success(restore_application(application_id, payload.get("expected_version")))
    except ApplicationError as exc:
        return _failure(exc)
