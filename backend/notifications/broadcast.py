import logging

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from backend.config import (
    GmailSettings,
    OpenWeatherSettings,
    Settings,
    WeatherNotificationSettings,
)
from backend.models import (
    EmailStatus,
    NotificationResult,
    WeatherAlert,
)
from backend.notifications.email import (
    GmailNotificationError,
    GmailNotificationService,
    WeatherEmailFormatter,
)
from backend.notifications.policy import (
    CurrentWeatherEvaluation,
    WeatherAlertPolicy,
)
from backend.openweather import OpenWeatherService


logger = logging.getLogger(__name__)


class WeatherNotificationService:
    """Persist an alert, then deliver it through Gmail."""

    def __init__(
        self,
        *,
        repository: Any,
        gmail_service: GmailNotificationService,
        email_formatter: WeatherEmailFormatter,
        gmail_settings: GmailSettings,
    ) -> None:
        self.repository = repository
        self.gmail_service = gmail_service
        self.email_formatter = email_formatter
        self.gmail_settings = gmail_settings

    @staticmethod
    def _safe_error_message(error: Exception) -> str:
        message = str(error).strip()
        if not message:
            message = error.__class__.__name__
        return message[:500]

    def notify(
        self,
        alert: WeatherAlert,
        *,
        device_name: str | None = None,
        location_name: str | None = None,
        timezone_name: str = "UTC",
        recipient_email: str | None = None,
        email_authorized: bool = True,
    ) -> NotificationResult:
        if not isinstance(email_authorized, bool):
            raise TypeError(
                "email_authorized must be a boolean"
            )

        email_delivery_enabled = (
            self.gmail_settings.enabled
            and email_authorized
        )
        initial_email_status = (
            EmailStatus.PENDING
            if email_delivery_enabled
            else EmailStatus.SKIPPED
        )

        # Firestore is the source of truth and is written first.
        created = self.repository.create_notification(
            alert,
            email_status=initial_email_status,
        )
        if not created:
            return NotificationResult(
                notification_id=alert.alert_id,
                created=False,
                email_status=EmailStatus.SKIPPED,
            )
        if not email_delivery_enabled:
            return NotificationResult(
                notification_id=alert.alert_id,
                created=True,
                email_status=EmailStatus.SKIPPED,
            )

        try:
            content = self.email_formatter.format(
                alert,
                device_name=device_name,
                location_name=location_name,
                timezone_name=timezone_name,
            )
            send_arguments = {
                "subject": content.subject,
                "body": content.body,
            }
            if recipient_email is not None:
                send_arguments["recipient_email"] = (
                    recipient_email
                )
            gmail_message_id = self.gmail_service.send_email(
                **send_arguments
            )
        except (GmailNotificationError, ValueError) as error:
            error_message = self._safe_error_message(error)
            try:
                self.repository.mark_email_failed(
                    device_id=alert.device_id,
                    notification_id=alert.alert_id,
                    error_message=error_message,
                )
            except Exception:
                logger.exception(
                    "Could not record failed Gmail delivery "
                    "for notification %s",
                    alert.alert_id,
                )
            logger.warning(
                "Gmail notification failed for %s: %s",
                alert.alert_id,
                error_message,
            )
            return NotificationResult(
                notification_id=alert.alert_id,
                created=True,
                email_status=EmailStatus.FAILED,
                error=error_message,
            )

        self.repository.mark_email_sent(
            device_id=alert.device_id,
            notification_id=alert.alert_id,
            gmail_message_id=gmail_message_id,
        )
        return NotificationResult(
            notification_id=alert.alert_id,
            created=True,
            email_status=EmailStatus.SENT,
            gmail_message_id=gmail_message_id,
        )


@dataclass(frozen=True)
class WeatherLocation:
    location_id: str
    name: str
    timezone_name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class NotificationTarget:
    device_id: str
    device_name: str
    location_id: str
    location_name: str
    timezone_name: str
    latitude: float
    longitude: float
    gmail: str | None
    gmail_authorized: bool


class WeatherNotificationBroadcaster:
    """Check weather for every enabled Firebase account."""

    def __init__(
        self,
        *,
        repository: Any,
        notification_service: WeatherNotificationService,
        settings: Settings,
        provider_factory: Callable[
            [OpenWeatherSettings],
            Any,
        ] = OpenWeatherService.from_settings,
    ) -> None:
        self.repository = repository
        self.notification_service = notification_service
        self.settings = settings
        self.provider_factory = provider_factory

    @staticmethod
    def _required_text(
        value: Any,
    ) -> str | None:
        if not isinstance(value, str):
            return None

        value = value.strip()
        return value or None

    @staticmethod
    def _coordinate(
        value: Any,
        *,
        minimum: float,
        maximum: float,
    ) -> float | None:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
        ):
            return None

        coordinate = float(value)

        if not minimum <= coordinate <= maximum:
            return None

        return coordinate

    @classmethod
    def _gmail_address(
        cls,
        value: Any,
    ) -> str | None:
        gmail = cls._required_text(value)

        if gmail is None:
            return None

        gmail = gmail.lower()

        if (
            gmail.count("@") != 1
            or any(character.isspace() for character in gmail)
        ):
            return None

        local_part, domain = gmail.rsplit("@", 1)

        if (
            not local_part
            or domain not in {
                "gmail.com",
                "googlemail.com",
            }
        ):
            return None

        return gmail

    def _target_settings(
        self,
        target: NotificationTarget,
    ) -> WeatherNotificationSettings:
        return replace(
            self.settings.weather_notifications,
            device_id=target.device_id,
            location_id=target.location_id,
        )

    def _weather_provider(
        self,
        location: WeatherLocation,
    ) -> Any:
        weather_settings = replace(
            self.settings.openweather,
            latitude=location.latitude,
            longitude=location.longitude,
        )

        return self.provider_factory(weather_settings)

    def _load_locations(
        self,
    ) -> dict[str, WeatherLocation]:
        locations: dict[str, WeatherLocation] = {}

        for document in self.repository.get_locations():
            location_id = self._required_text(
                document.get("location_id")
                or document.get("document_id")
            )

            if location_id is None:
                logger.warning(
                    "Skipping a location without an ID"
                )
                continue

            latitude = self._coordinate(
                document.get("latitude"),
                minimum=-90,
                maximum=90,
            )
            longitude = self._coordinate(
                document.get("longitude"),
                minimum=-180,
                maximum=180,
            )

            if latitude is None or longitude is None:
                logger.warning(
                    "Skipping location %s because its "
                    "coordinates are invalid",
                    location_id,
                )
                continue

            locations[location_id] = WeatherLocation(
                location_id=location_id,
                name=(
                    self._required_text(
                        document.get("name")
                    )
                    or location_id
                ),
                timezone_name=(
                    self._required_text(
                        document.get("timezone")
                    )
                    or "UTC"
                ),
                latitude=latitude,
                longitude=longitude,
            )

        logger.info(
            "Prepared %d OpenWeather location(s)",
            len(locations),
        )
        return locations

    def _load_targets(
        self,
        locations: dict[str, WeatherLocation],
    ) -> list[NotificationTarget]:
        accounts = self.repository.get_enabled_accounts()
        targets: list[NotificationTarget] = []

        for account in accounts:
            device_id = self._required_text(
                account.get("device_id")
                or account.get("document_id")
            )

            if device_id is None:
                logger.warning(
                    "Skipping an enabled account without a device ID"
                )
                continue

            try:
                gmail = self._gmail_address(
                    account.get("gmail")
                )
                gmail_authorized = bool(
                    gmail is not None
                    and account.get("gmail_authorized")
                    is True
                )

                if (
                    account.get("gmail_authorized") is True
                    and gmail is None
                ):
                    logger.warning(
                        "Email delivery is skipped for account %s "
                        "because its authorized Gmail is invalid",
                        device_id,
                    )

                device = self.repository.get_device(device_id)

                if device is None:
                    logger.warning(
                        "Skipping account %s because its device "
                        "document does not exist",
                        device_id,
                    )
                    continue

                location_id = self._required_text(
                    device.get("location_id")
                )

                if location_id is None:
                    logger.warning(
                        "Skipping account %s because its device "
                        "has no location_id",
                        device_id,
                    )
                    continue

                location = locations.get(location_id)

                if location is None:
                    logger.warning(
                        "Skipping account %s because location %s "
                        "does not exist",
                        device_id,
                        location_id,
                    )
                    continue

                targets.append(
                    NotificationTarget(
                        device_id=device_id,
                        device_name=(
                            self._required_text(
                                account.get("display_name")
                            )
                            or device_id
                        ),
                        location_id=location_id,
                        location_name=location.name,
                        timezone_name=(
                            location.timezone_name
                        ),
                        latitude=location.latitude,
                        longitude=location.longitude,
                        gmail=gmail,
                        gmail_authorized=gmail_authorized,
                    )
                )
            except Exception:
                logger.exception(
                    "Could not prepare weather notifications "
                    "for account %s",
                    device_id,
                )

        logger.info(
            "Prepared %d weather notification target(s) "
            "from %d enabled account(s)",
            len(targets),
            len(accounts),
        )

        return targets

    @staticmethod
    def _group_by_location(
        targets: list[NotificationTarget],
    ) -> dict[str, list[NotificationTarget]]:
        grouped: dict[
            str,
            list[NotificationTarget],
        ] = defaultdict(list)

        for target in targets:
            grouped[target.location_id].append(target)

        return dict(grouped)

    @staticmethod
    def _notification_created_at(
        notification: dict[str, Any] | None,
    ) -> datetime | None:
        if notification is None:
            return None

        created_at = notification.get("created_at")

        if (
            not isinstance(created_at, datetime)
            or created_at.tzinfo is None
        ):
            return None

        return created_at

    def _send_evaluation_alerts(
        self,
        evaluations: list[
            tuple[
                NotificationTarget,
                CurrentWeatherEvaluation,
            ]
        ],
    ) -> list[NotificationResult]:
        results: list[NotificationResult] = []

        for target, evaluation in evaluations:
            if evaluation.alert is None:
                continue

            try:
                result = self.notification_service.notify(
                    evaluation.alert,
                    device_name=target.device_name,
                    location_name=target.location_name,
                    timezone_name=target.timezone_name,
                    recipient_email=target.gmail,
                    email_authorized=(
                        target.gmail_authorized
                    ),
                )
                results.append(result)
                logger.info(
                    "Current-weather notification for %s: "
                    "created=%s, email_status=%s",
                    target.device_id,
                    result.created,
                    result.email_status.value,
                )
            except Exception:
                logger.exception(
                    "Current-weather notification failed for "
                    "account %s",
                    target.device_id,
                )

        return results

    def _include_missing_current_rain_alerts(
        self,
        evaluations: list[
            tuple[
                NotificationTarget,
                CurrentWeatherEvaluation,
            ]
        ],
        scan_id: str,
    ) -> list[
        tuple[
            NotificationTarget,
            CurrentWeatherEvaluation,
        ]
    ]:
        completed: list[
            tuple[
                NotificationTarget,
                CurrentWeatherEvaluation,
            ]
        ] = []

        for target, evaluation in evaluations:
            if evaluation.alert is not None:
                completed.append(
                    (
                        target,
                        replace(
                            evaluation,
                            alert=replace(
                                evaluation.alert,
                                scan_id=scan_id,
                            ),
                        ),
                    )
                )
                continue

            if (
                not evaluation.is_raining
                or evaluation.rain_started_at is None
            ):
                completed.append((target, evaluation))
                continue

            observed_at = evaluation.weather_document.get(
                "observed_at"
            )

            if not isinstance(observed_at, datetime):
                completed.append((target, evaluation))
                continue

            raw_rain_amount = (
                evaluation.weather_document.get(
                    "rain_last_1h_mm"
                )
            )
            rain_amount = (
                float(raw_rain_amount)
                if isinstance(raw_rain_amount, (int, float))
                and not isinstance(raw_rain_amount, bool)
                else None
            )
            raw_condition = evaluation.weather_document.get(
                "condition"
            )
            alert = WeatherAlert.current_rain(
                device_id=target.device_id,
                location_id=target.location_id,
                observed_at=observed_at,
                rain_started_at=(
                    evaluation.rain_started_at
                ),
                condition=(
                    str(raw_condition)
                    if raw_condition is not None
                    else None
                ),
                rain_amount_mm=rain_amount,
            )

            latest_notification = (
                self.repository
                .get_latest_current_notification(
                    target.device_id
                )
            )
            event_was_notified = bool(
                latest_notification
                and latest_notification.get("alert_key")
                == alert.alert_key
            )

            completed.append(
                (
                    target,
                    (
                        evaluation
                        if event_was_notified
                        else replace(
                            evaluation,
                            alert=replace(
                                alert,
                                scan_id=scan_id,
                            ),
                        )
                    ),
                )
            )

        return completed

    def _process_current_scan(
        self,
        *,
        location_id: str,
        weather: Mapping[str, Any],
        targets: list[NotificationTarget],
        previous_weather: Mapping[str, Any] | None,
        scan_id: str | None = None,
    ) -> list[NotificationResult]:
        """Evaluate and broadcast one current-weather scan."""
        evaluations = [
            (
                target,
                WeatherAlertPolicy(
                    self._target_settings(target)
                ).evaluate_current_weather(
                    current_weather=weather,
                    previous_weather=previous_weather,
                ),
            )
            for target in targets
        ]

        if evaluations:
            state = evaluations[0][1]
        else:
            location_settings = replace(
                self.settings.weather_notifications,
                location_id=location_id,
            )
            state = WeatherAlertPolicy(
                location_settings
            ).evaluate_current_weather(
                current_weather=weather,
                previous_weather=previous_weather,
            )

        effective_scan_id = scan_id
        if effective_scan_id is None:
            effective_scan_id = (
                self.repository.set_current_weather(
                    location_id=location_id,
                    weather=state.weather_document,
                    is_raining=state.is_raining,
                    rain_started_at=state.rain_started_at,
                )
            )

        completed = self._include_missing_current_rain_alerts(
            evaluations,
            effective_scan_id,
        )
        return self._send_evaluation_alerts(completed)

    def _process_forecast_scan(
        self,
        *,
        forecasts: list[Mapping[str, Any]],
        targets: list[NotificationTarget],
        currently_raining: bool,
        scan_id: str,
        force_notify: bool = False,
    ) -> list[NotificationResult]:
        """Evaluate and broadcast one forecast scan."""
        results: list[NotificationResult] = []

        for target in targets:
            try:
                latest_notification = (
                    None
                    if force_notify
                    else self.repository
                    .get_latest_forecast_notification(
                        target.device_id
                    )
                )
                alert = WeatherAlertPolicy(
                    self._target_settings(target)
                ).select_forecast_alert(
                    forecasts=forecasts,
                    currently_raining=(
                        False
                        if force_notify
                        else currently_raining
                    ),
                    last_forecast_alert_at=(
                        self._notification_created_at(
                            latest_notification
                        )
                    ),
                )
                if alert is None:
                    continue

                results.append(
                    self.notification_service.notify(
                        replace(alert, scan_id=scan_id),
                        device_name=target.device_name,
                        location_name=target.location_name,
                        timezone_name=target.timezone_name,
                        recipient_email=target.gmail,
                        email_authorized=(
                            target.gmail_authorized
                        ),
                    )
                )
            except Exception:
                logger.exception(
                    "Forecast notification failed for "
                    "account %s",
                    target.device_id,
                )

        return results

    def check_current_weather(
        self,
        **_: Any,
    ) -> list[NotificationResult]:
        locations = self._load_locations()
        grouped_targets = self._group_by_location(
            self._load_targets(locations)
        )
        results: list[NotificationResult] = []

        for location_id, location in locations.items():
            targets = grouped_targets.get(location_id, [])

            try:
                provider = self._weather_provider(location)
                current_weather = (
                    provider.get_current_weather().to_dict()
                )
                previous_weather = (
                    self.repository.get_current_weather(
                        location_id
                    )
                )

                results.extend(
                    self._process_current_scan(
                        location_id=location_id,
                        weather=current_weather,
                        targets=targets,
                        previous_weather=previous_weather,
                    )
                )
            except Exception:
                logger.exception(
                    "Current-weather broadcast failed for "
                    "location %s",
                    location_id,
                )

        return results

    def check_forecast(
        self,
        **_: Any,
    ) -> list[NotificationResult]:
        locations = self._load_locations()
        grouped_targets = self._group_by_location(
            self._load_targets(locations)
        )
        results: list[NotificationResult] = []

        for location_id, location in locations.items():
            targets = grouped_targets.get(location_id, [])

            try:
                provider = self._weather_provider(location)
                forecast_models = provider.get_forecast(
                    hours=(
                        self.settings.weather_notifications
                        .forecast_horizon_hours
                    )
                )
                forecasts = [
                    forecast.to_dict()
                    for forecast in forecast_models
                ]

                scan_id = self.repository.set_latest_forecast(
                    location_id=location_id,
                    forecasts=forecasts,
                )

                current_weather = (
                    self.repository.get_current_weather(
                        location_id
                    )
                )
                currently_raining = bool(
                    current_weather
                    and current_weather.get("is_raining")
                    is True
                )
            except Exception:
                logger.exception(
                    "Forecast broadcast failed for location %s",
                    location_id,
                )
                continue

            results.extend(
                self._process_forecast_scan(
                    forecasts=forecasts,
                    targets=targets,
                    currently_raining=currently_raining,
                    scan_id=scan_id,
                )
            )

        return results

    @staticmethod
    def _result_document(
        result: NotificationResult,
    ) -> dict[str, Any]:
        return {
            "notification_id": result.notification_id,
            "created": result.created,
            "email_status": result.email_status.value,
            "gmail_message_id": result.gmail_message_id,
            "error": result.error,
        }

    def check_pending_weather_scans(
        self,
        **_: Any,
    ) -> list[NotificationResult]:
        locations = self._load_locations()
        grouped_targets = self._group_by_location(
            self._load_targets(locations)
        )
        all_results: list[NotificationResult] = []

        for scan in self.repository.get_pending_weather_scans():
            location_id = self._required_text(
                scan.get("location_id")
            )
            scan_id = self._required_text(
                scan.get("scan_id")
                or scan.get("document_id")
            )
            scan_type = self._required_text(scan.get("scan_type"))

            if (
                location_id is None
                or scan_id is None
                or scan_type not in {"current", "forecast"}
            ):
                logger.warning(
                    "Skipping malformed pending weather scan"
                )
                continue

            results: list[NotificationResult] = []

            try:
                location = locations.get(location_id)
                targets = grouped_targets.get(location_id, [])

                if location is None:
                    raise ValueError(
                        f"Location does not exist: {location_id}"
                    )

                if not targets:
                    raise ValueError(
                        "No enabled notification account is assigned "
                        f"to {location_id}"
                    )

                force_notify = scan.get("force_notify") is True

                if scan_type == "current":
                    results.extend(
                        self._process_current_scan(
                            location_id=location_id,
                            weather=scan,
                            targets=targets,
                            previous_weather=(
                                None
                                if force_notify
                                else self.repository
                                .get_current_weather(location_id)
                            ),
                            scan_id=scan_id,
                        )
                    )
                else:
                    forecasts = scan.get("items")

                    if not isinstance(forecasts, list) or not all(
                        isinstance(item, Mapping)
                        for item in forecasts
                    ):
                        raise ValueError(
                            "Forecast scan items are invalid"
                        )

                    current_weather = (
                        self.repository.get_current_weather(location_id)
                    )
                    currently_raining = bool(
                        current_weather
                        and current_weather.get("is_raining") is True
                    )

                    results.extend(
                        self._process_forecast_scan(
                            forecasts=forecasts,
                            targets=targets,
                            currently_raining=currently_raining,
                            scan_id=scan_id,
                            force_notify=force_notify,
                        )
                    )

                self.repository.finish_weather_scan(
                    location_id=location_id,
                    scan_type=scan_type,
                    scan_id=scan_id,
                    results=[
                        self._result_document(result)
                        for result in results
                    ],
                )
                all_results.extend(results)
            except Exception as error:
                logger.exception(
                    "Pending weather scan processing failed for %s/%s/%s",
                    location_id,
                    scan_type,
                    scan_id,
                )

                try:
                    self.repository.finish_weather_scan(
                        location_id=location_id,
                        scan_type=scan_type,
                        scan_id=scan_id,
                        results=[
                            self._result_document(result)
                            for result in results
                        ],
                        error=str(error),
                    )
                except Exception:
                    logger.exception(
                        "Could not mark pending weather scan failed"
                    )

        return all_results
