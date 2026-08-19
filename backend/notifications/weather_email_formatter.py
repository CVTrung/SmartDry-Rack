from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.models import (
    AlertType,
    EmailContent,
    WeatherAlert,
)


class WeatherEmailFormatter:
    @staticmethod
    def _timezone(
        timezone_name: str,
    ) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                f"Unknown timezone: {timezone_name}"
            ) from error

    @classmethod
    def _datetime_text(
        cls,
        value: datetime,
        timezone_name: str,
    ) -> str:
        timezone = cls._timezone(timezone_name)

        local_time = value.astimezone(timezone)

        return (
            local_time.strftime("%H:%M, %d %b %Y")
            + f" ({timezone_name})"
        )

    @classmethod
    def _short_time_text(
        cls,
        value: datetime,
        timezone_name: str,
    ) -> str:
        timezone = cls._timezone(timezone_name)
        return value.astimezone(timezone).strftime("%H:%M")

    @staticmethod
    def _location_text(
        location_id: str,
        location_name: str | None,
    ) -> str:
        if location_name and location_name.strip():
            return location_name.strip()

        normalized_id = location_id.strip().lower()
        readable_id = normalized_id.removeprefix(
            "location_"
        )
        readable_id = readable_id.replace("_", " ")
        readable_id = readable_id.replace("-", " ")

        return readable_id.title() or location_id

    @staticmethod
    def _duration_text(minutes: int) -> str:
        hours, remaining_minutes = divmod(
            minutes,
            60,
        )

        parts: list[str] = []

        if hours > 0:
            unit = "hour" if hours == 1 else "hours"
            parts.append(f"{hours} {unit}")

        if remaining_minutes > 0:
            unit = (
                "minute"
                if remaining_minutes == 1
                else "minutes"
            )
            parts.append(
                f"{remaining_minutes} {unit}"
            )

        if not parts:
            return "now"

        return " ".join(parts)

    @staticmethod
    def _rain_amount_text(
        rain_amount_mm: float | None,
    ) -> str | None:
        if rain_amount_mm is None:
            return None

        return f"{rain_amount_mm:g} mm"

    def _format_current_rain(
        self,
        alert: WeatherAlert,
        *,
        device_name: str,
        location_name: str,
        timezone_name: str,
    ) -> EmailContent:
        if alert.observed_at is None:
            raise ValueError(
                "Current-rain alert is missing observed_at"
            )

        if alert.rain_started_at is None:
            raise ValueError(
                "Current-rain alert is missing "
                "rain_started_at"
            )

        detected_time = self._short_time_text(
            alert.observed_at,
            timezone_name,
        )

        subject = (
            "[SmartDry][CURRENT] "
            f"{device_name} - Rain at {detected_time}"
        )

        lines = [
            "SmartDry urgent rain alert",
            "",
            (
                "Rain has been detected at "
                f"{location_name}."
            ),
            "",
            f"Location: {location_name}",
            (
                "Detected: "
                + self._datetime_text(
                    alert.observed_at,
                    timezone_name,
                )
            ),
            (
                "Rain began: "
                + self._datetime_text(
                    alert.rain_started_at,
                    timezone_name,
                )
            ),
            f"Device: {device_name} ({alert.device_id})",
        ]

        lines.extend([
            "",
            "Action required:",
            "- Make sure the drying rack is retracted.",
            "- Protect any clothes still exposed to rain.",
        ])

        return EmailContent(
            subject=subject,
            body="\n".join(lines),
        )

    def _format_forecast_rain(
        self,
        alert: WeatherAlert,
        *,
        device_name: str,
        location_name: str,
        timezone_name: str,
    ) -> EmailContent:
        if alert.forecast_at is None:
            raise ValueError(
                "Forecast alert is missing forecast_at"
            )

        if alert.forecast_within_minutes is None:
            raise ValueError(
                "Forecast alert is missing "
                "forecast_within_minutes"
            )

        if alert.rain_probability_percent is None:
            raise ValueError(
                "Forecast alert is missing "
                "rain_probability_percent"
            )

        duration = self._duration_text(
            alert.forecast_within_minutes
        )

        forecast_time = self._short_time_text(
            alert.forecast_at,
            timezone_name,
        )

        subject = (
            "[SmartDry][FORECAST] "
            f"{device_name} - Rain at {forecast_time}"
        )

        lines = [
            "SmartDry rain forecast",
            "",
            (
                f"Rain may reach {location_name} "
                f"in {duration}."
            ),
            "",
            f"Location: {location_name}",
            (
                "Expected: "
                + self._datetime_text(
                    alert.forecast_at,
                    timezone_name,
                )
            ),
            (
                "Rain probability: "
                f"{alert.rain_probability_percent}%"
            ),
            f"Device: {device_name} ({alert.device_id})",
        ]

        rain_amount = self._rain_amount_text(
            alert.rain_amount_mm
        )

        if rain_amount is not None:
            lines.append(
                f"Expected rain amount: {rain_amount}"
            )

        lines.extend([
            "",
            "Recommended action:",
            "- Check the rack before the expected rain time.",
            "- Retract it if clothes are still outside.",
            "",
            "SmartDry will continue monitoring the weather.",
        ])

        return EmailContent(
            subject=subject,
            body="\n".join(lines),
        )

    def format(
        self,
        alert: WeatherAlert,
        *,
        device_name: str | None = None,
        location_name: str | None = None,
        timezone_name: str = "UTC",
    ) -> EmailContent:
        display_location = self._location_text(
            alert.location_id,
            location_name,
        )
        display_device = (
            device_name.strip()
            if device_name and device_name.strip()
            else alert.device_id
        )

        if alert.alert_type == AlertType.CURRENT_RAIN:
            return self._format_current_rain(
                alert,
                device_name=display_device,
                location_name=display_location,
                timezone_name=timezone_name,
            )

        if (
            alert.alert_type
            == AlertType.NEAR_FORECAST_RAIN
        ):
            return self._format_forecast_rain(
                alert,
                device_name=display_device,
                location_name=display_location,
                timezone_name=timezone_name,
            )

        raise ValueError(
            f"Unsupported alert type: {alert.alert_type}"
        )
