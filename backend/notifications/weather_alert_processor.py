from datetime import datetime
from typing import Any, Mapping, Protocol

from backend.config import (
    WeatherNotificationSettings,
)

from backend.models import NotificationResult

from backend.notifications.alert_policy import (
    WeatherAlertPolicy,
)

from backend.notifications.weather_notification_service import (
    WeatherNotificationService,
)

from backend.models import (
    CurrentWeather,
    ForecastItem,
    NotificationResult,
)

class WeatherProvider(Protocol):
    def get_current_weather(
        self,
    ) -> CurrentWeather:
        """Fetch current weather."""

    def get_forecast(
        self,
        hours: int = 24,
    ) -> list[ForecastItem]:
        """Fetch the weather forecast."""


class WeatherRepository(Protocol):
    def get_current_weather(
        self,
        location_id: str,
    ) -> CurrentWeather | None:
        """Read stored current weather."""

    def set_current_weather(
        self,
        *,
        location_id: str,
        weather: Mapping[str, Any],
        is_raining: bool,
        rain_started_at: datetime | None,
    ) -> str:
        """Store current weather and rain state."""

    def set_latest_forecast(
        self,
        *,
        location_id: str,
        forecasts: list[Mapping[str, Any]],
    ) -> str:
        """Store the latest forecast."""

    def get_latest_forecast_notification(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        """Read the latest forecast notification."""


class WeatherAlertProcessor:
    def __init__(
        self,
        *,
        weather_provider: WeatherProvider,
        repository: WeatherRepository,
        alert_policy: WeatherAlertPolicy,
        notification_service: WeatherNotificationService,
        settings: WeatherNotificationSettings,
    ) -> None:
        self.weather_provider = weather_provider
        self.repository = repository
        self.alert_policy = alert_policy
        self.notification_service = (
            notification_service
        )
        self.settings = settings

    @staticmethod
    def _notification_created_at(
        notification: Mapping[str, Any] | None,
    ) -> datetime | None:
        if notification is None:
            return None

        created_at = notification.get(
            "created_at"
        )

        if not isinstance(created_at, datetime):
            return None

        if created_at.tzinfo is None:
            return None

        return created_at

    def check_current_weather(
        self,
        *,
        device_name: str | None = None,
        location_name: str | None = None,
        timezone_name: str = "UTC",
    ) -> NotificationResult | None:
        current_weather_model = (
            self.weather_provider
            .get_current_weather()
        )

        current_weather = (
            current_weather_model.to_dict()
        )

        previous_weather = (
            self.repository.get_current_weather(
                self.settings.location_id
            )
        )

        evaluation = (
            self.alert_policy
            .evaluate_current_weather(
                current_weather=current_weather,
                previous_weather=previous_weather,
            )
        )

        # Store the weather state before attempting Gmail.
        self.repository.set_current_weather(
            location_id=self.settings.location_id,
            weather=evaluation.weather_document,
            is_raining=evaluation.is_raining,
            rain_started_at=(
                evaluation.rain_started_at
            ),
        )

        if evaluation.alert is None:
            return None

        return self.notification_service.notify(
            evaluation.alert,
            device_name=device_name,
            location_name=location_name,
            timezone_name=timezone_name,
        )

    def check_forecast(
        self,
        *,
        device_name: str | None = None,
        location_name: str | None = None,
        timezone_name: str = "UTC",
    ) -> NotificationResult | None:
        forecast_models = (
            self.weather_provider.get_forecast(
                hours=(
                    self.settings
                    .forecast_horizon_hours
                )
            )
        )

        forecasts = [
            forecast.to_dict()
            for forecast in forecast_models
        ]

        # Save the full forecast whether or not it causes an alert.
        self.repository.set_latest_forecast(
            location_id=self.settings.location_id,
            forecasts=forecasts,
        )

        current_weather = (
            self.repository.get_current_weather(
                self.settings.location_id
            )
        )

        currently_raining = bool(
            current_weather
            and current_weather.get(
                "is_raining"
            ) is True
        )

        latest_notification = (
            self.repository
            .get_latest_forecast_notification(
                self.settings.device_id
            )
        )

        last_alert_at = (
            self._notification_created_at(
                latest_notification
            )
        )

        alert = (
            self.alert_policy
            .select_forecast_alert(
                forecasts=forecasts,
                currently_raining=(
                    currently_raining
                ),
                last_forecast_alert_at=(
                    last_alert_at
                ),
            )
        )

        if alert is None:
            return None

        return self.notification_service.notify(
            alert,
            device_name=device_name,
            location_name=location_name,
            timezone_name=timezone_name,
        )
