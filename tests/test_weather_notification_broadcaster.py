import unittest

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from backend.config import (
    FirebaseSettings,
    GmailSettings,
    OpenWeatherSettings,
    Settings,
    WeatherNotificationSettings,
)
from backend.models import (
    EmailStatus,
    NotificationResult,
)
from backend.notifications.weather_notification_broadcaster import (
    WeatherNotificationBroadcaster,
)


class WeatherNotificationBroadcasterTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.settings = Settings(
            firebase=FirebaseSettings(
                database_url=(
                    "https://example.firebaseio.com"
                ),
                service_account_key_path=Path("unused.json"),
            ),
            openweather=OpenWeatherSettings(
                api_key="test-key",
                latitude=0,
                longitude=0,
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
                    device_id="default_device",
                    location_id="default_location",
                    current_check_interval_minutes=5,
                    forecast_check_interval_minutes=30,
                    forecast_horizon_hours=24,
                    rain_threshold_percent=70,
                    warning_window_minutes=180,
                    cooldown_minutes=60,
                )
            ),
        )
        self.repository = MagicMock()
        self.notification_service = MagicMock()
        self.provider = MagicMock()
        self.provider_factory = MagicMock(
            return_value=self.provider
        )
        self.now = datetime.now(timezone.utc)

        self.repository.get_enabled_accounts.return_value = [
            {
                "device_id": "device_001",
                "display_name": "Rack One",
                "gmail": "owner.one@gmail.com",
                "gmail_authorized": True,
                "enabled": True,
            },
            {
                "device_id": "device_002",
                "display_name": "Rack Two",
                "gmail": "owner.two@gmail.com",
                "gmail_authorized": False,
                "enabled": True,
            },
        ]
        self.repository.get_device.side_effect = lambda device_id: {
            "location_id": "location_hcm",
        }
        self.repository.get_locations.return_value = [
            {
                "location_id": "location_hcm",
                "name": "Ho Chi Minh City",
                "timezone": "Asia/Ho_Chi_Minh",
                "latitude": 10.8231,
                "longitude": 106.6297,
            }
        ]
        self.repository.set_current_weather.return_value = (
            "current_scan_001"
        )
        self.repository.set_latest_forecast.return_value = (
            "forecast_scan_001"
        )
        self.notification_service.notify.side_effect = (
            lambda alert, **kwargs: NotificationResult(
                notification_id=alert.alert_id,
                created=True,
                email_status=EmailStatus.SKIPPED,
            )
        )

        self.broadcaster = (
            WeatherNotificationBroadcaster(
                repository=self.repository,
                notification_service=(
                    self.notification_service
                ),
                settings=self.settings,
                provider_factory=self.provider_factory,
            )
        )

    def test_current_rain_broadcasts_to_all_accounts(
        self,
    ) -> None:
        current_weather = MagicMock()
        current_weather.to_dict.return_value = {
            "observed_at": self.now,
            "condition": "Rain",
            "rain_last_1h_mm": 1.5,
        }
        self.provider.get_current_weather.return_value = (
            current_weather
        )
        self.repository.get_current_weather.return_value = None

        results = self.broadcaster.check_current_weather()

        self.assertEqual(len(results), 2)
        self.provider_factory.assert_called_once()
        self.repository.get_locations.assert_called_once_with()
        self.repository.set_current_weather.assert_called_once()
        self.assertEqual(
            self.notification_service.notify.call_count,
            2,
        )

        device_ids = {
            call.args[0].device_id
            for call in (
                self.notification_service
                .notify.call_args_list
            )
        }
        self.assertEqual(
            device_ids,
            {"device_001", "device_002"},
        )
        self.assertTrue(
            all(
                call.args[0].scan_id
                == "current_scan_001"
                for call in (
                    self.notification_service
                    .notify.call_args_list
                )
            )
        )

        calls_by_device = {
            call.args[0].device_id: call.kwargs
            for call in (
                self.notification_service
                .notify.call_args_list
            )
        }
        self.assertEqual(
            calls_by_device["device_001"][
                "recipient_email"
            ],
            "owner.one@gmail.com",
        )
        self.assertTrue(
            calls_by_device["device_001"][
                "email_authorized"
            ]
        )
        self.assertFalse(
            calls_by_device["device_002"][
                "email_authorized"
            ]
        )

    def test_ongoing_rain_reaches_new_accounts(
        self,
    ) -> None:
        rain_started_at = self.now - timedelta(
            minutes=15
        )
        current_weather = MagicMock()
        current_weather.to_dict.return_value = {
            "observed_at": self.now,
            "condition": "Rain",
            "rain_last_1h_mm": 1.5,
        }
        self.provider.get_current_weather.return_value = (
            current_weather
        )
        self.repository.get_current_weather.return_value = {
            "is_raining": True,
            "rain_started_at": rain_started_at,
        }
        (
            self.repository
            .get_latest_current_notification.return_value
        ) = None

        results = self.broadcaster.check_current_weather()

        self.assertEqual(len(results), 2)
        self.assertEqual(
            self.repository
            .get_latest_current_notification.call_count,
            2,
        )
        self.assertEqual(
            self.notification_service.notify.call_count,
            2,
        )
        self.assertTrue(
            all(
                call.args[0].scan_id
                == "current_scan_001"
                for call in (
                    self.notification_service
                    .notify.call_args_list
                )
            )
        )

        alerts = [
            call.args[0]
            for call in (
                self.notification_service
                .notify.call_args_list
            )
        ]
        self.assertTrue(
            all(
                alert.rain_started_at == rain_started_at
                for alert in alerts
            )
        )

    def test_forecast_broadcasts_to_all_accounts(
        self,
    ) -> None:
        forecast = MagicMock()
        forecast.to_dict.return_value = {
            "forecast_at": self.now + timedelta(hours=1),
            "forecast_within_minutes": 60,
            "rain_probability_percent": 90,
            "rain_amount_mm": 2.0,
            "condition": "Rain",
        }
        self.provider.get_forecast.return_value = [forecast]
        self.repository.get_current_weather.return_value = {
            "is_raining": False,
        }
        self.repository.get_latest_forecast_notification.return_value = (
            None
        )

        results = self.broadcaster.check_forecast()

        self.assertEqual(len(results), 2)
        self.provider.get_forecast.assert_called_once_with(
            hours=24
        )
        self.repository.set_latest_forecast.assert_called_once()
        self.assertEqual(
            self.repository
            .get_latest_forecast_notification.call_count,
            2,
        )
        self.assertEqual(
            self.notification_service.notify.call_count,
            2,
        )
        self.assertTrue(
            all(
                call.args[0].scan_id
                == "forecast_scan_001"
                for call in (
                    self.notification_service
                    .notify.call_args_list
                )
            )
        )

    def test_skips_account_without_device_document(
        self,
    ) -> None:
        self.repository.get_device.side_effect = [
            {"location_id": "location_hcm"},
            None,
        ]
        current_weather = MagicMock()
        current_weather.to_dict.return_value = {
            "observed_at": self.now,
            "condition": "Clear",
            "rain_last_1h_mm": 0,
        }
        self.provider.get_current_weather.return_value = (
            current_weather
        )

        self.broadcaster.check_current_weather()

        self.provider_factory.assert_called_once()
        self.repository.set_current_weather.assert_called_once()

    def test_scans_location_without_accounts(
        self,
    ) -> None:
        self.repository.get_enabled_accounts.return_value = []
        current_weather = MagicMock()
        current_weather.to_dict.return_value = {
            "observed_at": self.now,
            "condition": "Clear",
            "rain_last_1h_mm": 0,
        }
        self.provider.get_current_weather.return_value = (
            current_weather
        )

        results = self.broadcaster.check_current_weather()

        self.assertEqual(results, [])
        self.provider_factory.assert_called_once()
        self.repository.set_current_weather.assert_called_once()
        self.notification_service.notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
