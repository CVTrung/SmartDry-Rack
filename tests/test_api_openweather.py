import os
import unittest

from fastapi.testclient import TestClient

from backend.auth_dependency import get_current_account
from backend.main import app

RUN_INTEGRATION_TESTS = (
    os.getenv("RUN_OPENWEATHER_INTEGRATION_TESTS")
    == "1"
)


@unittest.skipUnless(
    RUN_INTEGRATION_TESTS,
    "Set RUN_OPENWEATHER_INTEGRATION_TESTS=1 "
    "to run real OpenWeather tests",
)

class TestWeatherAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_current_account] = lambda: {
            "device_id": "test_device",
            "display_name": "Test Device",
            "enabled": True,
        }

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(
            get_current_account,
            None,
        )

    def test_get_current_weather_from_real_api(self) -> None:
        response = self.client.get("/api/weather/current")

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        data = response.json()

        self.assertIn("temperature_celsius", data)
        self.assertIn("humidity_percent", data)
        self.assertIn("observed_at", data)

        self.assertIsNotNone(data["temperature_celsius"])
        self.assertIsNotNone(data["humidity_percent"])

    def test_get_real_forecast(self) -> None:
        response = self.client.get(
            "/api/weather/forecast",
            params={"hours": 24},
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        data = response.json()

        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)
        self.assertGreater(len(data["items"]), 0)

        first_forecast = data["items"][0]

        self.assertIn(
            "rain_probability_percent",
            first_forecast,
        )
        self.assertIn(
            "forecast_within_minutes",
            first_forecast,
        )


if __name__ == "__main__":
    unittest.main()