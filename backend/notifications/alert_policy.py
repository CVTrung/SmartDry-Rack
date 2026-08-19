from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from backend.config import (
    WeatherNotificationSettings,
)
from backend.models import WeatherAlert


RAIN_CONDITIONS = {
    "rain",
    "drizzle",
    "thunderstorm",
}


@dataclass(frozen=True)
class CurrentWeatherEvaluation:
    is_raining: bool
    rain_started_at: datetime | None
    weather_document: dict[str, Any]
    alert: WeatherAlert | None


class WeatherAlertPolicy:
    def __init__(
        self,
        settings: WeatherNotificationSettings,
    ) -> None:
        self.settings = settings

    @staticmethod
    def _current_utc_time() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            normalized = value.strip()

            if not normalized:
                return None

            if normalized.endswith("Z"):
                normalized = (
                    normalized[:-1] + "+00:00"
                )

            try:
                parsed = datetime.fromisoformat(
                    normalized
                )
            except ValueError:
                return None
        else:
            return None

        if parsed.tzinfo is None:
            return None

        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _as_float(
        value: Any,
    ) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _as_integer(
        value: Any,
    ) -> int | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    @classmethod
    def is_raining(
        cls,
        current_weather: Mapping[str, Any],
    ) -> bool:
        raw_condition = current_weather.get(
            "condition"
        )

        condition = (
            str(raw_condition).strip().lower()
            if raw_condition is not None
            else ""
        )

        rain_amount = cls._as_float(
            current_weather.get(
                "rain_last_1h_mm"
            )
        )

        return (
            condition in RAIN_CONDITIONS
            or (
                rain_amount is not None
                and rain_amount > 0
            )
        )

    def evaluate_current_weather(
        self,
        *,
        current_weather: Mapping[str, Any],
        previous_weather: Mapping[str, Any] | None,
        now: datetime | None = None,
    ) -> CurrentWeatherEvaluation:
        current_time = (
            now
            if now is not None
            else self._current_utc_time()
        )

        if current_time.tzinfo is None:
            raise ValueError(
                "now must include timezone information"
            )

        current_time = current_time.astimezone(
            timezone.utc
        )

        observed_at = self._parse_datetime(
            current_weather.get("observed_at")
        )

        if observed_at is None:
            observed_at = current_time

        raining_now = self.is_raining(
            current_weather
        )

        previously_raining = bool(
            previous_weather
            and previous_weather.get(
                "is_raining"
            ) is True
        )

        previous_rain_started_at = None

        if previous_weather is not None:
            previous_rain_started_at = (
                self._parse_datetime(
                    previous_weather.get(
                        "rain_started_at"
                    )
                )
            )

        if raining_now:
            rain_started_at = (
                previous_rain_started_at
                if previously_raining
                and previous_rain_started_at
                is not None
                else observed_at
            )
        else:
            rain_started_at = None

        weather_document = dict(current_weather)

        weather_document["observed_at"] = (
            observed_at
        )
        weather_document["is_raining"] = (
            raining_now
        )
        weather_document["rain_started_at"] = (
            rain_started_at
        )

        alert = None

        # Only create an alert when rain starts.
        if raining_now and not previously_raining:
            raw_condition = current_weather.get(
                "condition"
            )

            condition = (
                str(raw_condition)
                if raw_condition is not None
                else None
            )

            rain_amount = self._as_float(
                current_weather.get(
                    "rain_last_1h_mm"
                )
            )

            alert = WeatherAlert.current_rain(
                device_id=(
                    self.settings.device_id
                ),
                location_id=(
                    self.settings.location_id
                ),
                observed_at=observed_at,
                rain_started_at=rain_started_at,
                condition=condition,
                rain_amount_mm=rain_amount,
            )

        return CurrentWeatherEvaluation(
            is_raining=raining_now,
            rain_started_at=rain_started_at,
            weather_document=weather_document,
            alert=alert,
        )

    def _cooldown_is_active(
        self,
        *,
        last_forecast_alert_at: datetime | None,
        now: datetime,
    ) -> bool:
        if last_forecast_alert_at is None:
            return False

        if last_forecast_alert_at.tzinfo is None:
            raise ValueError(
                "last_forecast_alert_at must "
                "include timezone information"
            )

        last_alert = (
            last_forecast_alert_at
            .astimezone(timezone.utc)
        )

        cooldown = timedelta(
            minutes=self.settings.cooldown_minutes
        )

        elapsed = now - last_alert

        return (
            elapsed < timedelta(0)
            or elapsed < cooldown
        )

    def select_forecast_alert(
        self,
        *,
        forecasts: Sequence[Mapping[str, Any]],
        currently_raining: bool,
        last_forecast_alert_at: (
            datetime | None
        ) = None,
        now: datetime | None = None,
    ) -> WeatherAlert | None:
        if currently_raining:
            return None

        current_time = (
            now
            if now is not None
            else self._current_utc_time()
        )

        if current_time.tzinfo is None:
            raise ValueError(
                "now must include timezone information"
            )

        current_time = current_time.astimezone(
            timezone.utc
        )

        if self._cooldown_is_active(
            last_forecast_alert_at=(
                last_forecast_alert_at
            ),
            now=current_time,
        ):
            return None

        qualifying_forecasts: list[
            tuple[
                int,
                datetime,
                Mapping[str, Any],
            ]
        ] = []

        for forecast in forecasts:
            probability = self._as_integer(
                forecast.get(
                    "rain_probability_percent"
                )
            )

            minutes_until = self._as_integer(
                forecast.get(
                    "forecast_within_minutes"
                )
            )

            forecast_at = self._parse_datetime(
                forecast.get("forecast_at")
            )

            if (
                probability is None
                or minutes_until is None
                or forecast_at is None
            ):
                continue

            if (
                probability
                < self.settings.rain_threshold_percent
            ):
                continue

            if not (
                0
                <= minutes_until
                <= self.settings.warning_window_minutes
            ):
                continue

            qualifying_forecasts.append(
                (
                    minutes_until,
                    forecast_at,
                    forecast,
                )
            )

        if not qualifying_forecasts:
            return None

        # Alert for the nearest qualifying forecast.
        (
            minutes_until,
            forecast_at,
            forecast,
        ) = min(
            qualifying_forecasts,
            key=lambda item: item[0],
        )

        probability = self._as_integer(
            forecast.get(
                "rain_probability_percent"
            )
        )

        if probability is None:
            return None

        rain_amount = self._as_float(
            forecast.get("rain_amount_mm")
        )

        raw_condition = forecast.get("condition")

        condition = (
            str(raw_condition)
            if raw_condition is not None
            else None
        )

        return WeatherAlert.near_forecast_rain(
            device_id=self.settings.device_id,
            location_id=self.settings.location_id,
            forecast_at=forecast_at,
            forecast_within_minutes=(
                minutes_until
            ),
            rain_probability_percent=(
                probability
            ),
            rain_amount_mm=rain_amount,
            condition=condition,
        )