import argparse
import sys
import time

from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.firebase import FirestoreService
from backend.models import CurrentWeather, ForecastItem


DEFAULT_LOCATIONS = ("location_hcm", "location_hn")
LOCATION_ALIASES = {"location_hn": "location_hanoi"}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write fake canonical weather scans for the running backend."
        )
    )
    parser.add_argument(
        "--locations",
        nargs="+",
        default=list(DEFAULT_LOCATIONS),
        help=(
            "Location document IDs (default: location_hcm location_hn)."
        ),
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=15,
        help="Wait for backend notification status (default: 15).",
    )
    return parser.parse_args()


def fake_current_weather(now: datetime) -> CurrentWeather:
    return CurrentWeather(
        location="Fake scan",
        observed_at=now,
        temperature_celsius=27.5,
        feels_like_celsius=30.0,
        humidity_percent=92,
        pressure_hpa=1005,
        condition="Rain",
        description="fake heavy rain scan",
        cloud_cover_percent=100,
        wind_speed_mps=5.0,
        rain_last_1h_mm=8.0,
    )


def fake_forecast(now: datetime) -> ForecastItem:
    return ForecastItem(
        forecast_at=now + timedelta(minutes=1),
        forecast_within_minutes=1,
        temperature_celsius=28.0,
        humidity_percent=90,
        condition="Thunderstorm",
        description="fake storm forecast scan",
        rain_probability_percent=100,
        rain_amount_mm=12.0,
        cloud_cover_percent=100,
    )


def resolve_location_id(
    repository: FirestoreService,
    requested_id: str,
) -> str:
    requested_id = requested_id.strip().lower()

    if repository.get_location(requested_id) is not None:
        return requested_id

    canonical_id = LOCATION_ALIASES.get(requested_id)

    if (
        canonical_id is not None
        and repository.get_location(canonical_id) is not None
    ):
        print(f"Using {canonical_id} for alias {requested_id}.")
        return canonical_id

    raise RuntimeError(
        f"Firestore location does not exist: {requested_id}"
    )


def main() -> None:
    arguments = parse_arguments()
    repository = FirestoreService()
    now = datetime.now(timezone.utc)
    current_weather = {
        **fake_current_weather(now).to_dict(),
        "source": "fake_weather_script",
    }
    forecasts = [{
        **fake_forecast(now).to_dict(),
        "source": "fake_weather_script",
    }]
    pending: dict[tuple[str, str, str], str] = {}

    for requested_id in arguments.locations:
        location_id = resolve_location_id(
            repository,
            requested_id,
        )
        current_scan_id = repository.set_current_weather(
            location_id=location_id,
            weather=current_weather,
            is_raining=True,
            rain_started_at=now,
            notification_trigger=True,
        )
        forecast_scan_id = repository.set_latest_forecast(
            location_id=location_id,
            forecasts=forecasts,
            notification_trigger=True,
        )
        pending[(location_id, "current", current_scan_id)] = "pending"
        pending[(location_id, "forecast", forecast_scan_id)] = "pending"
        print(
            f"Created locations/{location_id}/current/{current_scan_id}"
        )
        print(
            f"Created locations/{location_id}/forecast/{forecast_scan_id}"
        )

    if arguments.wait_seconds <= 0:
        print("The running backend will process the pending scans.")
        return

    deadline = time.monotonic() + arguments.wait_seconds

    while time.monotonic() < deadline and any(
        status == "pending" for status in pending.values()
    ):
        time.sleep(1)

        for key, status in list(pending.items()):
            if status != "pending":
                continue

            location_id, scan_type, scan_id = key
            scan = repository.get_weather_scan(
                location_id=location_id,
                scan_type=scan_type,
                scan_id=scan_id,
            ) or {}
            pending[key] = str(
                scan.get("notification_status") or "pending"
            )

    unsuccessful = False

    for (location_id, scan_type, scan_id), status in pending.items():
        scan = repository.get_weather_scan(
            location_id=location_id,
            scan_type=scan_type,
            scan_id=scan_id,
        ) or {}
        print(f"{location_id}/{scan_type}/{scan_id}: {status}")

        for result in scan.get("notification_results") or []:
            print(
                "  notification="
                f"{result.get('notification_id')} "
                f"email={result.get('email_status')}"
            )

        if status != "processed":
            unsuccessful = True

    if unsuccessful:
        raise SystemExit(
            "Some scans were not processed. "
            "Make sure the updated backend is running."
        )


if __name__ == "__main__":
    main()
