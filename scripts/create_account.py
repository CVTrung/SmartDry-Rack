from dataclasses import dataclass
from getpass import getpass

from backend.config import get_settings
from backend.firebase import FirebaseAuthService


@dataclass(frozen=True)
class LocationPreset:
    name: str
    latitude: float
    longitude: float
    timezone: str


LOCATION_PRESETS = {
    "location_hcm": LocationPreset(
        name="Ho Chi Minh City",
        latitude=10.8231,
        longitude=106.6297,
        timezone="Asia/Ho_Chi_Minh",
    ),
    "location_hanoi": LocationPreset(
        name="Hanoi",
        latitude=21.0278,
        longitude=105.8342,
        timezone="Asia/Ho_Chi_Minh",
    ),
}


def get_location_preset(location_id: str) -> LocationPreset:
    normalized_id = location_id.strip().lower()

    preset = LOCATION_PRESETS.get(normalized_id)

    if preset is None:
        choices = ", ".join(sorted(LOCATION_PRESETS))
        raise SystemExit(
            "Error: Unknown Location ID. "
            f"Choose one of: {choices}"
        )

    return preset


def prompt_with_default(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def main() -> None:
    settings = get_settings()

    print("SmartDry account setup")
    print("-" * 25)
    print("Available locations: " + ", ".join(LOCATION_PRESETS))

    device_id = prompt_with_default(
        "Device ID",
        settings.weather_notifications.device_id,
    ).lower()
    display_name = prompt_with_default(
        "Device display name",
        device_id,
    )
    location_id = prompt_with_default(
        "Location ID",
        settings.weather_notifications.location_id,
    ).lower()
    location = get_location_preset(location_id)
    default_gmail = settings.gmail.recipient_email or ""
    gmail = prompt_with_default(
        "Notification Gmail",
        default_gmail,
    ).lower()

    if not gmail:
        raise SystemExit(
            "Error: Notification Gmail is required."
        )

    gmail_authorized = (
        input(
            "Authorize weather emails to this Gmail? [y/N]: "
        )
        .strip()
        .lower()
        in {"y", "yes"}
    )

    password = getpass("Password (at least 6 characters): ")
    confirmation_password = getpass("Confirm password: ")

    if password != confirmation_password:
        raise SystemExit("Error: Passwords do not match.")

    print()
    print(f"Device:   {display_name} ({device_id})")
    print(f"Location: {location.name} ({location_id})")
    print(f"Gmail:    {gmail}")
    print(
        "Email notifications: "
        + ("authorized" if gmail_authorized else "not authorized")
    )
    print(
        "Coordinates: "
        f"{location.latitude}, {location.longitude}"
    )
    print(f"Timezone: {location.timezone}")

    if input("\nContinue? [y/N]: ").strip().lower() not in {"y", "yes"}:
        print("Setup cancelled.")
        return

    try:
        auth_service = FirebaseAuthService()
        result = auth_service.create_device_account(
            device_id=device_id,
            password=password,
            display_name=display_name,
            location_id=location_id,
            gmail=gmail,
            gmail_authorized=gmail_authorized,
            enabled=True,
        )
        auth_service.firestore.set_location(
            location_id=location_id,
            name=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
            timezone=location.timezone,
        )
    except Exception as error:
        raise SystemExit(f"Setup failed: {error}") from error

    print("\nSetup completed successfully.")
    print(f"Auth UID: {result['uid']}")
    print(
        "The notification scheduler will discover this enabled "
        "account automatically on its next check."
    )


if __name__ == "__main__":
    main()
