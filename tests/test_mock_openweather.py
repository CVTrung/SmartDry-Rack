import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


# Cho phép import backend khi chạy trực tiếp từ tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


import requests

from backend.openweather import (
    OpenWeatherError,
    OpenWeatherService,
)


class TestOpenWeatherService(unittest.TestCase):
    def setUp(self) -> None:
        """Tạo service mới trước mỗi test."""

        self.service = OpenWeatherService(
            api_key="fake-api-key",
            latitude=10.8231,
            longitude=106.6297,
        )

    def test_get_current_weather(self) -> None:
        """Kiểm tra chuẩn hóa dữ liệu thời tiết hiện tại."""

        mock_response = {
            "name": "Ho Chi Minh City",
            "dt": 1786417200,
            "main": {
                "temp": 30.5,
                "feels_like": 34.2,
                "humidity": 75,
                "pressure": 1008,
            },
            "weather": [
                {
                    "main": "Rain",
                    "description": "mưa nhẹ",
                }
            ],
            "clouds": {
                "all": 80,
            },
            "wind": {
                "speed": 3.5,
            },
            "rain": {
                "1h": 1.2,
            },
        }

        with patch.object(
            self.service,
            "_request",
            return_value=mock_response,
        ) as mock_request:
            result = self.service.get_current_weather()

        mock_request.assert_called_once_with("weather")

        self.assertEqual(
            result["location"],
            "Ho Chi Minh City",
        )
        self.assertEqual(
            result["temperature_celsius"],
            30.5,
        )
        self.assertEqual(
            result["feels_like_celsius"],
            34.2,
        )
        self.assertEqual(
            result["humidity_percent"],
            75,
        )
        self.assertEqual(
            result["condition"],
            "Rain",
        )
        self.assertEqual(
            result["description"],
            "mưa nhẹ",
        )
        self.assertEqual(
            result["cloud_cover_percent"],
            80,
        )
        self.assertEqual(
            result["wind_speed_mps"],
            3.5,
        )
        self.assertEqual(
            result["rain_last_1h_mm"],
            1.2,
        )
        self.assertIsNotNone(result["observed_at"])

    def test_get_current_weather_without_rain(self) -> None:
        """Nếu response không có rain thì lượng mưa mặc định bằng 0."""

        mock_response = {
            "name": "Ho Chi Minh City",
            "main": {
                "temp": 31,
                "humidity": 70,
            },
            "weather": [
                {
                    "main": "Clear",
                    "description": "trời quang",
                }
            ],
        }

        with patch.object(
            self.service,
            "_request",
            return_value=mock_response,
        ):
            result = self.service.get_current_weather()

        self.assertEqual(result["rain_last_1h_mm"], 0)
        self.assertIsNone(result["observed_at"])

    def test_get_forecast(self) -> None:
        """Kiểm tra chuẩn hóa dữ liệu dự báo."""

        forecast_time = (
            datetime.now(timezone.utc)
            + timedelta(hours=3)
        )

        mock_response = {
            "list": [
                {
                    "dt": int(forecast_time.timestamp()),
                    "main": {
                        "temp": 29.5,
                        "humidity": 82,
                    },
                    "weather": [
                        {
                            "main": "Rain",
                            "description": "mưa vừa",
                        }
                    ],
                    "pop": 0.75,
                    "rain": {
                        "3h": 2.4,
                    },
                    "clouds": {
                        "all": 90,
                    },
                }
            ]
        }

        with patch.object(
            self.service,
            "_request",
            return_value=mock_response,
        ) as mock_request:
            result = self.service.get_forecast(hours=24)

        mock_request.assert_called_once_with("forecast")

        self.assertEqual(len(result), 1)

        forecast = result[0]

        self.assertEqual(
            forecast["temperature_celsius"],
            29.5,
        )
        self.assertEqual(
            forecast["humidity_percent"],
            82,
        )
        self.assertEqual(
            forecast["condition"],
            "Rain",
        )
        self.assertEqual(
            forecast["description"],
            "mưa vừa",
        )
        self.assertEqual(
            forecast["rain_probability_percent"],
            75,
        )
        self.assertEqual(
            forecast["rain_amount_mm"],
            2.4,
        )
        self.assertEqual(
            forecast["cloud_cover_percent"],
            90,
        )

        # Có thể lệch khoảng một phút do thời gian chạy test.
        self.assertGreaterEqual(
            forecast["forecast_within_minutes"],
            179,
        )
        self.assertLessEqual(
            forecast["forecast_within_minutes"],
            180,
        )

    def test_forecast_without_pop_returns_none(self) -> None:
        """Nếu OpenWeather không trả pop thì kết quả là None."""

        forecast_time = (
            datetime.now(timezone.utc)
            + timedelta(hours=3)
        )

        mock_response = {
            "list": [
                {
                    "dt": int(forecast_time.timestamp()),
                    "main": {},
                    "weather": [],
                    "rain": {},
                    "clouds": {},
                }
            ]
        }

        with patch.object(
            self.service,
            "_request",
            return_value=mock_response,
        ):
            result = self.service.get_forecast(hours=24)

        self.assertEqual(len(result), 1)
        self.assertIsNone(
            result[0]["rain_probability_percent"]
        )

    def test_forecast_skips_item_without_timestamp(self) -> None:
        """Mốc dự báo thiếu dt phải được bỏ qua."""

        mock_response = {
            "list": [
                {
                    "main": {
                        "temp": 30,
                    },
                    "pop": 0.5,
                }
            ]
        }

        with patch.object(
            self.service,
            "_request",
            return_value=mock_response,
        ):
            result = self.service.get_forecast(hours=24)

        self.assertEqual(result, [])

    def test_forecast_rejects_invalid_hours(self) -> None:
        """Chỉ chấp nhận khoảng dự báo từ 1 đến 120 giờ."""

        with self.assertRaises(ValueError):
            self.service.get_forecast(hours=0)

        with self.assertRaises(ValueError):
            self.service.get_forecast(hours=121)

    def test_request_adds_default_parameters(self) -> None:
        """Kiểm tra các query parameter gửi tới OpenWeather."""

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "name": "Ho Chi Minh City"
        }

        self.service.session.get = MagicMock(
            return_value=response
        )

        result = self.service._request("weather")

        self.assertEqual(
            result["name"],
            "Ho Chi Minh City",
        )

        self.service.session.get.assert_called_once()

        call_arguments = (
            self.service.session.get.call_args
        )

        self.assertEqual(
            call_arguments.kwargs["params"],
            {
                "appid": "fake-api-key",
                "lat": 10.8231,
                "lon": 106.6297,
                "units": "metric",
                "lang": "vi",
            },
        )

        self.assertEqual(
            call_arguments.kwargs["timeout"],
            10,
        )

    def test_request_handles_invalid_api_key(self) -> None:
        """Response 401 phải tạo OpenWeatherError."""

        response = MagicMock()
        response.status_code = 401

        self.service.session.get = MagicMock(
            return_value=response
        )

        with self.assertRaises(OpenWeatherError):
            self.service._request("weather")

    def test_request_handles_rate_limit(self) -> None:
        """Response 429 phải tạo OpenWeatherError."""

        response = MagicMock()
        response.status_code = 429

        self.service.session.get = MagicMock(
            return_value=response
        )

        with self.assertRaises(OpenWeatherError):
            self.service._request("weather")

    def test_request_handles_timeout(self) -> None:
        """Timeout phải được chuyển thành OpenWeatherError."""

        self.service.session.get = MagicMock(
            side_effect=requests.Timeout()
        )

        with self.assertRaises(OpenWeatherError):
            self.service._request("weather")


if __name__ == "__main__":
    unittest.main()