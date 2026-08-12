from fastapi import FastAPI, HTTPException

from backend.openweather import (
    OpenWeatherError,
    OpenWeatherService,
)


app = FastAPI()

weather_service = OpenWeatherService.from_env()


@app.get("/api/weather/current")
def get_current_weather():
    try:
        return weather_service.get_current_weather()
    except OpenWeatherError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


@app.get("/api/weather/forecast")
def get_forecast(hours: int = 24):
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