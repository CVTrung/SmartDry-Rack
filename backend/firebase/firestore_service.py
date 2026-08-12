from datetime import datetime
from typing import Any, Mapping

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from backend.firebase import get_firebase_app


class FirestoreService:
    ACCOUNTS = "accounts"
    DEVICES = "devices"

    DEVICE_HISTORY = "device_history"
    COMMAND_HISTORY = "command_history"
    FORECAST_HISTORY = "forecast_history"

    DEVICE_RECORD_TYPES = {
        "sensor",
        "state_change",
        "config_change",
        "device_online",
        "device_offline",
        "error",
    }

    COMMAND_ACTIONS = {
        "extend",
        "retract",
        "stop",
    }

    COMMAND_SOURCES = {
        "website",
        "physical_button",
        "automatic",
    }

    COMMAND_STATUSES = {
        "pending",
        "received",
        "executing",
        "completed",
        "failed",
        "rejected",
    }

    TERMINAL_COMMAND_STATUSES = {
        "completed",
        "failed",
        "rejected",
    }

    def __init__(self) -> None:
        self.app = get_firebase_app()
        self.database = firestore.client(app=self.app)

    # =========================================================
    # Shared helpers
    # =========================================================

    @staticmethod
    def _validate_device_id(device_id: str) -> str:
        device_id = device_id.strip().lower()

        if not device_id:
            raise ValueError(
                "device_id must not be empty"
            )

        invalid_characters = ".#$[]/"

        if any(
            character in device_id
            for character in invalid_characters
        ):
            raise ValueError(
                "device_id must not contain . # $ [ ] or /"
            )

        return device_id

    @staticmethod
    def _validate_required_text(
        value: str,
        field_name: str,
        maximum_length: int = 200,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if len(value) > maximum_length:
            raise ValueError(
                f"{field_name} must not exceed "
                f"{maximum_length} characters"
            )

        return value

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if not 1 <= limit <= 100:
            raise ValueError(
                "limit must be between 1 and 100"
            )

        return limit

    @staticmethod
    def _validate_datetime(
        value: datetime | None,
        field_name: str,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError(
                f"{field_name} must include timezone information"
            )

        return value

    @staticmethod
    def _snapshot_to_dict(
        snapshot: Any,
    ) -> dict[str, Any] | None:
        if not snapshot.exists:
            return None

        data = snapshot.to_dict()

        if data is None:
            return None

        return {
            "document_id": snapshot.id,
            **data,
        }

    @classmethod
    def _snapshots_to_list(
        cls,
        snapshots: Any,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for snapshot in snapshots:
            data = cls._snapshot_to_dict(snapshot)

            if data is not None:
                results.append(data)

        return results

    def _device_reference(
        self,
        device_id: str,
    ):
        device_id = self._validate_device_id(device_id)

        return (
            self.database
            .collection(self.DEVICES)
            .document(device_id)
        )

    # =========================================================
    # Accounts
    #
    # Firestore path:
    # accounts/{device_id}
    #
    # Passwords are managed by Firebase Authentication.
    # They must never be stored in this collection.
    # =========================================================

    def create_account(
        self,
        device_id: str,
        display_name: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)

        display_name = self._validate_required_text(
            display_name,
            "display_name",
            maximum_length=100,
        )

        if not isinstance(enabled, bool):
            raise TypeError(
                "enabled must be a boolean"
            )

        account_reference = (
            self.database
            .collection(self.ACCOUNTS)
            .document(device_id)
        )

        device_reference = self._device_reference(device_id)

        if account_reference.get().exists:
            raise ValueError(
                f"Account already exists: {device_id}"
            )

        if device_reference.get().exists:
            raise ValueError(
                f"Device already exists: {device_id}"
            )

        account_payload: dict[str, Any] = {
            "device_id": device_id,
            "display_name": display_name,
            "enabled": enabled,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "last_login_at": None,
        }

        device_payload: dict[str, Any] = {
            "device_id": device_id,
            "display_name": display_name,
            "enabled": enabled,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

        batch = self.database.batch()

        batch.create(
            account_reference,
            account_payload,
        )

        batch.create(
            device_reference,
            device_payload,
        )

        batch.commit()

        account = self.get_account(device_id)

        if account is None:
            raise RuntimeError(
                "Account was created but could not be read"
            )

        return account

    def get_account(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)

        snapshot = (
            self.database
            .collection(self.ACCOUNTS)
            .document(device_id)
            .get()
        )

        return self._snapshot_to_dict(snapshot)

    def update_account(
        self,
        device_id: str,
        *,
        display_name: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)

        updates: dict[str, Any] = {
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

        if display_name is not None:
            updates["display_name"] = (
                self._validate_required_text(
                    display_name,
                    "display_name",
                    maximum_length=100,
                )
            )

        if enabled is not None:
            if not isinstance(enabled, bool):
                raise TypeError(
                    "enabled must be a boolean"
                )

            updates["enabled"] = enabled

        if len(updates) == 1:
            raise ValueError(
                "At least one account field must be provided"
            )

        account_reference = (
            self.database
            .collection(self.ACCOUNTS)
            .document(device_id)
        )

        account_reference.update(updates)

        account = self.get_account(device_id)

        if account is None:
            raise RuntimeError(
                "Account was updated but could not be read"
            )

        return account

    def mark_account_login(
        self,
        device_id: str,
    ) -> None:
        device_id = self._validate_device_id(device_id)

        (
            self.database
            .collection(self.ACCOUNTS)
            .document(device_id)
            .update({
                "last_login_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
        )

    def account_is_enabled(
        self,
        device_id: str,
    ) -> bool:
        account = self.get_account(device_id)

        return bool(
            account
            and account.get("enabled") is True
        )

    # =========================================================
    # Device history
    #
    # Firestore path:
    # devices/{device_id}/device_history/{generated_id}
    # =========================================================

    def create_device_history(
        self,
        device_id: str,
        record_type: str,
        data: Mapping[str, Any],
        *,
        recorded_at: datetime | None = None,
    ) -> str:
        device_id = self._validate_device_id(device_id)
        record_type = record_type.strip().lower()

        if record_type not in self.DEVICE_RECORD_TYPES:
            raise ValueError(
                "Unsupported device history record_type"
            )

        if not isinstance(data, Mapping):
            raise TypeError(
                "data must be a mapping"
            )

        recorded_at = self._validate_datetime(
            recorded_at,
            "recorded_at",
        )

        history_reference = (
            self._device_reference(device_id)
            .collection(self.DEVICE_HISTORY)
            .document()
        )

        payload: dict[str, Any] = {
            "device_id": device_id,
            "record_type": record_type,
            "recorded_at": (
                recorded_at
                if recorded_at is not None
                else firestore.SERVER_TIMESTAMP
            ),
            "received_at": firestore.SERVER_TIMESTAMP,
            record_type: dict(data),
        }

        history_reference.set(payload)

        return history_reference.id

    def save_sensor_record(
        self,
        device_id: str,
        *,
        light_lux: float,
        humidity_percent: float,
        temperature_celsius: float,
        rain_detected: bool,
        recorded_at: datetime | None = None,
    ) -> str:
        if light_lux < 0:
            raise ValueError(
                "light_lux must not be negative"
            )

        if not 0 <= humidity_percent <= 100:
            raise ValueError(
                "humidity_percent must be between 0 and 100"
            )

        if not -40 <= temperature_celsius <= 85:
            raise ValueError(
                "temperature_celsius must be between -40 and 85"
            )

        if not isinstance(rain_detected, bool):
            raise TypeError(
                "rain_detected must be a boolean"
            )

        return self.create_device_history(
            device_id=device_id,
            record_type="sensor",
            recorded_at=recorded_at,
            data={
                "light_lux": light_lux,
                "humidity_percent": humidity_percent,
                "temperature_celsius": temperature_celsius,
                "rain_detected": rain_detected,
            },
        )

    def save_state_change(
        self,
        device_id: str,
        *,
        previous_state: str,
        new_state: str,
        reason: str,
        command_id: str | None = None,
        result: str = "success",
        recorded_at: datetime | None = None,
    ) -> str:
        previous_state = self._validate_required_text(
            previous_state,
            "previous_state",
            maximum_length=30,
        )

        new_state = self._validate_required_text(
            new_state,
            "new_state",
            maximum_length=30,
        )

        reason = self._validate_required_text(
            reason,
            "reason",
        )

        data: dict[str, Any] = {
            "previous_state": previous_state,
            "new_state": new_state,
            "reason": reason,
            "result": result,
        }

        if command_id is not None:
            data["command_id"] = (
                self._validate_required_text(
                    command_id,
                    "command_id",
                    maximum_length=100,
                )
            )

        return self.create_device_history(
            device_id=device_id,
            record_type="state_change",
            recorded_at=recorded_at,
            data=data,
        )

    def save_config_change(
        self,
        device_id: str,
        *,
        previous_config: Mapping[str, Any],
        current_config: Mapping[str, Any],
        changed_by: str,
        recorded_at: datetime | None = None,
    ) -> str:
        changed_by = self._validate_required_text(
            changed_by,
            "changed_by",
            maximum_length=128,
        )

        return self.create_device_history(
            device_id=device_id,
            record_type="config_change",
            recorded_at=recorded_at,
            data={
                "previous": dict(previous_config),
                "current": dict(current_config),
                "changed_by": changed_by,
            },
        )

    def get_device_history(
        self,
        device_id: str,
        *,
        record_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        device_id = self._validate_device_id(device_id)
        limit = self._validate_limit(limit)

        query = (
            self._device_reference(device_id)
            .collection(self.DEVICE_HISTORY)
        )

        if record_type is not None:
            record_type = record_type.strip().lower()

            if record_type not in self.DEVICE_RECORD_TYPES:
                raise ValueError(
                    "Unsupported device history record_type"
                )

            query = query.where(
                filter=FieldFilter(
                    "record_type",
                    "==",
                    record_type,
                )
            )

        snapshots = (
            query
            .order_by(
                "recorded_at",
                direction=firestore.Query.DESCENDING,
            )
            .limit(limit)
            .stream()
        )

        return self._snapshots_to_list(snapshots)

    # =========================================================
    # Command history
    #
    # Firestore path:
    # devices/{device_id}/command_history/{command_id}
    # =========================================================

    def create_command_history(
        self,
        command_id: str,
        device_id: str,
        action: str,
        source: str,
        reason: str,
        *,
        requested_by: str | None = None,
        requested_at: datetime | None = None,
        status: str = "pending",
        result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        command_id = self._validate_required_text(
            command_id,
            "command_id",
            maximum_length=100,
        )

        device_id = self._validate_device_id(device_id)
        action = action.strip().lower()
        source = source.strip().lower()
        status = status.strip().lower()

        reason = self._validate_required_text(
            reason,
            "reason",
        )

        if action not in self.COMMAND_ACTIONS:
            raise ValueError(
                "action must be extend, retract, or stop"
            )

        if source not in self.COMMAND_SOURCES:
            raise ValueError(
                "source must be website, physical_button, "
                "or automatic"
            )

        if status not in self.COMMAND_STATUSES:
            raise ValueError(
                "Unsupported command status"
            )

        requested_at = self._validate_datetime(
            requested_at,
            "requested_at",
        )

        command_reference = (
            self._device_reference(device_id)
            .collection(self.COMMAND_HISTORY)
            .document(command_id)
        )

        payload: dict[str, Any] = {
            "command_id": command_id,
            "device_id": device_id,
            "action": action,
            "source": source,
            "reason": reason,
            "status": status,
            "requested_at": (
                requested_at
                if requested_at is not None
                else firestore.SERVER_TIMESTAMP
            ),
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

        if requested_by is not None:
            payload["requested_by"] = {
                "auth_uid": self._validate_required_text(
                    requested_by,
                    "requested_by",
                    maximum_length=128,
                )
            }
        else:
            payload["requested_by"] = None

        if result is not None:
            payload["result"] = dict(result)

        if status in self.TERMINAL_COMMAND_STATUSES:
            payload["completed_at"] = (
                firestore.SERVER_TIMESTAMP
            )

        # Prevent accidental replacement of an existing command.
        command_reference.create(payload)

        command = self.get_command_history(
            command_id,
            device_id,
        )

        if command is None:
            raise RuntimeError(
                "Command was created but could not be read"
            )

        return command

    def update_command_status(
        self,
        command_id: str,
        device_id: str,
        status: str,
        *,
        previous_state: str | None = None,
        final_state: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        command_id = self._validate_required_text(
            command_id,
            "command_id",
            maximum_length=100,
        )

        status = status.strip().lower()

        if status not in self.COMMAND_STATUSES:
            raise ValueError(
                "Unsupported command status"
            )

        updates: dict[str, Any] = {
            "status": status,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

        if status == "received":
            updates["received_at"] = (
                firestore.SERVER_TIMESTAMP
            )

        if status == "executing":
            updates["started_at"] = (
                firestore.SERVER_TIMESTAMP
            )

        if status in self.TERMINAL_COMMAND_STATUSES:
            updates["completed_at"] = (
                firestore.SERVER_TIMESTAMP
            )

        if (
            previous_state is not None
            or final_state is not None
            or error_code is not None
        ):
            updates["result"] = {
                "previous_state": previous_state,
                "final_state": final_state,
                "error_code": error_code,
            }

        command_reference = (
            self._device_reference(device_id)
            .collection(self.COMMAND_HISTORY)
            .document(command_id)
        )

        command_reference.update(updates)

        command = self.get_command_history(
            command_id,
            device_id,
        )

        if command is None:
            raise RuntimeError(
                "Command was updated but could not be read"
            )

        return command

    def get_command_history(
        self,
        command_id: str,
        device_id: str,
    ) -> dict[str, Any] | None:
        command_id = self._validate_required_text(
            command_id,
            "command_id",
            maximum_length=100,
        )

        snapshot = (
            self._device_reference(device_id)
            .collection(self.COMMAND_HISTORY)
            .document(command_id)
            .get()
        )

        return self._snapshot_to_dict(snapshot)

    def get_device_commands(
        self,
        device_id: str,
        *,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        device_id = self._validate_device_id(device_id)
        limit = self._validate_limit(limit)

        query = (
            self._device_reference(device_id)
            .collection(self.COMMAND_HISTORY)
        )

        if source is not None:
            source = source.strip().lower()

            if source not in self.COMMAND_SOURCES:
                raise ValueError(
                    "Unsupported command source"
                )

            query = query.where(
                filter=FieldFilter(
                    "source",
                    "==",
                    source,
                )
            )

        snapshots = (
            query
            .order_by(
                "requested_at",
                direction=firestore.Query.DESCENDING,
            )
            .limit(limit)
            .stream()
        )

        return self._snapshots_to_list(snapshots)

    # =========================================================
    # Forecast history
    #
    # Firestore path:
    # devices/{device_id}/forecast_history/{generated_id}
    # =========================================================

    def create_forecast_history(
        self,
        device_id: str,
        *,
        forecast_at: datetime,
        weather: Mapping[str, Any],
        location: Mapping[str, Any] | None = None,
        expires_at: datetime | None = None,
        source: str = "openweather",
    ) -> str:
        device_id = self._validate_device_id(device_id)

        forecast_at = self._validate_datetime(
            forecast_at,
            "forecast_at",
        )

        expires_at = self._validate_datetime(
            expires_at,
            "expires_at",
        )

        if forecast_at is None:
            raise ValueError(
                "forecast_at is required"
            )

        if not isinstance(weather, Mapping):
            raise TypeError(
                "weather must be a mapping"
            )

        source = self._validate_required_text(
            source,
            "source",
            maximum_length=50,
        )

        forecast_reference = (
            self._device_reference(device_id)
            .collection(self.FORECAST_HISTORY)
            .document()
        )

        payload: dict[str, Any] = {
            "device_id": device_id,
            "forecast_at": forecast_at,
            "retrieved_at": firestore.SERVER_TIMESTAMP,
            "weather": dict(weather),
            "source": source,
        }

        if location is not None:
            payload["location"] = dict(location)

        if expires_at is not None:
            payload["expires_at"] = expires_at

        forecast_reference.set(payload)

        return forecast_reference.id

    def get_device_forecasts(
        self,
        device_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        device_id = self._validate_device_id(device_id)
        limit = self._validate_limit(limit)

        snapshots = (
            self._device_reference(device_id)
            .collection(self.FORECAST_HISTORY)
            .order_by(
                "forecast_at",
                direction=firestore.Query.DESCENDING,
            )
            .limit(limit)
            .stream()
        )

        return self._snapshots_to_list(snapshots)