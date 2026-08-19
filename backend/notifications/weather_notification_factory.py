from backend.config import (
    Settings,
    get_settings,
)
from backend.firebase import FirestoreService
from backend.notifications.gmail_service import (
    GmailNotificationService,
)
from backend.notifications.weather_notification_broadcaster import (
    WeatherNotificationBroadcaster,
)
from backend.notifications.weather_email_formatter import (
    WeatherEmailFormatter,
)
from backend.notifications.weather_notification_runner import (
    WeatherNotificationRunner,
)
from backend.notifications.weather_notification_service import (
    WeatherNotificationService,
)


def create_weather_notification_runner(
    settings: Settings | None = None,
) -> WeatherNotificationRunner:
    """
    Create the complete weather notification workflow.

    Passing settings is useful for tests. The application
    normally allows this function to call get_settings().
    """

    application_settings = (
        settings
        if settings is not None
        else get_settings()
    )

    repository = FirestoreService()

    gmail_service = GmailNotificationService(
        application_settings.gmail
    )

    email_formatter = WeatherEmailFormatter()

    notification_service = (
        WeatherNotificationService(
            repository=repository,
            gmail_service=gmail_service,
            email_formatter=email_formatter,
            gmail_settings=(
                application_settings.gmail
            ),
        )
    )

    broadcaster = WeatherNotificationBroadcaster(
        repository=repository,
        notification_service=(
            notification_service
        ),
        settings=application_settings,
    )

    return WeatherNotificationRunner(
        processor=broadcaster,
        lease_repository=repository,
        settings=(
            application_settings
            .weather_notifications
        ),
    )
