import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.config import (
    FirebaseSettings,
    GmailSettings,
    OpenWeatherSettings,
    Settings,
    WeatherNotificationSettings,
)
from backend.notifications.weather_notification_factory import (
    create_weather_notification_runner,
)


FACTORY_MODULE = (
    "backend.notifications."
    "weather_notification_factory"
)


class WeatherNotificationFactoryTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.settings = Settings(
            firebase=FirebaseSettings(
                database_url=(
                    "https://example.firebaseio.com"
                ),
                service_account_key_path=Path(
                    "unused-service-account.json"
                ),
            ),
            openweather=OpenWeatherSettings(
                api_key="test-api-key",
                latitude=10.7769,
                longitude=106.7009,
                timeout_seconds=10,
            ),
            gmail=GmailSettings(
                enabled=False,
                sender_email=None,
                recipient_email=None,
                credentials_path=None,
                token_path=None,
                max_retry_attempts=3,
            ),
            weather_notifications=(
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
            ),
        )

    def test_creates_broadcast_runner(self) -> None:
        repository = MagicMock()
        broadcaster = MagicMock()
        runner = MagicMock()

        with (
            patch(
                f"{FACTORY_MODULE}.FirestoreService",
                return_value=repository,
            ),
            patch(
                (
                    f"{FACTORY_MODULE}."
                    "WeatherNotificationBroadcaster"
                ),
                return_value=broadcaster,
            ) as broadcaster_class,
            patch(
                (
                    f"{FACTORY_MODULE}."
                    "WeatherNotificationRunner"
                ),
                return_value=runner,
            ) as runner_class,
            patch(
                f"{FACTORY_MODULE}.get_settings"
            ) as get_settings,
        ):
            result = create_weather_notification_runner(
                self.settings
            )

        self.assertIs(result, runner)
        get_settings.assert_not_called()

        broadcaster_class.assert_called_once()
        broadcaster_arguments = (
            broadcaster_class.call_args.kwargs
        )
        self.assertIs(
            broadcaster_arguments["repository"],
            repository,
        )
        self.assertIs(
            broadcaster_arguments["settings"],
            self.settings,
        )

        runner_class.assert_called_once_with(
            processor=broadcaster,
            lease_repository=repository,
            settings=self.settings.weather_notifications,
        )

    def test_uses_central_settings_by_default(
        self,
    ) -> None:
        runner = MagicMock()

        with (
            patch(
                f"{FACTORY_MODULE}.get_settings",
                return_value=self.settings,
            ) as get_settings,
            patch(
                f"{FACTORY_MODULE}.FirestoreService"
            ),
            patch(
                (
                    f"{FACTORY_MODULE}."
                    "WeatherNotificationRunner"
                ),
                return_value=runner,
            ),
        ):
            result = create_weather_notification_runner()

        self.assertIs(result, runner)
        get_settings.assert_called_once_with()

    def test_account_discovery_is_deferred_to_checks(
        self,
    ) -> None:
        repository = MagicMock()

        with (
            patch(
                f"{FACTORY_MODULE}.FirestoreService",
                return_value=repository,
            ),
            patch(
                (
                    f"{FACTORY_MODULE}."
                    "WeatherNotificationRunner"
                )
            ),
        ):
            create_weather_notification_runner(
                self.settings
            )

        repository.get_enabled_accounts.assert_not_called()
        repository.get_location.assert_not_called()


if __name__ == "__main__":
    unittest.main()
