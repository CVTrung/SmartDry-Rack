"""Shared backend service instances used by routers and background jobs."""

from backend.firebase import FirestoreService, RealtimeFirebaseService
from backend.openweather import OpenWeatherService
from backend.services.device_status import DeviceHeartbeatTracker
from backend.services.rack_commands import RackCommandService


weather_service = OpenWeatherService.from_config()
realtime_firebase_service = RealtimeFirebaseService.from_env()
firestore_service = FirestoreService()
device_heartbeat_tracker = DeviceHeartbeatTracker(timeout_seconds=15)
rack_command_service = RackCommandService(
    realtime=realtime_firebase_service,
    firestore=firestore_service,
)
