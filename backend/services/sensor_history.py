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
    ) -> str:
        """Persist one five-minute sensor snapshot."""


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

                self.repository.save_sensor_snapshot(
                    device_id,
                    sensor_data,
                )
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
