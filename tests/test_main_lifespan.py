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

        runner.start = AsyncMock()
        runner.stop = AsyncMock()

        with patch(
            (
                "backend.main."
                "create_weather_notification_runner"
            ),
            return_value=runner,
        ) as create_runner:
            async with lifespan(test_app):
                create_runner.assert_called_once_with()

                self.assertIs(
                    (
                        test_app.state
                        .weather_notification_runner
                    ),
                    runner,
                )

                runner.start.assert_awaited_once_with()
                runner.stop.assert_not_awaited()

        runner.stop.assert_awaited_once_with()

    async def test_stops_runner_after_error(
        self,
    ) -> None:
        test_app = FastAPI()
        runner = MagicMock()

        runner.start = AsyncMock()
        runner.stop = AsyncMock()

        with patch(
            (
                "backend.main."
                "create_weather_notification_runner"
            ),
            return_value=runner,
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


if __name__ == "__main__":
    unittest.main()