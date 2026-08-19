from backend.config import get_settings
from backend.firebase import FirestoreService


def prompt_with_default(
    label: str,
    default: str,
) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def main() -> None:
    settings = get_settings()
    default_gmail = settings.gmail.recipient_email or ""

    print("Authorize account Gmail notifications")
    print("-" * 38)

    device_id = prompt_with_default(
        "Device ID",
        settings.weather_notifications.device_id,
    ).lower()
    gmail = prompt_with_default(
        "Notification Gmail",
        default_gmail,
    ).lower()

    if not gmail:
        raise SystemExit(
            "Error: Notification Gmail is required."
        )

    print()
    print(f"Device: {device_id}")
    print(f"Gmail:  {gmail}")

    confirmation = input(
        "Authorize weather notification emails? [y/N]: "
    ).strip().lower()

    if confirmation not in {"y", "yes"}:
        print("Authorization cancelled.")
        return

    try:
        account = FirestoreService().update_account(
            device_id,
            gmail=gmail,
            gmail_authorized=True,
        )
    except Exception as error:
        raise SystemExit(
            f"Gmail authorization failed: {error}"
        ) from error

    print("Gmail authorization saved successfully.")
    print(f"Account: {account['device_id']}")


if __name__ == "__main__":
    main()
