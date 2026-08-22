from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import dependencies
from backend.notifications import create_weather_notification_runner
from backend.routers import routers
from backend.services.sensor_history import SensorHistoryRunner


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    weather_runner = create_weather_notification_runner()
    sensor_history_runner = SensorHistoryRunner(
        realtime=dependencies.realtime_firebase_service,
        repository=dependencies.firestore_service,
    )

    app.state.weather_notification_runner = weather_runner
    app.state.sensor_history_runner = sensor_history_runner
    started_runners = []

    try:
        await weather_runner.start()
        started_runners.append(weather_runner)
        await sensor_history_runner.start()
        started_runners.append(sensor_history_runner)
        yield
    finally:
        for runner in reversed(started_runners):
            await runner.stop()


def create_app() -> FastAPI:
    application = FastAPI(lifespan=lifespan)

    for router in routers:
        application.include_router(router)

    application.add_middleware(
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
    return application


app = create_app()
