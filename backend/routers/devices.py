from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend import dependencies
from backend.auth_dependency import get_current_account
from backend.schemas import DeviceConfigRequest


router = APIRouter(prefix="/api", tags=["devices"])


@router.get("/rack/state")
def get_rack_state(
    current_account: Annotated[dict, Depends(get_current_account)],
):
    device_id = current_account["device_id"]

    try:
        state_data = (
            dependencies.realtime_firebase_service.get_device_state(
                device_id
            )
            or {}
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể đọc trạng thái dàn phơi.",
        ) from error

    rack_state = state_data.get("rack_state")
    mode = state_data.get("mode")

    if rack_state not in {"extended", "retracted", "error"}:
        rack_state = None

    if mode not in {"auto", "manual"}:
        mode = None

    return {
        "device_id": device_id,
        "rack_state": rack_state,
        "mode": mode,
        "updated_at": state_data.get("updated_at"),
    }


@router.get("/device/status")
def get_device_status(
    current_account: Annotated[dict, Depends(get_current_account)],
):
    device_id = current_account["device_id"]

    try:
        sensor_timestamp = (
            dependencies.realtime_firebase_service.get_sensor_timestamp(
                device_id
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể kiểm tra trạng thái ESP32.",
        ) from error

    return dependencies.device_heartbeat_tracker.observe(
        device_id,
        sensor_timestamp,
    )


@router.get("/device/config")
def get_device_config(
    current_account: Annotated[dict, Depends(get_current_account)],
):
    device_id = current_account["device_id"]

    try:
        state_data = (
            dependencies.realtime_firebase_service.get_device_state(
                device_id
            )
            or {}
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể đọc cấu hình thiết bị.",
        ) from error

    mode = state_data.get("mode")

    if mode not in {"auto", "manual"}:
        mode = None

    return {
        "device_id": device_id,
        "mode": mode,
        "updated_at": state_data.get("updated_at"),
    }


@router.put("/device/config")
def update_device_config(
    config: DeviceConfigRequest,
    current_account: Annotated[dict, Depends(get_current_account)],
):
    device_id = current_account["device_id"]

    try:
        previous = (
            dependencies.realtime_firebase_service.get_device_state(
                device_id
            )
            or {}
        )
        updated = (
            dependencies.realtime_firebase_service.set_device_mode(
                device_id,
                config.mode,
            )
        )
        dependencies.firestore_service.save_config_change(
            device_id=device_id,
            previous_config={"mode": previous.get("mode")},
            current_config={"mode": config.mode},
            changed_by=(
                current_account.get("uid")
                or current_account.get("user_id")
                or device_id
            ),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể cập nhật cấu hình thiết bị.",
        ) from error

    return updated
