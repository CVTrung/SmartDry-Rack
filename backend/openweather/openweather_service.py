from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from backend.config import (
    OpenWeatherSettings,
    get_settings,
)
from backend.models import (
    CurrentWeather,
    ForecastItem,
)

class OpenWeatherError(RuntimeError):
    """Lỗi xảy ra khi gọi hoặc xử lý dữ liệu OpenWeather."""


class OpenWeatherService:
    BASE_URL = "https://api.openweathermap.org/data/2.5"

    def __init__(
        self,
        api_key: str,
        latitude: float,
        longitude: float,
        timeout: int = 10,
    ) -> None:
        if not api_key:
            raise ValueError("OPENWEATHER_API_KEY không được để trống")

        if not -90 <= latitude <= 90:
            raise ValueError("Latitude phải nằm trong khoảng -90 đến 90")

        if not -180 <= longitude <= 180:
            raise ValueError("Longitude phải nằm trong khoảng -180 đến 180")

        self.api_key = api_key
        self.latitude = latitude
        self.longitude = longitude
        self.timeout = timeout
        self.session = requests.Session()

    @classmethod
    def from_settings(
        cls,
        settings: OpenWeatherSettings,
    ) -> "OpenWeatherService":
        """Create the service from validated settings."""

        if not isinstance(
            settings,
            OpenWeatherSettings,
        ):
            raise TypeError(
                "settings must be OpenWeatherSettings"
            )

        return cls(
            api_key=settings.api_key,
            latitude=settings.latitude,
            longitude=settings.longitude,
            timeout=settings.timeout_seconds,
        )


    @classmethod
    def from_config(
        cls,
    ) -> "OpenWeatherService":
        """Create the service from centralized app config."""

        return cls.from_settings(
            get_settings().openweather
        )


    @classmethod
    def from_env(
        cls,
    ) -> "OpenWeatherService":
        """
        Backward-compatible alias.

        Prefer from_config() in new application code.
        """

        return cls.from_config()

    def _request(
        self,
        endpoint: str,
        **params: Any,
    ) -> dict[str, Any]:

        # Default params
        params.setdefault("appid", self.api_key)
        params.setdefault("lat", self.latitude)
        params.setdefault("lon", self.longitude)
        params.setdefault("units", "metric")
        params.setdefault("lang", "vi")

        try:
            response = self.session.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params,
                timeout=self.timeout,
            )

            if response.status_code == 401:
                raise OpenWeatherError(
                    "OpenWeather API key không hợp lệ hoặc chưa được kích hoạt"
                )

            if response.status_code == 429:
                raise OpenWeatherError(
                    "Đã vượt quá giới hạn số lần gọi OpenWeather API"
                )

            response.raise_for_status()
            result = response.json()

            if not isinstance(result, dict):
                raise OpenWeatherError(
                    "OpenWeather trả về dữ liệu không hợp lệ"
                )

            return result

        except requests.Timeout as error:
            raise OpenWeatherError(
                "OpenWeather phản hồi quá thời gian cho phép"
            ) from error

        except requests.RequestException as error:
            raise OpenWeatherError(
                f"Không thể kết nối OpenWeather: {error}"
            ) from error

        except ValueError as error:
            raise OpenWeatherError(
                "Không thể đọc JSON trả về từ OpenWeather"
            ) from error

    def get_current_weather(self) -> CurrentWeather:
        """Lấy và chuẩn hóa thông tin thời tiết hiện tại."""

        data = self._request("weather")

        main = data.get("main", {})
        weather_items = data.get("weather") or [{}]
        weather = weather_items[0]
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        rain = data.get("rain", {})

        timestamp = data.get("dt")
        observed_at = None

        if timestamp is not None:
            observed_at = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

        return CurrentWeather(
            location=data.get("name"),
            observed_at=observed_at,
            temperature_celsius=main.get("temp"),
            feels_like_celsius=main.get(
                "feels_like"
            ),
            humidity_percent=main.get("humidity"),
            pressure_hpa=main.get("pressure"),
            condition=weather.get("main"),
            description=weather.get("description"),
            cloud_cover_percent=clouds.get("all"),
            wind_speed_mps=wind.get("speed"),
            rain_last_1h_mm=rain.get("1h", 0),
        )

    def get_forecast(
        self,
        hours: int = 24,
    ) -> list[ForecastItem]:
        """Lấy dự báo theo từng khoảng ba giờ."""

        if hours <= 0 or hours > 120:
            raise ValueError("hours phải nằm trong khoảng 1 đến 120")

        data = self._request("forecast")
        intervals = data.get("list", [])

        now = datetime.now(timezone.utc)
        until = now + timedelta(hours=hours)

        forecasts: list[ForecastItem] = []

        for interval in intervals:
            timestamp = interval.get("dt")

            if timestamp is None:
                continue

            forecast_time = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

            if forecast_time > until:
                break

            main = interval.get("main", {})
            weather_items = interval.get("weather") or [{}]
            weather = weather_items[0]
            rain = interval.get("rain", {})
            clouds = interval.get("clouds", {})
            pop = interval.get("pop")

            forecasts.append(
                ForecastItem(
                    forecast_at=forecast_time,
                    forecast_within_minutes=max(
                        0,
                        round(
                            (
                                forecast_time - now
                            ).total_seconds()
                            / 60
                        ),
                    ),
                    temperature_celsius=main.get(
                        "temp"
                    ),
                    humidity_percent=main.get(
                        "humidity"
                    ),
                    condition=weather.get("main"),
                    description=weather.get(
                        "description"
                    ),
                    rain_probability_percent=(
                        round(float(pop) * 100)
                        if pop is not None
                        else None
                    ),
                    rain_amount_mm=rain.get(
                        "3h",
                        0,
                    ),
                    cloud_cover_percent=clouds.get(
                        "all"
                    ),
                )
            )

        return forecasts