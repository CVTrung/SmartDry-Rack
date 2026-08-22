import time
import threading
from typing import Any, Callable

from firebase_admin import db

from backend.firebase import get_firebase_app


class RealtimeFirebaseServiceError(RuntimeError):
    """Raised when Realtime Database data is invalid."""

class RealtimeFirebaseService:
    INPUT_SENSOR = "Input_Sensor"
    LEGACY_INPUT_SENSOR = "Input_sensor"
    DEVICE_STATE = "Device_State"

    _command_locks_guard = threading.Lock()
    _command_locks: dict[str, threading.Lock] = {}
    
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

    def get_sensor_timestamp(
        self,
        device_id: str,
    ) -> int | float | None:
        """Read the device uptime timestamp used by heartbeat checks.

        ``Input_Sensor`` is the canonical node used by the current
        simulator. ``Input_sensor`` is retained as a read-only fallback for
        older deployments whose Firebase keys used different casing.
        """

        device_id = self._validate_device_id(device_id)
        result = self._reference(
            f"{self.INPUT_SENSOR}/{device_id}/timestamp"
        ).get()

        if result is None:
            result = self._reference(
                f"{self.LEGACY_INPUT_SENSOR}/{device_id}/timestamp"
            ).get()

        if result is None:
            return None

        if (
            not isinstance(result, (int, float))
            or isinstance(result, bool)
        ):
            raise RealtimeFirebaseServiceError(
                "Input_Sensor timestamp must be numeric"
            )

        return result

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
    # Device_State
    # Firmware and backend share operating mode and rack state.
    # =========================================================

    def get_device_state(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)
        result = self._reference(
            f"{self.DEVICE_STATE}/{device_id}"
        ).get()

        return self._validate_dictionary(
            result,
            self.DEVICE_STATE,
        )

    def set_device_mode(
        self,
        device_id: str,
        mode: str,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)
        mode = mode.strip().lower()

        if mode not in {"auto", "manual"}:
            raise ValueError(
                "mode must be either 'auto' or 'manual'"
            )

        updated_at = self._timestamp()
        self._reference(
            f"{self.DEVICE_STATE}/{device_id}"
        ).update({
            "device_id": device_id,
            "mode": mode,
            "updated_at": updated_at,
        })

        return {
            "device_id": device_id,
            "mode": mode,
            "updated_at": updated_at,
        }

    @classmethod
    def command_lock(
        cls,
        device_id: str,
    ) -> threading.Lock:
        """Return the in-process serialization lock for one device."""

        device_id = cls._validate_device_id(device_id)

        with cls._command_locks_guard:
            return cls._command_locks.setdefault(
                device_id,
                threading.Lock(),
            )

    def set_rack_command(
        self,
        device_id: str,
        command: str,
    ) -> dict[str, Any]:
        """Atomically switch to manual mode and set desired rack state."""

        device_id = self._validate_device_id(device_id)
        command = command.strip().lower()

        if command not in {"open", "close"}:
            raise ValueError(
                "command must be either 'open' or 'close'"
            )

        timestamp = self._timestamp()
        rack_state = (
            "extended"
            if command == "open"
            else "retracted"
        )
        state_path = f"{self.DEVICE_STATE}/{device_id}"
        updates = {
            f"{state_path}/device_id": device_id,
            f"{state_path}/mode": "manual",
            f"{state_path}/rack_state": rack_state,
            f"{state_path}/updated_at": timestamp,
        }

        self._reference("/").update(updates)

        return {
            "device_id": device_id,
            "command": command,
            "rack_state": rack_state,
            "timestamp": timestamp,
            "mode": "manual",
        }
