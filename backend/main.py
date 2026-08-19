from typing import Annotated

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.notifications import (
    create_weather_notification_runner,
)

from backend.openweather import (
    OpenWeatherError,
    OpenWeatherService,
)

from backend.auth_dependency import get_current_account

weather_service = (
    OpenWeatherService.from_config()
)


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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)