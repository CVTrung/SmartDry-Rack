import asyncio
import logging
import uuid

from collections.abc import Callable
from typing import Any

from backend.config import (
    Settings,
    WeatherNotificationSettings,
    get_settings,
)
from backend.firebase import FirestoreService
from backend.notifications.broadcast import (
    WeatherNotificationBroadcaster,
    WeatherNotificationService,
)
from backend.notifications.email import (
    GmailNotificationService,
    WeatherEmailFormatter,
)
logger = logging.getLogger(__name__)


class WeatherNotificationRunner:
    def __init__(
        self,
        *,
        processor: Any,
        settings: WeatherNotificationSettings,
        lease_repository: (
            Any | None
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

        await self._run_safely(
            "pending_weather_scans",
            self.processor.check_pending_weather_scans,
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
            asyncio.create_task(
                self._repeat(
                    check_name="pending_weather_scans",
                    interval_seconds=2,
                    check=(
                        self.processor.check_pending_weather_scans
                    ),
                ),
                name="pending-weather-scan-notifications",
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


def create_weather_notification_runner(
    settings: Settings | None = None,
) -> WeatherNotificationRunner:
    """Build the complete weather notification workflow."""
    application_settings = (
        settings if settings is not None else get_settings()
    )
    repository = FirestoreService()
    notification_service = WeatherNotificationService(
        repository=repository,
        gmail_service=GmailNotificationService(
            application_settings.gmail
        ),
        email_formatter=WeatherEmailFormatter(),
        gmail_settings=application_settings.gmail,
    )
    broadcaster = WeatherNotificationBroadcaster(
        repository=repository,
        notification_service=notification_service,
        settings=application_settings,
    )
    return WeatherNotificationRunner(
        processor=broadcaster,
        lease_repository=repository,
        settings=application_settings.weather_notifications,
    )
