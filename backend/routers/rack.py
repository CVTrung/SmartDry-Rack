from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from backend import dependencies
from backend.auth_dependency import get_current_account
from backend.schemas import RackCommandRequest
from backend.services.rack_commands import (
    CommandConflictError,
    CommandDispatchError,
)


router = APIRouter(prefix="/api", tags=["rack"])


@router.post("/rack/commands", status_code=status.HTTP_202_ACCEPTED)
def create_rack_command(
    request: RackCommandRequest,
    current_account: Annotated[dict, Depends(get_current_account)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    if (
        idempotency_key is not None
        and request.client_request_id is not None
        and idempotency_key != request.client_request_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key and client_request_id must match",
        )

    try:
        return dependencies.rack_command_service.send(
            device_id=current_account["device_id"],
            command=request.command,
            requested_by=(
                current_account.get("uid")
                or current_account.get("user_id")
                or current_account["device_id"]
            ),
            idempotency_key=(
                idempotency_key or request.client_request_id
            ),
        )
    except (ValueError, CommandConflictError) as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error
    except CommandDispatchError as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể gửi lệnh tới thiết bị.",
        ) from error


@router.get("/history")
def get_command_history(
    current_account: Annotated[dict, Depends(get_current_account)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    device_id = current_account["device_id"]

    try:
        records = dependencies.firestore_service.get_device_commands(
            device_id=device_id,
            source="website",
            limit=limit,
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể đọc lịch sử hoạt động.",
        ) from error

    items = []

    for record in records:
        result = record.get("result")
        error_code = (
            result.get("error_code")
            if isinstance(result, dict)
            else None
        )
        items.append({
            "command_id": record.get("command_id"),
            "device_id": record.get("device_id", device_id),
            "command": (
                dependencies.rack_command_service.command_from_record(
                    record
                )
            ),
            "action": record.get("action"),
            "source": record.get("source", "website"),
            "status": (
                dependencies.rack_command_service.status_from_record(
                    record
                )
            ),
            "acknowledged": False,
            "requested_at": record.get("requested_at"),
            "updated_at": record.get("updated_at"),
            "completed_at": record.get("completed_at"),
            "error": error_code,
        })

    return {"items": items, "limit": limit}
