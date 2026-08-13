from getpass import getpass

from backend.firebase import FirebaseAuthService


def main() -> None:
    print("SmartDry test-account generator")
    print("-" * 35)

    device_id = input(
        "Device ID: "
    ).strip().lower()

    display_name = input(
        "Display name: "
    ).strip()

    if not display_name:
        display_name = device_id

    password = input(
        "Password (at least 6 characters): "
    )

    password_confirmation = input(
        "Confirm password: "
    )

    if password != password_confirmation:
        raise SystemExit(
            "Error: Passwords do not match."
        )

    print()
    print("The following test account will be created:")
    print(f"  Device ID:   {device_id}")
    print(f"  Login email: {device_id}@smartdry.local")
    print(f"  Display name: {display_name}")

    confirmation = input(
        "Continue? [y/N]: "
    ).strip().lower()

    if confirmation not in {"y", "yes"}:
        print("Account creation cancelled.")
        return

    try:
        service = FirebaseAuthService()

        result = service.create_device_account(
            device_id=device_id,
            password=password,
            display_name=display_name,
            enabled=True,
        )
    except Exception as error:
        print()
        print(f"Failed to create account: {error}")
        raise SystemExit(1) from error

    print()
    print("Test account created successfully.")
    print(f"  UID:         {result['uid']}")
    print(f"  Login email: {result['login_email']}")
    print(
        "  Firestore:   "
        f"accounts/{result['account']['device_id']}"
    )


if __name__ == "__main__":
    main()