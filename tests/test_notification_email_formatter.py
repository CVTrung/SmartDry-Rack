import unittest

from datetime import datetime, timedelta, timezone

from backend.models import WeatherAlert
from backend.notifications.email import (
    WeatherEmailFormatter,
)


class WeatherEmailFormatterTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.formatter = WeatherEmailFormatter()

        self.now = datetime(
            2026,
            8,
            16,
            10,
            0,
            tzinfo=timezone.utc,
        )

    def test_formats_current_rain_email(
        self,
    ) -> None:
        alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=(
                self.now - timedelta(minutes=30)
            ),
            condition="Rain",
            rain_amount_mm=1.8,
        )

        content = self.formatter.format(
            alert,
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.assertEqual(
            content.subject,
            (
                "[SmartDry][CURRENT] "
                "Laundry Rack - Rain at 17:00"
            ),
        )

        self.assertIn(
            "Device: Laundry Rack (device_001)",
            content.body,
        )
        self.assertIn(
            "Location: Ho Chi Minh City",
            content.body,
        )
        self.assertIn(
            "Rain has been detected at Ho Chi Minh City.",
            content.body,
        )
        self.assertIn(
            "Detected: 17:00, 16 Aug 2026 "
            "(Asia/Ho_Chi_Minh)",
            content.body,
        )
        self.assertNotIn(
            "Status:",
            content.body,
        )
        self.assertNotIn(
            "Condition:",
            content.body,
        )
        self.assertNotIn(
            "Rain in the last hour:",
            content.body,
        )

    def test_formats_forecast_email(
        self,
    ) -> None:
        alert = WeatherAlert.near_forecast_rain(
            device_id="device_001",
            location_id="location_hcm",
            forecast_at=(
                self.now + timedelta(hours=2)
            ),
            forecast_within_minutes=120,
            rain_probability_percent=80,
            rain_amount_mm=2.5,
            condition="Rain",
        )

        content = self.formatter.format(
            alert,
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.assertEqual(
            content.subject,
            (
                "[SmartDry][FORECAST] "
                "Laundry Rack - Rain at 19:00"
            ),
        )

        self.assertIn(
            "Rain may reach Ho Chi Minh City in 2 hours.",
            content.body,
        )
        self.assertIn(
            "Rain probability: 80%",
            content.body,
        )
        self.assertIn(
            "Expected rain amount: 2.5 mm",
            content.body,
        )
        self.assertIn(
            "Expected: 19:00, 16 Aug 2026 "
            "(Asia/Ho_Chi_Minh)",
            content.body,
        )
        self.assertNotIn(
            "Condition:",
            content.body,
        )

    def test_uses_location_id_as_fallback(
        self,
    ) -> None:
        alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=self.now,
            condition="Rain",
            rain_amount_mm=1,
        )

        content = self.formatter.format(
            alert,
            location_name=None,
            timezone_name="UTC",
        )

        self.assertIn(
            "Location: Hcm",
            content.body,
        )

    def test_optional_weather_fields_are_omitted(
        self,
    ) -> None:
        alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=self.now,
            condition=None,
            rain_amount_mm=None,
        )

        content = self.formatter.format(
            alert,
            timezone_name="UTC",
        )

        self.assertNotIn(
            "Condition:",
            content.body,
        )
        self.assertNotIn(
            "Rain in the last hour:",
            content.body,
        )

    def test_formats_mixed_hour_duration(
        self,
    ) -> None:
        result = self.formatter._duration_text(
            90
        )

        self.assertEqual(
            result,
            "1 hour 30 minutes",
        )

    def test_formats_zero_minutes_as_now(
        self,
    ) -> None:
        result = self.formatter._duration_text(
            0
        )

        self.assertEqual(
            result,
            "now",
        )

    def test_formats_singular_minute(
        self,
    ) -> None:
        result = self.formatter._duration_text(
            1
        )

        self.assertEqual(
            result,
            "1 minute",
        )

    def test_invalid_timezone_is_rejected(
        self,
    ) -> None:
        alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=self.now,
            condition="Rain",
            rain_amount_mm=1,
        )

        with self.assertRaises(ValueError):
            self.formatter.format(
                alert,
                timezone_name="Invalid/Timezone",
            )


if __name__ == "__main__":
    unittest.main()
