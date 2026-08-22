from fastapi import APIRouter

from backend.routers.auth import router as auth_router
from backend.routers.devices import router as devices_router
from backend.routers.rack import router as rack_router
from backend.routers.sensors import router as sensors_router
from backend.routers.weather import router as weather_router


routers: tuple[APIRouter, ...] = (
    auth_router,
    sensors_router,
    devices_router,
    rack_router,
    weather_router,
)

__all__ = ["routers"]
