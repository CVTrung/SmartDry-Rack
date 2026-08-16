from typing import Annotated

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.firebase import RealtimeFirebaseService
from backend.openweather import (
    OpenWeatherError,
    OpenWeatherService,
)

from backend.auth_dependency import get_current_account
from backend.sensor_stream import SensorEventStream

app = FastAPI()

weather_service = OpenWeatherService.from_env()
realtime_firebase_service = RealtimeFirebaseService.from_env()

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
# WEATHER
# ================================

@app.get("/api/weather/current")
def get_current_weather(current_account: Annotated[dict, Depends(get_current_account)]):
    try:
        return weather_service.get_current_weather()
    except OpenWeatherError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


@app.get("/api/weather/forecast")
def get_forecast(current_account: Annotated[dict, Depends(get_current_account)], hours: int = 24):
    try:
        return {
            "items": weather_service.get_forecast(hours=hours)
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
    ],
)
