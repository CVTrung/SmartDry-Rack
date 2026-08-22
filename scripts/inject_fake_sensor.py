import argparse
import json
import sys

from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.firebase import RealtimeFirebaseService


def parse_arguments(
    arguments: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write one fake sensor snapshot to Firebase Realtime "
            "Database for the running backend to process."
        )
    )
    parser.add_argument(
        "--device-id",
        help=(
            "Target device ID. Defaults to the configured DEVICE_ID."
        ),
    )
    parser.add_argument(
        "--light-lux",
        type=float,
        default=650.0,
        help="Light level in lux (default: 650).",
    )
    parser.add_argument(
        "--humidity-percent",
        type=float,
        default=72.5,
        help="Relative humidity from 0 to 100 (default: 72.5).",
    )
    parser.add_argument(
        "--temperature-celsius",
        type=float,
        default=30.5,
        help="Temperature from -40 to 85 C (default: 30.5).",
    )
    parser.add_argument(
        "--rain-detected",
        action="store_true",
        help="Set the fake rain sensor to true.",
    )
    return parser.parse_args(arguments)


def inject_fake_sensor(
    arguments: argparse.Namespace,
    service: RealtimeFirebaseService,
    *,
    default_device_id: str,
) -> dict:
    device_id = (
        arguments.device_id or default_device_id
    )
    return service.set_sensor_data(
        device_id=device_id,
        light_lux=arguments.light_lux,
        humidity_percent=arguments.humidity_percent,
        temperature_celsius=(
            arguments.temperature_celsius
        ),
        rain_detected=arguments.rain_detected,
    )


def main() -> None:
    arguments = parse_arguments()
    settings = get_settings()
    payload = inject_fake_sensor(
        arguments,
        RealtimeFirebaseService(),
        default_device_id=(
            settings.weather_notifications.device_id
        ),
    )
    device_id = payload["device_id"]

    print(f"Updated Input_Sensor/{device_id}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print()
    print(
        "The running backend can stream this value immediately and "
        "will copy it to Firestore sensor_history during its next "
        "five-minute snapshot. Restarting the backend runs that "
        "snapshot immediately."
    )
    print(
        "Firestore target: "
        f"devices/{device_id}/sensor_history/{{five_minute_bucket}}"
    )


if __name__ == "__main__":
    main()
