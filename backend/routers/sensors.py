from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend import dependencies
from backend.auth_dependency import get_current_account
from backend.services.sensor_stream import SensorEventStream


router = APIRouter(prefix="/api", tags=["sensors"])


@router.get("/sensors/stream")
async def stream_sensor_data(
    current_account: Annotated[dict, Depends(get_current_account)],
):
    sensor_stream = SensorEventStream(
        service=dependencies.realtime_firebase_service,
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
