import asyncio
import logging
import uuid

from collections.abc import Callable
from typing import Any, Protocol

from backend.config import (
    WeatherNotificationSettings,
)
logger = logging.getLogger(__name__)


class WeatherCheckProcessor(Protocol):
    def check_current_weather(
        self,
        **kwargs: Any,
    ) -> Any:
        """Check current weather notifications."""

    def check_forecast(
        self,
        **kwargs: Any,
    ) -> Any:
        """Check forecast notifications."""


class WeatherBroadcastLeaseRepository(Protocol):
    def try_acquire_weather_broadcast_lease(
        self,
        *,
        owner_id: str,
        lease_seconds: int,
    ) -> bool:
        """Atomically acquire the shared broadcast lease."""

    def renew_weather_broadcast_lease(
        self,
        *,
        owner_id: str,
        lease_seconds: int,
    ) -> bool:
        """Extend a lease still owned by this runner."""

    def release_weather_broadcast_lease(
        self,
        *,
        owner_id: str,
    ) -> None:
        """Release a lease still owned by this runner."""


class WeatherNotificationRunner:
    def __init__(
        self,
        *,
        processor: WeatherCheckProcessor,
        settings: WeatherNotificationSettings,
        lease_repository: (
            WeatherBroadcastLeaseRepository | None
        ) = None,
        device_name: str | None = None,
        location_name: str | None = None,
        timezone_name: str = "UTC",
    ) -> None:
        self.processor = processor
        self.settings = settings
        self.lease_repository = lease_repository
        self.lease_owner_id = uuid.uuid4().hex
        self.lease_seconds = 120
        self.device_name = device_name
        self.location_name = location_name
        self.timezone_name = timezone_name
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def running(self) -> bool:
        return bool(self._tasks)

    async def _run_safely(
        self,
        check_name: str,
        check: Callable[..., Any],
    ) -> None:
        lease_acquired = False
        check_task: asyncio.Task[None] | None = None

        try:
            if self.lease_repository is not None:
                lease_acquired = await asyncio.to_thread(
                    self.lease_repository
                    .try_acquire_weather_broadcast_lease,
                    owner_id=self.lease_owner_id,
                    lease_seconds=self.lease_seconds,
                )

                if not lease_acquired:
                    logger.info(
                        "Skipping %s because another main "
                        "backend process owns the weather "
                        "broadcast lease",
                        check_name,
                    )
                    return

            # OpenWeather and Firebase currently use
            # synchronous APIs, so run them outside the
            # FastAPI event loop.
            check_task = asyncio.create_task(
                asyncio.to_thread(
                    check,
                    device_name=self.device_name,
                    location_name=self.location_name,
                    timezone_name=self.timezone_name,
                )
            )

            while True:
                done, _ = await asyncio.wait(
                    {check_task},
                    timeout=self.lease_seconds / 3,
                )

                if done:
                    await check_task
                    break

                if self.lease_repository is not None:
                    renewed = await asyncio.to_thread(
                        self.lease_repository
                        .renew_weather_broadcast_lease,
                        owner_id=self.lease_owner_id,
                        lease_seconds=self.lease_seconds,
                    )

                    if not renewed:
                        logger.warning(
                            "Lost the weather broadcast lease "
                            "while running %s",
                            check_name,
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            # One failed check must not terminate future checks.
            logger.exception(
                "Weather notification check failed: %s",
                check_name,
            )
        finally:
            if (
                lease_acquired
                and self.lease_repository is not None
                and (
                    check_task is None
                    or check_task.done()
                )
            ):
                try:
                    await asyncio.to_thread(
                        self.lease_repository
                        .release_weather_broadcast_lease,
                        owner_id=self.lease_owner_id,
                    )
                except Exception:
                    logger.exception(
                        "Could not release the weather "
                        "broadcast lease"
                    )

    async def _repeat(
        self,
        *,
        check_name: str,
        interval_seconds: int,
        check: Callable[..., Any],
    ) -> None:
        while True:
            await asyncio.sleep(interval_seconds)

            await self._run_safely(
                check_name,
                check,
            )

    async def start(self) -> None:
        if self.running:
            return

        # Perform the first checks in order. Current weather
        # must be stored before forecast alert evaluation.
        await self._run_safely(
            "current_weather",
            self.processor.check_current_weather,
        )

        await self._run_safely(
            "forecast",
            self.processor.check_forecast,
        )

        current_interval_seconds = (
            self.settings
            .current_check_interval_minutes
            * 60
        )

        forecast_interval_seconds = (
            self.settings
            .forecast_check_interval_minutes
            * 60
        )

        self._tasks = [
            asyncio.create_task(
                self._repeat(
                    check_name="current_weather",
                    interval_seconds=(
                        current_interval_seconds
                    ),
                    check=(
                        self.processor
                        .check_current_weather
                    ),
                ),
                name="current-weather-notifications",
            ),
            asyncio.create_task(
                self._repeat(
                    check_name="forecast",
                    interval_seconds=(
                        forecast_interval_seconds
                    ),
                    check=self.processor.check_forecast,
                ),
                name="forecast-notifications",
            ),
        ]

    async def stop(self) -> None:
        tasks = self._tasks
        self._tasks = []

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )
