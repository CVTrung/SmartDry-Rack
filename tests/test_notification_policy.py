import unittest

from datetime import datetime, timedelta, timezone

from backend.config import (
    WeatherNotificationSettings,
)
from backend.models import AlertType
from backend.notifications.policy import (
    WeatherAlertPolicy,
)


class WeatherAlertPolicyTests(unittest.TestCase):
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

        self.policy = WeatherAlertPolicy(
            self.settings
        )

        self.now = datetime(
            2026,
            8,
            16,
            10,
            0,
            tzinfo=timezone.utc,
        )

    def forecast(
        self,
        *,
        minutes_until: int,
        probability: int | None,
        condition: str = "Rain",
        rain_amount_mm: float = 2.5,
    ) -> dict:
        return {
            "forecast_at": (
                self.now
                + timedelta(minutes=minutes_until)
            ).isoformat(),
            "forecast_within_minutes": (
                minutes_until
            ),
            "rain_probability_percent": probability,
            "rain_amount_mm": rain_amount_mm,
            "condition": condition,
        }

    def test_dry_to_rain_creates_alert(
        self,
    ) -> None:
        current = {
            "observed_at": self.now.isoformat(),
            "condition": "Rain",
            "rain_last_1h_mm": 1.5,
        }

        previous = {
            "is_raining": False,
            "rain_started_at": None,
        }

        result = (
            self.policy.evaluate_current_weather(
                current_weather=current,
                previous_weather=previous,
                now=self.now,
            )
        )

        self.assertTrue(result.is_raining)
        self.assertEqual(
            result.rain_started_at,
            self.now,
        )
        self.assertIsNotNone(result.alert)

        assert result.alert is not None

        self.assertEqual(
            result.alert.alert_type,
            AlertType.CURRENT_RAIN,
        )
        self.assertEqual(
            result.alert.device_id,
            "device_001",
        )
        self.assertEqual(
            result.alert.location_id,
            "location_hcm",
        )

    def test_continuing_rain_does_not_alert(
        self,
    ) -> None:
        rain_started_at = (
            self.now - timedelta(minutes=30)
        )

        current = {
            "observed_at": self.now.isoformat(),
            "condition": "Rain",
            "rain_last_1h_mm": 2.0,
        }

        previous = {
            "is_raining": True,
            "rain_started_at": rain_started_at,
        }

        result = (
            self.policy.evaluate_current_weather(
                current_weather=current,
                previous_weather=previous,
                now=self.now,
            )
        )

        self.assertTrue(result.is_raining)
        self.assertEqual(
            result.rain_started_at,
            rain_started_at,
        )
        self.assertIsNone(result.alert)

    def test_rain_to_dry_resets_episode(
        self,
    ) -> None:
        current = {
            "observed_at": self.now.isoformat(),
            "condition": "Clear",
            "rain_last_1h_mm": 0,
        }

        previous = {
            "is_raining": True,
            "rain_started_at": (
                self.now - timedelta(hours=1)
            ),
        }

        result = (
            self.policy.evaluate_current_weather(
                current_weather=current,
                previous_weather=previous,
                now=self.now,
            )
        )

        self.assertFalse(result.is_raining)
        self.assertIsNone(
            result.rain_started_at
        )
        self.assertIsNone(result.alert)
        self.assertIsNone(
            result.weather_document[
                "rain_started_at"
            ]
        )

    def test_drizzle_counts_as_rain(
        self,
    ) -> None:
        current = {
            "condition": "Drizzle",
            "rain_last_1h_mm": 0,
        }

        self.assertTrue(
            self.policy.is_raining(current)
        )

    def test_rain_amount_counts_as_rain(
        self,
    ) -> None:
        current = {
            "condition": "Clouds",
            "rain_last_1h_mm": 0.5,
        }

        self.assertTrue(
            self.policy.is_raining(current)
        )

    def test_clear_weather_is_not_rain(
        self,
    ) -> None:
        current = {
            "condition": "Clear",
            "rain_last_1h_mm": 0,
        }

        self.assertFalse(
            self.policy.is_raining(current)
        )

    def test_forecast_at_exact_boundary_alerts(
        self,
    ) -> None:
        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=180,
                    probability=70,
                )
            ],
            currently_raining=False,
            now=self.now,
        )

        self.assertIsNotNone(alert)

        assert alert is not None

        self.assertEqual(
            alert.alert_type,
            AlertType.NEAR_FORECAST_RAIN,
        )
        self.assertEqual(
            alert.forecast_within_minutes,
            180,
        )
        self.assertEqual(
            alert.rain_probability_percent,
            70,
        )

    def test_probability_below_threshold_skips(
        self,
    ) -> None:
        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=120,
                    probability=69,
                )
            ],
            currently_raining=False,
            now=self.now,
        )

        self.assertIsNone(alert)

    def test_forecast_outside_window_skips(
        self,
    ) -> None:
        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=181,
                    probability=90,
                )
            ],
            currently_raining=False,
            now=self.now,
        )

        self.assertIsNone(alert)

    def test_missing_probability_skips(
        self,
    ) -> None:
        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=60,
                    probability=None,
                )
            ],
            currently_raining=False,
            now=self.now,
        )

        self.assertIsNone(alert)

    def test_selects_nearest_qualifying_forecast(
        self,
    ) -> None:
        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=150,
                    probability=90,
                ),
                self.forecast(
                    minutes_until=60,
                    probability=75,
                ),
                self.forecast(
                    minutes_until=120,
                    probability=80,
                ),
            ],
            currently_raining=False,
            now=self.now,
        )

        self.assertIsNotNone(alert)

        assert alert is not None

        self.assertEqual(
            alert.forecast_within_minutes,
            60,
        )
        self.assertEqual(
            alert.rain_probability_percent,
            75,
        )

    def test_current_rain_prevents_forecast_alert(
        self,
    ) -> None:
        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=60,
                    probability=90,
                )
            ],
            currently_raining=True,
            now=self.now,
        )

        self.assertIsNone(alert)

    def test_active_cooldown_prevents_alert(
        self,
    ) -> None:
        last_alert_at = (
            self.now - timedelta(minutes=59)
        )

        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=60,
                    probability=90,
                )
            ],
            currently_raining=False,
            last_forecast_alert_at=last_alert_at,
            now=self.now,
        )

        self.assertIsNone(alert)

    def test_expired_cooldown_allows_alert(
        self,
    ) -> None:
        last_alert_at = (
            self.now - timedelta(minutes=60)
        )

        alert = self.policy.select_forecast_alert(
            forecasts=[
                self.forecast(
                    minutes_until=60,
                    probability=90,
                )
            ],
            currently_raining=False,
            last_forecast_alert_at=last_alert_at,
            now=self.now,
        )

        self.assertIsNotNone(alert)

    def test_invalid_forecast_is_ignored(
        self,
    ) -> None:
        alert = self.policy.select_forecast_alert(
            forecasts=[
                {
                    "forecast_at": "invalid-time",
                    "forecast_within_minutes": 60,
                    "rain_probability_percent": 90,
                },
                self.forecast(
                    minutes_until=120,
                    probability=80,
                ),
            ],
            currently_raining=False,
            now=self.now,
        )

        self.assertIsNotNone(alert)

        assert alert is not None

        self.assertEqual(
            alert.forecast_within_minutes,
            120,
        )


if __name__ == "__main__":
    unittest.main()
