from backend.config import get_settings
from backend.firebase import FirebaseAuthService


def prompt_with_default(
    label: str,
    default: str,
) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def main() -> None:
    settings = get_settings()
    device_id = prompt_with_default(
        "Device ID",
        settings.weather_notifications.device_id,
    ).lower()

    try:
        service = FirebaseAuthService()
        account = service.firestore.get_account(
            device_id
        )
    except Exception as error:
        raise SystemExit(
            f"Could not load account: {error}"
        ) from error

    print("Delete SmartDry account")
    print("-" * 24)
    print(f"Device ID: {device_id}")
    print(
        "Name:      "
        + (
            str(account.get("display_name", device_id))
            if account is not None
            else "Firestore account not found"
        )
    )
    print(
        "Gmail:     "
        + (
            str(account.get("gmail", "not configured"))
            if account is not None
            else "unknown"
        )
    )

    if account is None:
        print(
            "Warning: Firestore account data is missing; "
            "Auth and any remaining device data will still be checked."
        )
    print()
    print(
        "This permanently deletes the Firebase Auth user, "
        "account, device, history, and notifications."
    )

    confirmation = input(
        f"Type {device_id} to confirm: "
    ).strip().lower()

    if confirmation != device_id:
        print("Deletion cancelled.")
        return

    try:
        service.delete_device_account(device_id)
    except Exception as error:
        raise SystemExit(
            f"Account deletion failed: {error}"
        ) from error

    print(f"Account deleted successfully: {device_id}")


if __name__ == "__main__":
    main()
