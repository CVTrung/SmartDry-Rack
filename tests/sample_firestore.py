import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.firebase.firestore_service import (
    FirestoreService,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = (
    PROJECT_ROOT
    / "tests"
    / "sample_firestore_data.json"
)


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def load_sample_data() -> dict[str, Any]:
    with SAMPLE_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Firestore sample data must be an object"
        )

    return data


def push_sample_data() -> None:
    if os.getenv("ALLOW_FIRESTORE_SAMPLE_WRITE") != "yes":
        raise RuntimeError(
            "Sample write is disabled. Set "
            "ALLOW_FIRESTORE_SAMPLE_WRITE=yes to enable it."
        )

    data = load_sample_data()
    service = FirestoreService()

    account = data["account"]
    device_id = account["device_id"]

    if service.get_account(device_id) is not None:
        raise RuntimeError(
            f"Sample account already exists: {device_id}"
        )

    service.create_account(
        device_id=device_id,
        display_name=account["display_name"],
        enabled=account["enabled"],
    )

    for record in data["device_history"]:
        service.create_device_history(
            device_id=device_id,
            record_type=record["record_type"],
            recorded_at=parse_datetime(
                record["recorded_at"]
            ),
            data=record["data"],
        )

    for command in data["command_history"]:
        service.create_command_history(
            command_id=command["command_id"],
            device_id=device_id,
            action=command["action"],
            source=command["source"],
            reason=command["reason"],
            status=command["status"],
            requested_by=command["requested_by"],
            requested_at=parse_datetime(
                command["requested_at"]
            ),
            result=command["result"],
        )

    for forecast in data["forecast_history"]:
        service.create_forecast_history(
            device_id=device_id,
            forecast_at=parse_datetime(
                forecast["forecast_at"]
            ),
            expires_at=parse_datetime(
                forecast["expires_at"]
            ),
            source=forecast["source"],
            location=forecast["location"],
            weather=forecast["weather"],
        )

    print(
        "Firestore sample data created for "
        f"{device_id}"
    )


if __name__ == "__main__":
    push_sample_data()