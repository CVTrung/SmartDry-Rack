import os

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)


class ConfigurationError(RuntimeError):
    """Raised when backend configuration is invalid."""


def _required_text(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise ConfigurationError(
            f"{name} is missing from .env"
        )

    return value


def _optional_text(
    name: str,
    default: str = "",
) -> str:
    return os.getenv(name, default).strip()


def _integer(
    name: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw_value = os.getenv(name, "").strip()

    if not raw_value:
        if default is None:
            raise ConfigurationError(
                f"{name} is missing from .env"
            )

        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError as error:
            raise ConfigurationError(
                f"{name} must be an integer"
            ) from error

    if minimum is not None and value < minimum:
        raise ConfigurationError(
            f"{name} must be at least {minimum}"
        )

    if maximum is not None and value > maximum:
        raise ConfigurationError(
            f"{name} must not exceed {maximum}"
        )

    return value


def _float(
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw_value = _required_text(name)

    try:
        value = float(raw_value)
    except ValueError as error:
        raise ConfigurationError(
            f"{name} must be a number"
        ) from error

    if minimum is not None and value < minimum:
        raise ConfigurationError(
            f"{name} must be at least {minimum}"
        )

    if maximum is not None and value > maximum:
        raise ConfigurationError(
            f"{name} must not exceed {maximum}"
        )

    return value


def _boolean(
    name: str,
    *,
    default: bool | None = None,
) -> bool:
    raw_value = os.getenv(name, "").strip().lower()

    if not raw_value:
        if default is None:
            raise ConfigurationError(
                f"{name} is missing from .env"
            )

        return default

    if raw_value in {"true", "1", "yes", "on"}:
        return True

    if raw_value in {"false", "0", "no", "off"}:
        return False

    raise ConfigurationError(
        f"{name} must be true or false"
    )


def _project_path(name: str) -> Path:
    raw_path = _required_text(name)
    path = Path(raw_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def _validate_identifier(
    value: str,
    name: str,
) -> str:
    invalid_characters = ".#$[]/"

    if any(
        character in value
        for character in invalid_characters
    ):
        raise ConfigurationError(
            f"{name} must not contain "
            ". # $ [ ] or /"
        )

    return value


def _validate_email(
    value: str,
    name: str,
) -> str:
    if (
        value.count("@") != 1
        or any(character.isspace() for character in value)
    ):
        raise ConfigurationError(
            f"{name} must contain one valid email address"
        )

    local_part, domain = value.rsplit("@", 1)

    if (
        not local_part
        or not domain
        or "." not in domain
    ):
        raise ConfigurationError(
            f"{name} must contain one valid email address"
        )

    return value


@dataclass(frozen=True)
class FirebaseSettings:
    database_url: str
    service_account_key_path: Path


@dataclass(frozen=True)
class OpenWeatherSettings:
    api_key: str
    latitude: float
    longitude: float
    timeout_seconds: int


@dataclass(frozen=True)
class GmailSettings:
    enabled: bool
    sender_email: str | None
    recipient_email: str | None
    credentials_path: Path | None
    token_path: Path | None
    max_retry_attempts: int


@dataclass(frozen=True)
class WeatherNotificationSettings:
    device_id: str
    location_id: str

    current_check_interval_minutes: int
    forecast_check_interval_minutes: int
    forecast_horizon_hours: int

    rain_threshold_percent: int
    warning_window_minutes: int
    cooldown_minutes: int


@dataclass(frozen=True)
class Settings:
    firebase: FirebaseSettings
    openweather: OpenWeatherSettings
    gmail: GmailSettings
    weather_notifications: WeatherNotificationSettings

    @classmethod
    def from_env(cls) -> "Settings":
        gmail_enabled = _boolean(
            "EMAIL_NOTIFICATIONS_ENABLED",
            default=False,
        )

        gmail_sender_email: str | None = None
        gmail_recipient_email: str | None = None
        gmail_credentials_path: Path | None = None
        gmail_token_path: Path | None = None

        if gmail_enabled:
            gmail_sender_email = _validate_email(
                _required_text(
                    "GMAIL_SENDER_EMAIL"
                ),
                "GMAIL_SENDER_EMAIL",
            )

            raw_recipient_email = _optional_text(
                "GMAIL_RECIPIENT_EMAIL"
            )

            if raw_recipient_email:
                gmail_recipient_email = _validate_email(
                    raw_recipient_email,
                    "GMAIL_RECIPIENT_EMAIL",
                )

            gmail_credentials_path = _project_path(
                "GMAIL_CREDENTIALS_PATH"
            )

            gmail_token_path = _project_path(
                "GMAIL_TOKEN_PATH"
            )

        return cls(
            firebase=FirebaseSettings(
                database_url=_required_text(
                    "FIREBASE_DATABASE_URL"
                ).rstrip("/"),
                service_account_key_path=_project_path(
                    "FIREBASE_SERVICE_ACCOUNT_KEY_PATH"
                ),
            ),
            openweather=OpenWeatherSettings(
                api_key=_required_text(
                    "OPENWEATHER_API_KEY"
                ),
                latitude=_float(
                    "OPENWEATHER_LAT",
                    minimum=-90,
                    maximum=90,
                ),
                longitude=_float(
                    "OPENWEATHER_LON",
                    minimum=-180,
                    maximum=180,
                ),
                timeout_seconds=_integer(
                    "OPENWEATHER_TIMEOUT_SECONDS",
                    default=10,
                    minimum=1,
                    maximum=60,
                ),
            ),
            gmail=GmailSettings(
                enabled=gmail_enabled,
                sender_email=gmail_sender_email,
                recipient_email=gmail_recipient_email,
                credentials_path=gmail_credentials_path,
                token_path=gmail_token_path,
                max_retry_attempts=_integer(
                    "GMAIL_MAX_RETRY_ATTEMPTS",
                    default=3,
                    minimum=1,
                    maximum=10,
                ),
            ),
            weather_notifications=(
                WeatherNotificationSettings(
                    device_id=_validate_identifier(
                        _required_text("DEVICE_ID"),
                        "DEVICE_ID",
                    ),
                    location_id=_validate_identifier(
                        _required_text("LOCATION_ID"),
                        "LOCATION_ID",
                    ),
                    current_check_interval_minutes=(
                        _integer(
                            (
                                "CURRENT_WEATHER_CHECK_"
                                "INTERVAL_MINUTES"
                            ),
                            default=5,
                            minimum=1,
                        )
                    ),
                    forecast_check_interval_minutes=(
                        _integer(
                            "FORECAST_CHECK_INTERVAL_MINUTES",
                            default=30,
                            minimum=1,
                        )
                    ),
                    forecast_horizon_hours=_integer(
                        "FORECAST_HORIZON_HOURS",
                        default=24,
                        minimum=1,
                        maximum=120,
                    ),
                    rain_threshold_percent=_integer(
                        "RAIN_ALERT_THRESHOLD_PERCENT",
                        default=70,
                        minimum=0,
                        maximum=100,
                    ),
                    warning_window_minutes=_integer(
                        "RAIN_WARNING_WINDOW_MINUTES",
                        default=180,
                        minimum=0,
                    ),
                    cooldown_minutes=_integer(
                        "RAIN_ALERT_COOLDOWN_MINUTES",
                        default=60,
                        minimum=0,
                    ),
                )
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return validated backend settings."""

    return Settings.from_env()
