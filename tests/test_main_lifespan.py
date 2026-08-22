import unittest

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI

from backend.main import lifespan


class MainLifespanTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_starts_and_stops_runner(
        self,
    ) -> None:
        test_app = FastAPI()
        runner = MagicMock()
        sensor_runner = MagicMock()

        runner.start = AsyncMock()
        runner.stop = AsyncMock()
        sensor_runner.start = AsyncMock()
        sensor_runner.stop = AsyncMock()

        with patch(
            (
                "backend.main."
                "create_weather_notification_runner"
            ),
            return_value=runner,
        ) as create_runner:
            with patch(
                "backend.main.SensorHistoryRunner",
                return_value=sensor_runner,
            ) as create_sensor_runner:
                async with lifespan(test_app):
                    create_runner.assert_called_once_with()
                    create_sensor_runner.assert_called_once()

                    self.assertIs(
                        (
                            test_app.state
                            .weather_notification_runner
                        ),
                        runner,
                    )
                    self.assertIs(
                        test_app.state.sensor_history_runner,
                        sensor_runner,
                    )

                    runner.start.assert_awaited_once_with()
                    sensor_runner.start.assert_awaited_once_with()
                    runner.stop.assert_not_awaited()
                    sensor_runner.stop.assert_not_awaited()

        runner.stop.assert_awaited_once_with()
        sensor_runner.stop.assert_awaited_once_with()

    async def test_stops_runner_after_error(
        self,
    ) -> None:
        test_app = FastAPI()
        runner = MagicMock()
        sensor_runner = MagicMock()

        runner.start = AsyncMock()
        runner.stop = AsyncMock()
        sensor_runner.start = AsyncMock()
        sensor_runner.stop = AsyncMock()

        with patch(
            (
                "backend.main."
                "create_weather_notification_runner"
            ),
            return_value=runner,
        ):
            with patch(
                "backend.main.SensorHistoryRunner",
                return_value=sensor_runner,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Test application failure",
                ):
                    async with lifespan(test_app):
                        raise RuntimeError(
                            "Test application failure"
                        )

        runner.start.assert_awaited_once_with()
        runner.stop.assert_awaited_once_with()
        sensor_runner.start.assert_awaited_once_with()
        sensor_runner.stop.assert_awaited_once_with()

    async def test_cleans_up_started_runner_when_next_start_fails(
        self,
    ) -> None:
        test_app = FastAPI()
        weather_runner = MagicMock()
        sensor_runner = MagicMock()
        weather_runner.start = AsyncMock()
        weather_runner.stop = AsyncMock()
        sensor_runner.start = AsyncMock(
            side_effect=RuntimeError("Sensor runner failed")
        )
        sensor_runner.stop = AsyncMock()

        with (
            patch(
                (
                    "backend.main."
                    "create_weather_notification_runner"
                ),
                return_value=weather_runner,
            ),
            patch(
                "backend.main.SensorHistoryRunner",
                return_value=sensor_runner,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Sensor runner failed",
            ):
                async with lifespan(test_app):
                    pass

        weather_runner.stop.assert_awaited_once_with()
        sensor_runner.stop.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
