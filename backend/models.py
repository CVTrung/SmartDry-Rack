import hashlib

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AlertType(str, Enum):
    CURRENT_RAIN = "current_rain"
    NEAR_FORECAST_RAIN = "near_forecast_rain"


class EmailStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class EmailContent:
    subject: str
    body: str


@dataclass(frozen=True)
class WeatherAlert:
    alert_key: str
    alert_type: AlertType

    device_id: str
    location_id: str
    reason: str
    scan_id: str | None = None

    observed_at: datetime | None = None
    rain_started_at: datetime | None = None
    forecast_at: datetime | None = None

    forecast_within_minutes: int | None = None
    rain_probability_percent: int | None = None
    rain_amount_mm: float | None = None
    condition: str | None = None

    def __post_init__(self) -> None:
        if not self.alert_key.strip():
            raise ValueError(
                "alert_key must not be empty"
            )

        if not self.device_id.strip():
            raise ValueError(
                "device_id must not be empty"
            )

        if not self.location_id.strip():
            raise ValueError(
                "location_id must not be empty"
            )

        if not self.reason.strip():
            raise ValueError(
                "reason must not be empty"
            )

        if (
            self.scan_id is not None
            and not self.scan_id.strip()
        ):
            raise ValueError(
                "scan_id must not be empty"
            )

        self._validate_datetime(
            self.observed_at,
            "observed_at",
        )
        self._validate_datetime(
            self.rain_started_at,
            "rain_started_at",
        )
        self._validate_datetime(
            self.forecast_at,
            "forecast_at",
        )

        if (
            self.forecast_within_minutes is not None
            and self.forecast_within_minutes < 0
        ):
            raise ValueError(
                "forecast_within_minutes "
                "must not be negative"
            )

        if (
            self.rain_probability_percent is not None
            and not (
                0
                <= self.rain_probability_percent
                <= 100
            )
        ):
            raise ValueError(
                "rain_probability_percent must be "
                "between 0 and 100"
            )

        if (
            self.rain_amount_mm is not None
            and self.rain_amount_mm < 0
        ):
            raise ValueError(
                "rain_amount_mm must not be negative"
            )

        if self.alert_type == AlertType.CURRENT_RAIN:
            if self.observed_at is None:
                raise ValueError(
                    "Current-rain alert requires observed_at"
                )

            if self.rain_started_at is None:
                raise ValueError(
                    "Current-rain alert requires "
                    "rain_started_at"
                )

        if (
            self.alert_type
            == AlertType.NEAR_FORECAST_RAIN
        ):
            if self.forecast_at is None:
                raise ValueError(
                    "Forecast alert requires forecast_at"
                )

            if self.forecast_within_minutes is None:
                raise ValueError(
                    "Forecast alert requires "
                    "forecast_within_minutes"
                )

            if self.rain_probability_percent is None:
                raise ValueError(
                    "Forecast alert requires "
                    "rain_probability_percent"
                )

    @staticmethod
    def _validate_datetime(
        value: datetime | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if value.tzinfo is None:
            raise ValueError(
                f"{field_name} must include timezone information"
            )

    @staticmethod
    def _utc_text(value: datetime) -> str:
        return (
            value
            .astimezone(timezone.utc)
            .isoformat()
        )

    @property
    def alert_id(self) -> str:
        identity = self.alert_key

        if self.scan_id is not None:
            identity = (
                f"{identity}:scan:{self.scan_id}"
            )

        return hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()

    @classmethod
    def current_rain(
        cls,
        *,
        device_id: str,
        location_id: str,
        observed_at: datetime,
        rain_started_at: datetime,
        condition: str | None,
        rain_amount_mm: float | None,
        scan_id: str | None = None,
    ) -> "WeatherAlert":
        alert_key = (
            f"current_rain:"
            f"{device_id}:"
            f"{location_id}:"
            f"{cls._utc_text(rain_started_at)}"
        )

        return cls(
            alert_key=alert_key,
            alert_type=AlertType.CURRENT_RAIN,
            device_id=device_id,
            location_id=location_id,
            reason="Rain is happening now",
            scan_id=scan_id,
            observed_at=observed_at,
            rain_started_at=rain_started_at,
            rain_amount_mm=rain_amount_mm,
            condition=condition,
        )

    @classmethod
    def near_forecast_rain(
        cls,
        *,
        device_id: str,
        location_id: str,
        forecast_at: datetime,
        forecast_within_minutes: int,
        rain_probability_percent: int,
        rain_amount_mm: float | None,
        condition: str | None,
        scan_id: str | None = None,
    ) -> "WeatherAlert":
        alert_key = (
            f"forecast_rain:"
            f"{device_id}:"
            f"{location_id}:"
            f"{cls._utc_text(forecast_at)}"
        )

        return cls(
            alert_key=alert_key,
            alert_type=(
                AlertType.NEAR_FORECAST_RAIN
            ),
            device_id=device_id,
            location_id=location_id,
            reason="Rain is expected soon",
            scan_id=scan_id,
            forecast_at=forecast_at,
            forecast_within_minutes=(
                forecast_within_minutes
            ),
            rain_probability_percent=(
                rain_probability_percent
            ),
            rain_amount_mm=rain_amount_mm,
            condition=condition,
        )

    def weather_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}

        if self.observed_at is not None:
            snapshot["observed_at"] = (
                self.observed_at
            )

        if self.rain_started_at is not None:
            snapshot["rain_started_at"] = (
                self.rain_started_at
            )

        if self.forecast_at is not None:
            snapshot["forecast_at"] = (
                self.forecast_at
            )

        if self.forecast_within_minutes is not None:
            snapshot["forecast_within_minutes"] = (
                self.forecast_within_minutes
            )

        if self.rain_probability_percent is not None:
            snapshot["rain_probability_percent"] = (
                self.rain_probability_percent
            )

        if self.rain_amount_mm is not None:
            snapshot["rain_amount_mm"] = (
                self.rain_amount_mm
            )

        if self.condition is not None:
            snapshot["condition"] = self.condition

        return snapshot


@dataclass(frozen=True)
class NotificationResult:
    notification_id: str
    created: bool
    email_status: EmailStatus
    gmail_message_id: str | None = None
    error: str | None = None

@dataclass(frozen=True)
class CurrentWeather:
    location: str | None
    observed_at: datetime | None

    temperature_celsius: float | None
    feels_like_celsius: float | None
    humidity_percent: int | None
    pressure_hpa: int | None

    condition: str | None
    description: str | None

    cloud_cover_percent: int | None
    wind_speed_mps: float | None
    rain_last_1h_mm: float

    def __post_init__(self) -> None:
        if (
            self.observed_at is not None
            and self.observed_at.tzinfo is None
        ):
            raise ValueError(
                "observed_at must include "
                "timezone information"
            )

        self._validate_percentage(
            self.humidity_percent,
            "humidity_percent",
        )
        self._validate_percentage(
            self.cloud_cover_percent,
            "cloud_cover_percent",
        )

        if self.rain_last_1h_mm < 0:
            raise ValueError(
                "rain_last_1h_mm must not "
                "be negative"
            )

    @staticmethod
    def _validate_percentage(
        value: int | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if not 0 <= value <= 100:
            raise ValueError(
                f"{field_name} must be "
                "between 0 and 100"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "observed_at": self.observed_at,
            "temperature_celsius": (
                self.temperature_celsius
            ),
            "feels_like_celsius": (
                self.feels_like_celsius
            ),
            "humidity_percent": (
                self.humidity_percent
            ),
            "pressure_hpa": self.pressure_hpa,
            "condition": self.condition,
            "description": self.description,
            "cloud_cover_percent": (
                self.cloud_cover_percent
            ),
            "wind_speed_mps": (
                self.wind_speed_mps
            ),
            "rain_last_1h_mm": (
                self.rain_last_1h_mm
            ),
        }


@dataclass(frozen=True)
class ForecastItem:
    forecast_at: datetime
    forecast_within_minutes: int

    temperature_celsius: float | None
    humidity_percent: int | None

    condition: str | None
    description: str | None

    rain_probability_percent: int | None
    rain_amount_mm: float
    cloud_cover_percent: int | None

    def __post_init__(self) -> None:
        if self.forecast_at.tzinfo is None:
            raise ValueError(
                "forecast_at must include "
                "timezone information"
            )

        if self.forecast_within_minutes < 0:
            raise ValueError(
                "forecast_within_minutes must "
                "not be negative"
            )

        self._validate_percentage(
            self.humidity_percent,
            "humidity_percent",
        )
        self._validate_percentage(
            self.rain_probability_percent,
            "rain_probability_percent",
        )
        self._validate_percentage(
            self.cloud_cover_percent,
            "cloud_cover_percent",
        )

        if self.rain_amount_mm < 0:
            raise ValueError(
                "rain_amount_mm must not "
                "be negative"
            )

    @staticmethod
    def _validate_percentage(
        value: int | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if not 0 <= value <= 100:
            raise ValueError(
                f"{field_name} must be "
                "between 0 and 100"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecast_at": self.forecast_at,
            "forecast_within_minutes": (
                self.forecast_within_minutes
            ),
            "temperature_celsius": (
                self.temperature_celsius
            ),
            "humidity_percent": (
                self.humidity_percent
            ),
            "condition": self.condition,
            "description": self.description,
            "rain_probability_percent": (
                self.rain_probability_percent
            ),
            "rain_amount_mm": (
                self.rain_amount_mm
            ),
            "cloud_cover_percent": (
                self.cloud_cover_percent
            ),
        }
