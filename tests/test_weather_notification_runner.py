import asyncio
import unittest

from unittest.mock import (
    AsyncMock,
    MagicMock,
    call,
    patch,
)

from backend.config import (
    WeatherNotificationSettings,
)
from backend.notifications.weather_notification_runner import (
    WeatherNotificationRunner,
)


class WeatherNotificationRunnerTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        self.settings = (
            WeatherNotificationSettings(
                device_id="device_001",
                location_id="location_hcm",
                current_check_interval_minutes=5,
                forecast_check_interval_minutes=30,
                forecast_horizon_hours=24,
                rain_threshold_percent=70,
                warning_window_minutes=180,
                cooldown_minutes=60,
            )
        )

        self.processor = MagicMock()

        self.runner = WeatherNotificationRunner(
            processor=self.processor,
            settings=self.settings,
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

    async def asyncTearDown(self) -> None:
        await self.runner.stop()

    async def test_start_runs_initial_checks_in_order(
        self,
    ) -> None:
        with patch.object(
            self.runner,
            "_run_safely",
            new_callable=AsyncMock,
        ) as run_safely:
            await self.runner.start()

        self.assertEqual(
            run_safely.await_args_list,
            [
                call(
                    "current_weather",
                    self.processor.check_current_weather,
                ),
                call(
                    "forecast",
                    self.processor.check_forecast,
                ),
            ],
        )

        self.assertTrue(self.runner.running)
        self.assertEqual(
            len(self.runner._tasks),
            2,
        )

    async def test_start_is_idempotent(
        self,
    ) -> None:
        with patch.object(
            self.runner,
            "_run_safely",
            new_callable=AsyncMock,
        ) as run_safely:
            await self.runner.start()
            await self.runner.start()

        self.assertEqual(
            run_safely.await_count,
            2,
        )
        self.assertEqual(
            len(self.runner._tasks),
            2,
        )

    async def test_stop_clears_tasks(
        self,
    ) -> None:
        with patch.object(
            self.runner,
            "_run_safely",
            new_callable=AsyncMock,
        ):
            await self.runner.start()

        self.assertTrue(self.runner.running)

        await self.runner.stop()

        self.assertFalse(self.runner.running)
        self.assertEqual(
            self.runner._tasks,
            [],
        )

    async def test_run_safely_calls_check(
        self,
    ) -> None:
        check = MagicMock()

        await self.runner._run_safely(
            "current_weather",
            check,
        )

        check.assert_called_once_with(
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

    async def test_run_safely_handles_failure(
        self,
    ) -> None:
        check = MagicMock(
            side_effect=RuntimeError(
                "OpenWeather unavailable"
            )
        )

        with patch(
            (
                "backend.notifications."
                "weather_notification_runner."
                "logger.exception"
            )
        ) as log_exception:
            # The exception must not leave the runner.
            await self.runner._run_safely(
                "current_weather",
                check,
            )

        log_exception.assert_called_once_with(
            "Weather notification check failed: %s",
            "current_weather",
        )

    async def test_shared_lease_allows_only_one_broadcast(
        self,
    ) -> None:
        lease_repository = MagicMock()
        lease_repository.try_acquire_weather_broadcast_lease.return_value = (
            False
        )
        self.runner.lease_repository = lease_repository
        check = MagicMock()

        await self.runner._run_safely(
            "current_weather",
            check,
        )

        check.assert_not_called()
        lease_repository.try_acquire_weather_broadcast_lease.assert_called_once_with(
            owner_id=self.runner.lease_owner_id,
            lease_seconds=self.runner.lease_seconds,
        )
        lease_repository.release_weather_broadcast_lease.assert_not_called()

    async def test_shared_lease_is_released_after_broadcast(
        self,
    ) -> None:
        lease_repository = MagicMock()
        lease_repository.try_acquire_weather_broadcast_lease.return_value = (
            True
        )
        self.runner.lease_repository = lease_repository
        check = MagicMock()

        await self.runner._run_safely(
            "forecast",
            check,
        )

        check.assert_called_once()
        lease_repository.release_weather_broadcast_lease.assert_called_once_with(
            owner_id=self.runner.lease_owner_id,
        )

    async def test_current_repeat_uses_interval(
        self,
    ) -> None:
        with (
            patch(
                (
                    "backend.notifications."
                    "weather_notification_runner."
                    "asyncio.sleep"
                ),
                new_callable=AsyncMock,
                side_effect=[
                    None,
                    asyncio.CancelledError(),
                ],
            ) as sleep,
            patch.object(
                self.runner,
                "_run_safely",
                new_callable=AsyncMock,
            ) as run_safely,
        ):
            with self.assertRaises(
                asyncio.CancelledError
            ):
                await self.runner._repeat(
                    check_name="current_weather",
                    interval_seconds=300,
                    check=(
                        self.processor
                        .check_current_weather
                    ),
                )

        sleep.assert_any_await(300)

        run_safely.assert_awaited_once_with(
            "current_weather",
            self.processor.check_current_weather,
        )

    async def test_forecast_repeat_uses_interval(
        self,
    ) -> None:
        with (
            patch(
                (
                    "backend.notifications."
                    "weather_notification_runner."
                    "asyncio.sleep"
                ),
                new_callable=AsyncMock,
                side_effect=[
                    None,
                    asyncio.CancelledError(),
                ],
            ) as sleep,
            patch.object(
                self.runner,
                "_run_safely",
                new_callable=AsyncMock,
            ) as run_safely,
        ):
            with self.assertRaises(
                asyncio.CancelledError
            ):
                await self.runner._repeat(
                    check_name="forecast",
                    interval_seconds=1800,
                    check=self.processor.check_forecast,
                )

        sleep.assert_any_await(1800)

        run_safely.assert_awaited_once_with(
            "forecast",
            self.processor.check_forecast,
        )


if __name__ == "__main__":
    unittest.main()
