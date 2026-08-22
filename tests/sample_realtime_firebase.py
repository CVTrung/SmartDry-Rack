import json
import os
from pathlib import Path
from typing import Any

from firebase_admin import db

from backend.firebase import RealtimeFirebaseService


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = PROJECT_ROOT / "tests" / "sample_realtime_firebase_data.json"


def load_sample_data() -> dict[str, Any]:
    with SAMPLE_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "sample_realtime_firebase_data.json must contain a JSON object"
        )

    return data


def push_sample_data() -> None:
    confirmation = os.getenv(
        "ALLOW_FIREBASE_SAMPLE_WRITE",
        "",
    )

    if confirmation != "1":
        raise RuntimeError(
            "Sample write was not confirmed. Set "
            "ALLOW_FIREBASE_SAMPLE_WRITE=1 first."
        )

    service = RealtimeFirebaseService.from_env()
    sample = load_sample_data()

    normal_nodes = [
        "Device_Accounts",
        "Input_Sensor",
        "Device_State",
    ]

    for node_name in normal_nodes:
        records = sample.get(node_name, {})

        for device_id, payload in records.items():
            path = f"{node_name}/{device_id}"

            db.reference(
                path,
                app=service.app,
            ).set(payload)

            print(f"Wrote: {path}")

    print("Sample Firebase data pushed successfully.")


if __name__ == "__main__":
    push_sample_data()
