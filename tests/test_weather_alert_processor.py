import unittest

from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.config import (
    WeatherNotificationSettings,
)
from backend.models import (
    CurrentWeather,
    ForecastItem,
    EmailStatus,
    NotificationResult,
    WeatherAlert,
)
from backend.notifications.alert_policy import (
    CurrentWeatherEvaluation,
)
from backend.notifications.weather_alert_processor import (
    WeatherAlertProcessor,
)


class WeatherAlertProcessorTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.now = datetime(
            2026,
            8,
            16,
            10,
            0,
            tzinfo=timezone.utc,
        )

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

        self.weather_provider = MagicMock()
        self.repository = MagicMock()
        self.alert_policy = MagicMock()
        self.notification_service = MagicMock()

        self.processor = WeatherAlertProcessor(
            weather_provider=(
                self.weather_provider
            ),
            repository=self.repository,
            alert_policy=self.alert_policy,
            notification_service=(
                self.notification_service
            ),
            settings=self.settings,
        )

    def create_current_weather(
        self,
        *,
        condition: str,
        rain_amount_mm: float,
    ) -> CurrentWeather:
        return CurrentWeather(
            location="Ho Chi Minh City",
            observed_at=self.now,
            temperature_celsius=30.0,
            feels_like_celsius=34.0,
            humidity_percent=80,
            pressure_hpa=1008,
            condition=condition,
            description=condition.lower(),
            cloud_cover_percent=80,
            wind_speed_mps=3.5,
            rain_last_1h_mm=rain_amount_mm,
        )


    def create_forecast(
        self,
        *,
        forecast_at: datetime,
        condition: str,
        probability: int,
        rain_amount_mm: float,
    ) -> ForecastItem:
        minutes_until = round(
            (
                forecast_at - self.now
            ).total_seconds()
            / 60
        )

        return ForecastItem(
            forecast_at=forecast_at,
            forecast_within_minutes=(
                minutes_until
            ),
            temperature_celsius=29.0,
            humidity_percent=82,
            condition=condition,
            description=condition.lower(),
            rain_probability_percent=probability,
            rain_amount_mm=rain_amount_mm,
            cloud_cover_percent=90,
        )

    def test_current_weather_creates_alert(
        self,
    ) -> None:
        current_weather = (
            self.create_current_weather(
                condition="Rain",
                rain_amount_mm=1.5,
            )
        )

        weather_document = {
            **current_weather.to_dict(),
            "is_raining": True,
            "rain_started_at": self.now,
        }

        alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=self.now,
            condition="Rain",
            rain_amount_mm=1.5,
        )

        expected_result = NotificationResult(
            notification_id=alert.alert_id,
            created=True,
            email_status=EmailStatus.SENT,
            gmail_message_id="gmail_001",
        )

        self.weather_provider.get_current_weather.return_value = (
            current_weather
        )
        self.repository.get_current_weather.return_value = (
            None
        )
        self.alert_policy.evaluate_current_weather.return_value = (
            CurrentWeatherEvaluation(
                is_raining=True,
                rain_started_at=self.now,
                weather_document=weather_document,
                alert=alert,
            )
        )
        self.notification_service.notify.return_value = (
            expected_result
        )

        result = self.processor.check_current_weather(
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.repository.get_current_weather.assert_called_once_with(
            "location_hcm"
        )

        self.repository.set_current_weather.assert_called_once_with(
            location_id="location_hcm",
            weather=weather_document,
            is_raining=True,
            rain_started_at=self.now,
        )

        self.notification_service.notify.assert_called_once_with(
            alert,
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.assertEqual(
            result,
            expected_result,
        )

    def test_current_weather_without_alert(
        self,
    ) -> None:
        current_weather = (
            self.create_current_weather(
                condition="Clear",
                rain_amount_mm=0,
            )
        )

        weather_document = {
            **current_weather.to_dict(),
            "is_raining": False,
            "rain_started_at": None,
        }

        self.weather_provider.get_current_weather.return_value = (
            current_weather
        )
        self.repository.get_current_weather.return_value = {
            "is_raining": False,
        }
        self.alert_policy.evaluate_current_weather.return_value = (
            CurrentWeatherEvaluation(
                is_raining=False,
                rain_started_at=None,
                weather_document=weather_document,
                alert=None,
            )
        )

        result = (
            self.processor.check_current_weather()
        )

        self.repository.set_current_weather.assert_called_once_with(
            location_id="location_hcm",
            weather=weather_document,
            is_raining=False,
            rain_started_at=None,
        )

        self.notification_service.notify.assert_not_called()
        self.assertIsNone(result)

    def test_forecast_is_saved_and_alerted(
        self,
    ) -> None:
        forecast_at = datetime(
            2026,
            8,
            16,
            12,
            0,
            tzinfo=timezone.utc,
        )

        forecast_models = [
            self.create_forecast(
                forecast_at=forecast_at,
                condition="Rain",
                probability=80,
                rain_amount_mm=2.0,
            )
        ]

        forecasts = [
            forecast.to_dict()
            for forecast in forecast_models
        ]

        last_alert_at = datetime(
            2026,
            8,
            16,
            8,
            0,
            tzinfo=timezone.utc,
        )

        alert = WeatherAlert.near_forecast_rain(
            device_id="device_001",
            location_id="location_hcm",
            forecast_at=forecast_at,
            forecast_within_minutes=120,
            rain_probability_percent=80,
            rain_amount_mm=2.0,
            condition="Rain",
        )

        expected_result = NotificationResult(
            notification_id=alert.alert_id,
            created=True,
            email_status=EmailStatus.SENT,
            gmail_message_id="gmail_002",
        )

        self.weather_provider.get_forecast.return_value = (
            forecast_models
        )
        self.repository.get_current_weather.return_value = {
            "is_raining": False,
        }
        (
            self.repository
            .get_latest_forecast_notification
            .return_value
        ) = {
            "created_at": last_alert_at,
        }
        self.alert_policy.select_forecast_alert.return_value = (
            alert
        )
        self.notification_service.notify.return_value = (
            expected_result
        )

        result = self.processor.check_forecast(
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.weather_provider.get_forecast.assert_called_once_with(
            hours=24
        )

        self.repository.set_latest_forecast.assert_called_once_with(
            location_id="location_hcm",
            forecasts=forecasts,
        )

        (
            self.alert_policy
            .select_forecast_alert
            .assert_called_once_with(
                forecasts=forecasts,
                currently_raining=False,
                last_forecast_alert_at=(
                    last_alert_at
                ),
            )
        )

        self.notification_service.notify.assert_called_once_with(
            alert,
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.assertEqual(
            result,
            expected_result,
        )

    def test_forecast_without_alert(
        self,
    ) -> None:
        forecast_models = [
            self.create_forecast(
                forecast_at=self.now,
                condition="Clouds",
                probability=30,
                rain_amount_mm=0,
            )
        ]

        forecasts = [
            forecast.to_dict()
            for forecast in forecast_models
        ]

        self.weather_provider.get_forecast.return_value = (
            forecast_models
        )
        self.repository.get_current_weather.return_value = {
            "is_raining": False,
        }
        (
            self.repository
            .get_latest_forecast_notification
            .return_value
        ) = None
        self.alert_policy.select_forecast_alert.return_value = (
            None
        )

        result = self.processor.check_forecast()

        self.repository.set_latest_forecast.assert_called_once_with(
            location_id="location_hcm",
            forecasts=forecasts,
        )
        self.notification_service.notify.assert_not_called()
        self.assertIsNone(result)

    def test_forecast_reads_current_rain_state(
        self,
    ) -> None:
        self.weather_provider.get_forecast.return_value = (
            []
        )
        self.repository.get_current_weather.return_value = {
            "is_raining": True,
        }
        (
            self.repository
            .get_latest_forecast_notification
            .return_value
        ) = None
        self.alert_policy.select_forecast_alert.return_value = (
            None
        )

        self.processor.check_forecast()

        (
            self.alert_policy
            .select_forecast_alert
            .assert_called_once_with(
                forecasts=[],
                currently_raining=True,
                last_forecast_alert_at=None,
            )
        )

    def test_invalid_notification_timestamp_is_ignored(
        self,
    ) -> None:
        result = (
            self.processor
            ._notification_created_at(
                {
                    "created_at": (
                        "2026-08-16T10:00:00Z"
                    )
                }
            )
        )

        self.assertIsNone(result)

    def test_notification_timestamp_is_returned(
        self,
    ) -> None:
        result = (
            self.processor
            ._notification_created_at(
                {
                    "created_at": self.now,
                }
            )
        )

        self.assertEqual(result, self.now)


if __name__ == "__main__":
    unittest.main()
