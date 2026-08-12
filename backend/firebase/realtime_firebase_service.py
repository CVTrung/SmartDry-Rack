import time
from typing import Any, Callable

from firebase_admin import db

from backend.firebase import get_firebase_app


class RealtimeFirebaseServiceError(RuntimeError):
    """Raised when Realtime Database data is invalid."""


class RealtimeFirebaseService:
    INPUT_SENSOR = "Input_Sensor"
    INPUT_CONFIG = "Input_Config"
    OUTPUT_STATE = "Output_State"
    OUTPUT_FORECAST = "Output_Forecast"

    def __init__(self) -> None:
        self.app = get_firebase_app()

    @classmethod
    def from_env(cls) -> "RealtimeFirebaseService":
        """
        Create the service using the shared Firebase configuration.

        This method is retained for compatibility with existing code.
        """
        return cls()

    def _reference(self, path: str) -> db.Reference:
        """Create a Realtime Database reference."""

        return db.reference(
            path,
            app=self.app,
        )

    @staticmethod
    def _validate_device_id(device_id: str) -> str:
        """Validate a device ID before using it as a Firebase key."""

        device_id = device_id.strip()

        if not device_id:
            raise ValueError(
                "device_id must not be empty"
            )

        invalid_characters = ".#$[]/"

        if any(
            character in device_id
            for character in invalid_characters
        ):
            raise ValueError(
                "device_id must not contain . # $ [ ] or /"
            )

        return device_id

    @staticmethod
    def _timestamp() -> int:
        """Return the current Unix timestamp in seconds."""

        return int(time.time())

    @staticmethod
    def _validate_dictionary(
        value: Any,
        node_name: str,
    ) -> dict[str, Any] | None:
        """Validate data returned from Realtime Database."""

        if value is None:
            return None

        if not isinstance(value, dict):
            raise RealtimeFirebaseServiceError(
                f"{node_name} does not have the expected structure"
            )

        return value

    # =========================================================
    # Input_Sensor
    # Firmware writes sensor data.
    # Backend reads sensor data.
    # =========================================================

    def set_sensor_data(
        self,
        device_id: str,
        light_lux: float,
        humidity_percent: float,
        temperature_celsius: float,
        rain_detected: bool,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)

        if light_lux < 0:
            raise ValueError(
                "light_lux must not be less than 0"
            )

        if not 0 <= humidity_percent <= 100:
            raise ValueError(
                "humidity_percent must be between 0 and 100"
            )

        if not -40 <= temperature_celsius <= 85:
            raise ValueError(
                "temperature_celsius must be between -40 and 85"
            )

        if not isinstance(rain_detected, bool):
            raise TypeError(
                "rain_detected must be a boolean"
            )

        payload: dict[str, Any] = {
            "device_id": device_id,
            "timestamp": self._timestamp(),
            "light_lux": light_lux,
            "humidity_percent": humidity_percent,
            "temperature_celsius": temperature_celsius,
            "rain_detected": rain_detected,
        }

        self._reference(
            f"{self.INPUT_SENSOR}/{device_id}"
        ).set(payload)

        return payload

    def get_sensor_data(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)

        result = self._reference(
            f"{self.INPUT_SENSOR}/{device_id}"
        ).get()

        return self._validate_dictionary(
            result,
            self.INPUT_SENSOR,
        )

    def listen_sensor_data(
        self,
        device_id: str,
        callback: Callable[[db.Event], None],
    ) -> db.ListenerRegistration:
        """Listen for live sensor updates from a device."""

        device_id = self._validate_device_id(device_id)

        return self._reference(
            f"{self.INPUT_SENSOR}/{device_id}"
        ).listen(callback)

    # =========================================================
    # Input_Config
    # Website/backend writes configuration.
    # Firmware reads configuration.
    # =========================================================

    def set_device_config(
        self,
        device_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)

        payload = dict(config)

        payload["device_id"] = device_id
        payload["updated_at"] = self._timestamp()

        mode = payload.get("mode")

        if mode not in {"auto", "manual"}:
            raise ValueError(
                "mode must be either 'auto' or 'manual'"
            )

        self._reference(
            f"{self.INPUT_CONFIG}/{device_id}"
        ).set(payload)

        return payload

    def get_device_config(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)

        result = self._reference(
            f"{self.INPUT_CONFIG}/{device_id}"
        ).get()

        return self._validate_dictionary(
            result,
            self.INPUT_CONFIG,
        )

    def listen_device_config(
        self,
        device_id: str,
        callback: Callable[[db.Event], None],
    ) -> db.ListenerRegistration:
        """Listen for device configuration changes."""

        device_id = self._validate_device_id(device_id)

        return self._reference(
            f"{self.INPUT_CONFIG}/{device_id}"
        ).listen(callback)

    # =========================================================
    # Output_State
    # Backend writes the requested rack state.
    # Firmware reads the requested state.
    # =========================================================

    def set_output_state(
        self,
        device_id: str,
        rack_state: str,
        reason: str,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)
        rack_state = rack_state.strip()
        reason = reason.strip()

        allowed_states = {
            "extended",
            "retracted",
            "error",
        }

        if rack_state not in allowed_states:
            raise ValueError(
                "rack_state must be extended, retracted, or error"
            )

        if not reason:
            raise ValueError(
                "reason must not be empty"
            )

        if len(reason) > 200:
            raise ValueError(
                "reason must not exceed 200 characters"
            )

        payload: dict[str, Any] = {
            "device_id": device_id,
            "updated_at": self._timestamp(),
            "rack_state": rack_state,
            "reason": reason,
        }

        self._reference(
            f"{self.OUTPUT_STATE}/{device_id}"
        ).set(payload)

        return payload

    def get_output_state(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)

        result = self._reference(
            f"{self.OUTPUT_STATE}/{device_id}"
        ).get()

        return self._validate_dictionary(
            result,
            self.OUTPUT_STATE,
        )

    def listen_output_state(
        self,
        device_id: str,
        callback: Callable[[db.Event], None],
    ) -> db.ListenerRegistration:
        """Listen for rack state changes."""

        device_id = self._validate_device_id(device_id)

        return self._reference(
            f"{self.OUTPUT_STATE}/{device_id}"
        ).listen(callback)

    # =========================================================
    # Output_Forecast
    # Backend creates forecast notifications.
    # Website reads forecast notifications.
    # =========================================================

    def create_forecast_notification(
        self,
        device_id: str,
        reason: str,
        forecast_within_minutes: int,
        rain_probability_percent: int | None,
    ) -> str:
        device_id = self._validate_device_id(device_id)
        reason = reason.strip()

        if not reason:
            raise ValueError(
                "reason must not be empty"
            )

        if len(reason) > 200:
            raise ValueError(
                "reason must not exceed 200 characters"
            )

        if forecast_within_minutes < 0:
            raise ValueError(
                "forecast_within_minutes must not be negative"
            )

        if (
            rain_probability_percent is not None
            and not 0 <= rain_probability_percent <= 100
        ):
            raise ValueError(
                "rain_probability_percent must be between 0 and 100"
            )

        payload: dict[str, Any] = {
            "device_id": device_id,
            "notified_at": self._timestamp(),
            "reason": reason,
            "forecast_within_minutes": (
                forecast_within_minutes
            ),
        }

        if rain_probability_percent is not None:
            payload["rain_probability_percent"] = (
                rain_probability_percent
            )

        notification_reference = self._reference(
            f"{self.OUTPUT_FORECAST}/{device_id}"
        ).push(payload)

        notification_id = notification_reference.key

        if notification_id is None:
            raise RealtimeFirebaseServiceError(
                "Firebase did not create a notification ID"
            )

        return notification_id

    def get_forecast_notification(
        self,
        device_id: str,
        notification_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)
        notification_id = notification_id.strip()

        if not notification_id:
            raise ValueError(
                "notification_id must not be empty"
            )

        result = self._reference(
            (
                f"{self.OUTPUT_FORECAST}/"
                f"{device_id}/{notification_id}"
            )
        ).get()

        return self._validate_dictionary(
            result,
            self.OUTPUT_FORECAST,
        )

    def get_device_forecasts(
        self,
        device_id: str,
        limit: int = 10,
    ) -> dict[str, dict[str, Any]]:
        device_id = self._validate_device_id(device_id)

        if limit <= 0:
            raise ValueError(
                "limit must be greater than 0"
            )

        result = (
            self._reference(
                f"{self.OUTPUT_FORECAST}/{device_id}"
            )
            .order_by_key()
            .limit_to_last(limit)
            .get()
        )

        if result is None:
            return {}

        if not isinstance(result, dict):
            raise RealtimeFirebaseServiceError(
                "Output_Forecast does not have the expected structure"
            )

        return result