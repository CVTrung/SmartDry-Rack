import threading
import time
from dataclasses import dataclass


@dataclass
class _HeartbeatObservation:
    sensor_timestamp: int | float
    first_observed_monotonic: float
    last_change_monotonic: float | None = None
    last_change_observed_at: float | None = None


class DeviceHeartbeatTracker:
    """Track changes to device uptime timestamps across HTTP polls.

    Wokwi publishes an uptime counter, not Unix time, so availability cannot
    be calculated by subtracting it from ``time.time()``. The first snapshot
    enters a bounded ``checking`` window because one value alone does not
    prove that the device is still updating. Any subsequent value change,
    including an uptime reset, marks the device online for the configured
    window.
    """

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.timeout_seconds = timeout_seconds
        self._observations: dict[str, _HeartbeatObservation] = {}
        self._lock = threading.Lock()

    def _bounded_stale_seconds(self, elapsed_seconds: float) -> float:
        """Keep offline duration bounded while preserving threshold state."""

        if elapsed_seconds > self.timeout_seconds:
            return self.timeout_seconds + 1

        return elapsed_seconds

    def observe(
        self,
        device_id: str,
        sensor_timestamp: int | float | None,
        *,
        monotonic_now: float | None = None,
        wall_now: float | None = None,
    ) -> dict[str, object]:
        monotonic_now = (
            time.monotonic()
            if monotonic_now is None
            else monotonic_now
        )
        wall_now = time.time() if wall_now is None else wall_now

        if (
            sensor_timestamp is not None
            and (
                not isinstance(sensor_timestamp, (int, float))
                or isinstance(sensor_timestamp, bool)
            )
        ):
            raise ValueError("sensor_timestamp must be numeric or null")

        with self._lock:
            observation = self._observations.get(device_id)

            if sensor_timestamp is None:
                return {
                    "device_id": device_id,
                    "status": "offline",
                    "online": False,
                    "sensor_timestamp": None,
                    "last_change_observed_at": None,
                    "stale_for_seconds": None,
                    "timeout_seconds": self.timeout_seconds,
                }

            if observation is None:
                observation = _HeartbeatObservation(
                    sensor_timestamp=sensor_timestamp,
                    first_observed_monotonic=monotonic_now,
                )
                self._observations[device_id] = observation
            elif sensor_timestamp != observation.sensor_timestamp:
                observation.sensor_timestamp = sensor_timestamp
                observation.last_change_monotonic = monotonic_now
                observation.last_change_observed_at = wall_now

            return self._response(
                device_id=device_id,
                sensor_timestamp=sensor_timestamp,
                observation=observation,
                monotonic_now=monotonic_now,
            )

    def _response(
        self,
        *,
        device_id: str,
        sensor_timestamp: int | float | None,
        observation: _HeartbeatObservation | None,
        monotonic_now: float,
    ) -> dict[str, object]:
        stale_for_seconds: float | None = None
        last_change_observed_at: float | None = None
        online = False
        status = "offline"

        if (
            observation is not None
            and observation.last_change_monotonic is not None
        ):
            elapsed_seconds = max(
                0.0,
                monotonic_now - observation.last_change_monotonic,
            )
            stale_for_seconds = self._bounded_stale_seconds(
                elapsed_seconds
            )
            last_change_observed_at = (
                observation.last_change_observed_at
            )
            online = elapsed_seconds < self.timeout_seconds
            status = "online" if online else "offline"
        elif observation is not None:
            elapsed_seconds = max(
                0.0,
                monotonic_now - observation.first_observed_monotonic,
            )
            stale_for_seconds = self._bounded_stale_seconds(
                elapsed_seconds
            )

            if elapsed_seconds < self.timeout_seconds:
                status = "checking"

        return {
            "device_id": device_id,
            "status": status,
            "online": online,
            "sensor_timestamp": sensor_timestamp,
            "last_change_observed_at": last_change_observed_at,
            "stale_for_seconds": stale_for_seconds,
            "timeout_seconds": self.timeout_seconds,
        }
