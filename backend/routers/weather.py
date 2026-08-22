from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend import dependencies
from backend.auth_dependency import get_current_account
from backend.openweather import OpenWeatherError


router = APIRouter(prefix="/api", tags=["weather"])


@router.get("/weather/current")
def get_current_weather(
    current_account: Annotated[dict, Depends(get_current_account)],
):
    try:
        return dependencies.weather_service.get_current_weather().to_dict()
    except OpenWeatherError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


@router.get("/weather/forecast")
def get_forecast(
    current_account: Annotated[dict, Depends(get_current_account)],
    hours: int = 24,
):
    try:
        forecasts = dependencies.weather_service.get_forecast(hours=hours)
        return {"items": [forecast.to_dict() for forecast in forecasts]}
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
