import asyncio
import logging

from collections.abc import Mapping
from typing import Any, Protocol

from backend.config import SENSOR_HISTORY_INTERVAL_SECONDS


logger = logging.getLogger(__name__)


class SensorRealtimeRepository(Protocol):
    def get_sensor_data(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        """Return the latest RTDB sensor snapshot."""


class SensorHistoryRepository(Protocol):
    def get_enabled_accounts(self) -> list[dict[str, Any]]:
        """Return enabled accounts discovered for this scan."""

    def save_sensor_snapshot(
        self,
        device_id: str,
        sensor_data: Mapping[str, Any],
    ) -> str | None:
        """Persist a new five-minute sensor snapshot."""

    def get_sensor_history(
        self,
        device_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent sensor snapshots, newest first."""


class SensorHistoryRunner:
    def __init__(
        self,
        *,
        realtime: SensorRealtimeRepository,
        repository: SensorHistoryRepository,
        interval_seconds: int = SENSOR_HISTORY_INTERVAL_SECONDS,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        self.realtime = realtime
        self.repository = repository
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None

    @staticmethod
    def _device_id(account: Mapping[str, Any]) -> str | None:
        value = account.get("device_id") or account.get("document_id")

        if not isinstance(value, str) or not value.strip():
            return None

        return value.strip().lower()

    def _enabled_device_ids(self) -> list[str]:
        device_ids: set[str] = set()

        for account in self.repository.get_enabled_accounts():
            if not isinstance(account, Mapping):
                continue

            device_id = self._device_id(account)

            if device_id is not None:
                device_ids.add(device_id)

        return sorted(device_ids)

    @staticmethod
    def _sensor_timestamp(
        sensor_data: Mapping[str, Any],
    ) -> int | float | None:
        value = sensor_data.get("timestamp")

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0
        ):
            return None

        return value

    def _is_new_snapshot(
        self,
        device_id: str,
        sensor_data: Mapping[str, Any],
    ) -> bool:
        sensor_timestamp = self._sensor_timestamp(sensor_data)

        if sensor_timestamp is None:
            logger.warning(
                "Ignoring sensor data for %s because its timestamp "
                "is missing or invalid",
                device_id,
            )
            return False

        history = self.repository.get_sensor_history(
            device_id,
            limit=1,
        )

        if not history:
            return True

        latest_timestamp = history[0].get("sensor_timestamp")

        if (
            not isinstance(latest_timestamp, (int, float))
            or isinstance(latest_timestamp, bool)
        ):
            return True

        if sensor_timestamp == latest_timestamp:
            logger.info(
                "Ignoring unchanged sensor data for %s: "
                "timestamp=%s",
                device_id,
                sensor_timestamp,
            )
            return False

        # ESP32 timestamps are uptime seconds. A lower value can mean
        # the device rebooted, so it is a new session rather than proof
        # that the RTDB snapshot is stale.

        return True

    def snapshot_enabled_devices(self) -> int:
        """Copy current RTDB sensor values into Firestore."""

        saved_count = 0

        for device_id in self._enabled_device_ids():
            try:
                sensor_data = self.realtime.get_sensor_data(device_id)

                if sensor_data is None:
                    logger.info(
                        "Skipping sensor history for %s because RTDB "
                        "has no sensor snapshot",
                        device_id,
                    )
                    continue

                if not self._is_new_snapshot(
                    device_id,
                    sensor_data,
                ):
                    continue

                snapshot_id = self.repository.save_sensor_snapshot(
                    device_id,
                    sensor_data,
                )

                if snapshot_id is None:
                    logger.info(
                        "Ignoring sensor data for %s because the "
                        "five-minute bucket already exists",
                        device_id,
                    )
                    continue

                saved_count += 1
            except Exception:
                logger.exception(
                    "Could not save sensor history for %s",
                    device_id,
                )

        return saved_count

    async def _run_safely(self) -> None:
        try:
            await asyncio.to_thread(self.snapshot_enabled_devices)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Sensor history scan failed")

    async def _repeat(self) -> None:
        while True:
            await self._run_safely()
            await asyncio.sleep(self.interval_seconds)

    async def start(self) -> None:
        if self.running:
            return

        self._task = asyncio.create_task(
            self._repeat(),
            name="sensor-history-snapshots",
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None

        if task is None:
            return

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
