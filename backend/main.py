from typing import Annotated, Literal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    status,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.notifications import (
    create_weather_notification_runner,
)

from backend.device_status import DeviceHeartbeatTracker
from backend.firebase import (
    FirestoreService,
    RealtimeFirebaseService,
)
from backend.openweather import (
    OpenWeatherError,
    OpenWeatherService,
)

from backend.auth_dependency import get_current_account
from backend.rack_command_service import (
    CommandConflictError,
    CommandDispatchError,
    RackCommandService,
)
from backend.sensor_stream import SensorEventStream

weather_service = (
    OpenWeatherService.from_config()
)
realtime_firebase_service = (
    RealtimeFirebaseService.from_env()
)
firestore_service = FirestoreService()
device_heartbeat_tracker = DeviceHeartbeatTracker(
    timeout_seconds=15,
)
rack_command_service = RackCommandService(
    realtime=realtime_firebase_service,
    firestore=firestore_service,
)


class DeviceConfigRequest(BaseModel):
    mode: Literal["auto", "manual"]


class RackCommandRequest(BaseModel):
    command: Literal["open", "close"]
    client_request_id: str | None = None

@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    notification_runner = (
        create_weather_notification_runner()
    )

    app.state.weather_notification_runner = (
        notification_runner
    )

    await notification_runner.start()

    try:
        yield
    finally:
        await notification_runner.stop()


app = FastAPI(lifespan=lifespan)

# ================================
# AUTH
# ================================

@app.get("/api/auth/me")
def get_authenticated_account(
    account: Annotated[
        dict,
        Depends(get_current_account),
    ],
):
    return account


# ================================
# SENSOR DATA
# ================================

@app.get("/api/sensors/stream")
async def stream_sensor_data(
    current_account: Annotated[
        dict,
        Depends(get_current_account),
    ],
):
    sensor_stream = SensorEventStream(
        service=realtime_firebase_service,
        device_id=current_account["device_id"],
    )

    try:
        sensor_stream.start()
    except Exception as error:
        sensor_stream.close()
        raise HTTPException(
            status_code=502,
            detail="Không thể kết nối dữ liệu cảm biến.",
        ) from error

    return StreamingResponse(
        sensor_stream.events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ================================
# LIVE DEVICE / RACK CONTROL
# ================================

@app.get("/api/rack/state")
def get_rack_state(
    current_account: Annotated[
        dict,
        Depends(get_current_account),
    ],
):
    device_id = current_account["device_id"]

    try:
        state_data = (
            realtime_firebase_service.get_device_state(device_id)
            or {}
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể đọc trạng thái dàn phơi.",
        ) from error

    rack_state = state_data.get("rack_state")
    mode = state_data.get("mode")

    if rack_state not in {
        "extended",
        "retracted",
        "error",
    }:
        rack_state = None

    if mode not in {"auto", "manual"}:
        mode = None

    return {
        "device_id": device_id,
        "rack_state": rack_state,
        "mode": mode,
        "updated_at": state_data.get("updated_at"),
    }


@app.get("/api/device/status")
def get_device_status(
    current_account: Annotated[
        dict,
        Depends(get_current_account),
    ],
):
    device_id = current_account["device_id"]

    try:
        sensor_timestamp = (
            realtime_firebase_service.get_sensor_timestamp(
                device_id
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Không thể kiểm tra trạng thái ESP32.",
        ) from error

    return device_heartbeat_tracker.observe(
        device_id,
        sensor_timestamp,
    )


@app.get("/api/device/config")
def get_device_config(
    current_account: Annotated[
        dict,
        Depends(get_current_account),
    ],
):
    device_id = current_account["device_id"]

    try:
        state_data = (
            realtime_firebase_service.get_device_state(device_id)
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


@app.put("/api/device/config")
def update_device_config(
    config: DeviceConfigRequest,
    current_account: Annotated[
        dict,
        Depends(get_current_account),
    ],
):
    device_id = current_account["device_id"]

    try:
        previous = (
            realtime_firebase_service.get_device_state(device_id)
            or {}
        )
        updated = realtime_firebase_service.set_device_mode(
            device_id,
            config.mode,
        )
        firestore_service.save_config_change(
            device_id=device_id,
            previous_config={
                "mode": previous.get("mode"),
            },
            current_config={
                "mode": config.mode,
            },
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


@app.post(
    "/api/rack/commands",
    status_code=status.HTTP_202_ACCEPTED,
)
def create_rack_command(
    request: RackCommandRequest,
    current_account: Annotated[
        dict,
        Depends(get_current_account),
    ],
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
            detail=(
                "Idempotency-Key and client_request_id must match"
            ),
        )

    try:
        return rack_command_service.send(
            device_id=current_account["device_id"],
            command=request.command,
            requested_by=(
                current_account.get("uid")
                or current_account.get("user_id")
                or current_account["device_id"]
            ),
            idempotency_key=(
                idempotency_key
                or request.client_request_id
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


@app.get("/api/history")
def get_command_history(
    current_account: Annotated[
        dict,
        Depends(get_current_account),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    device_id = current_account["device_id"]

    try:
        records = firestore_service.get_device_commands(
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
                rack_command_service.command_from_record(record)
            ),
            "action": record.get("action"),
            "source": record.get("source", "website"),
            "status": (
                rack_command_service.status_from_record(record)
            ),
            "acknowledged": False,
            "requested_at": record.get("requested_at"),
            "updated_at": record.get("updated_at"),
            "completed_at": record.get("completed_at"),
            "error": error_code,
        })

    return {
        "items": items,
        "limit": limit,
    }

# ================================
# WEATHER
# ================================

@app.get("/api/weather/current")
def get_current_weather(current_account: Annotated[dict, Depends(get_current_account)]):
    try:
        weather = (
            weather_service.get_current_weather()
        )
        return weather.to_dict()
    except OpenWeatherError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


@app.get("/api/weather/forecast")
def get_forecast(current_account: Annotated[dict, Depends(get_current_account)], hours: int = 24):
    try:
        forecasts = weather_service.get_forecast(
            hours=hours
        )

        return {
            "items": [
                forecast.to_dict()
                for forecast in forecasts
            ]
        }
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except OpenWeatherError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

# ================================
# CORS
# ================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
    ],
)
