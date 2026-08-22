from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.api_core.exceptions import AlreadyExists

from backend.config import SENSOR_HISTORY_INTERVAL_MINUTES
from backend.firebase import get_firebase_app
from backend.models import (
    AlertType,
    EmailStatus,
    WeatherAlert,
)

class FirestoreService:
    ACCOUNTS = "accounts"
    DEVICES = "devices"
    LOCATIONS = "locations"

    DEVICE_HISTORY = "device_history"
    SENSOR_HISTORY = "sensor_history"
    COMMAND_HISTORY = "command_history"
    FORECAST_HISTORY = "forecast_history"
    NOTIFICATIONS = "notifications"
    SYSTEM_LEASES = "system_leases"
    WEATHER_BROADCAST_LEASE = "weather_broadcast"

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
    def _validate_gmail(gmail: str) -> str:
        gmail = gmail.strip().lower()

        if (
            gmail.count("@") != 1
            or any(character.isspace() for character in gmail)
        ):
            raise ValueError(
                "gmail must be a valid Gmail address"
            )

        local_part, domain = gmail.rsplit("@", 1)

        if (
            not local_part
            or domain not in {
                "gmail.com",
                "googlemail.com",
            }
        ):
            raise ValueError(
                "gmail must use gmail.com or googlemail.com"
            )

        return gmail

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
    def _validate_sensor_values(
        *,
        light_lux: Any,
        humidity_percent: Any,
        temperature_celsius: Any,
        rain_detected: Any,
        sensor_timestamp: Any | None = None,
        require_sensor_timestamp: bool = False,
    ) -> dict[str, Any]:
        numeric_values = {
            "light_lux": light_lux,
            "humidity_percent": humidity_percent,
            "temperature_celsius": temperature_celsius,
        }

        if require_sensor_timestamp and sensor_timestamp is None:
            raise TypeError("sensor_timestamp must be numeric")

        if sensor_timestamp is not None:
            numeric_values["sensor_timestamp"] = sensor_timestamp

        for field_name, value in numeric_values.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be numeric")

        if light_lux < 0:
            raise ValueError("light_lux must not be negative")

        if not 0 <= humidity_percent <= 100:
            raise ValueError(
                "humidity_percent must be between 0 and 100"
            )

        if not -40 <= temperature_celsius <= 85:
            raise ValueError(
                "temperature_celsius must be between -40 and 85"
            )

        if sensor_timestamp is not None and sensor_timestamp < 0:
            raise ValueError("sensor_timestamp must not be negative")

        if not isinstance(rain_detected, bool):
            raise TypeError("rain_detected must be a boolean")

        values: dict[str, Any] = {
            "light_lux": light_lux,
            "humidity_percent": humidity_percent,
            "temperature_celsius": temperature_celsius,
            "rain_detected": rain_detected,
        }

        if sensor_timestamp is not None:
            values["sensor_timestamp"] = sensor_timestamp

        return values

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

    def _notification_reference(
        self,
        device_id: str,
        notification_id: str,
    ):
        device_id = self._validate_device_id(
            device_id
        )

        notification_id = (
            self._validate_required_text(
                notification_id,
                "notification_id",
                maximum_length=128,
            )
        )

        if "/" in notification_id:
            raise ValueError(
                "notification_id must not contain /"
            )

        return (
            self._device_reference(device_id)
            .collection(self.NOTIFICATIONS)
            .document(notification_id)
        )

    @staticmethod
    def _validate_location_id(location_id: str) -> str:
        location_id = location_id.strip().lower()

        if not location_id:
            raise ValueError(
                "location_id must not be empty"
            )

        if "/" in location_id:
            raise ValueError(
                "location_id must not contain /"
            )

        return location_id


    def _location_reference(
        self,
        location_id: str,
    ):
        location_id = self._validate_location_id(
            location_id
        )

        return (
            self.database
            .collection(self.LOCATIONS)
            .document(location_id)
        )

    def _weather_broadcast_lease_reference(self):
        return (
            self.database
            .collection(self.SYSTEM_LEASES)
            .document(self.WEATHER_BROADCAST_LEASE)
        )

    @staticmethod
    def _validate_lease_seconds(
        lease_seconds: int,
    ) -> int:
        if (
            not isinstance(lease_seconds, int)
            or isinstance(lease_seconds, bool)
            or not 30 <= lease_seconds <= 3600
        ):
            raise ValueError(
                "lease_seconds must be between 30 and 3600"
            )

        return lease_seconds

    def try_acquire_weather_broadcast_lease(
        self,
        *,
        owner_id: str,
        lease_seconds: int,
    ) -> bool:
        owner_id = self._validate_required_text(
            owner_id,
            "owner_id",
            maximum_length=128,
        )
        lease_seconds = self._validate_lease_seconds(
            lease_seconds
        )
        lease_reference = (
            self._weather_broadcast_lease_reference()
        )
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(
            seconds=lease_seconds
        )
        transaction = self.database.transaction()

        @firestore.transactional
        def acquire(transaction):
            snapshot = lease_reference.get(
                transaction=transaction
            )
            lease = (
                snapshot.to_dict()
                if snapshot.exists
                else None
            ) or {}
            current_owner = lease.get("owner_id")
            current_expiry = lease.get("expires_at")
            available = (
                not snapshot.exists
                or current_owner == owner_id
                or not isinstance(current_expiry, datetime)
                or current_expiry <= now
            )

            if not available:
                return False

            transaction.set(
                lease_reference,
                {
                    "owner_id": owner_id,
                    "expires_at": expires_at,
                    "updated_at": (
                        firestore.SERVER_TIMESTAMP
                    ),
                },
            )
            return True

        return bool(acquire(transaction))

    def renew_weather_broadcast_lease(
        self,
        *,
        owner_id: str,
        lease_seconds: int,
    ) -> bool:
        owner_id = self._validate_required_text(
            owner_id,
            "owner_id",
            maximum_length=128,
        )
        lease_seconds = self._validate_lease_seconds(
            lease_seconds
        )
        lease_reference = (
            self._weather_broadcast_lease_reference()
        )
        expires_at = datetime.now(
            timezone.utc
        ) + timedelta(seconds=lease_seconds)
        transaction = self.database.transaction()

        @firestore.transactional
        def renew(transaction):
            snapshot = lease_reference.get(
                transaction=transaction
            )
            lease = (
                snapshot.to_dict()
                if snapshot.exists
                else None
            ) or {}

            if lease.get("owner_id") != owner_id:
                return False

            transaction.update(
                lease_reference,
                {
                    "expires_at": expires_at,
                    "updated_at": (
                        firestore.SERVER_TIMESTAMP
                    ),
                },
            )
            return True

        return bool(renew(transaction))

    def release_weather_broadcast_lease(
        self,
        *,
        owner_id: str,
    ) -> None:
        owner_id = self._validate_required_text(
            owner_id,
            "owner_id",
            maximum_length=128,
        )
        lease_reference = (
            self._weather_broadcast_lease_reference()
        )
        transaction = self.database.transaction()

        @firestore.transactional
        def release(transaction):
            snapshot = lease_reference.get(
                transaction=transaction
            )
            lease = (
                snapshot.to_dict()
                if snapshot.exists
                else None
            ) or {}

            if lease.get("owner_id") == owner_id:
                transaction.delete(lease_reference)

        release(transaction)

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
        location_id: str,
        gmail: str,
        gmail_authorized: bool = False,
        enabled: bool = True,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)

        display_name = self._validate_required_text(
            display_name,
            "display_name",
            maximum_length=100,
        )
        location_id = self._validate_location_id(
            location_id
        )
        gmail = self._validate_gmail(gmail)

        if not isinstance(gmail_authorized, bool):
            raise TypeError(
                "gmail_authorized must be a boolean"
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
            "gmail": gmail,
            "gmail_authorized": gmail_authorized,
            "enabled": enabled,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "last_login_at": None,
        }

        device_payload: dict[str, Any] = {
            "location_id": location_id,
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


    def get_enabled_accounts(
        self,
    ) -> list[dict[str, Any]]:
        snapshots = (
            self.database
            .collection(self.ACCOUNTS)
            .where(
                filter=FieldFilter(
                    "enabled",
                    "==",
                    True,
                )
            )
            .stream()
        )

        return self._snapshots_to_list(snapshots)


    def get_device(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        snapshot = self._device_reference(
            device_id
        ).get()

        return self._snapshot_to_dict(snapshot)

    def update_account(
        self,
        device_id: str,
        *,
        display_name: str | None = None,
        gmail: str | None = None,
        gmail_authorized: bool | None = None,
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

        if gmail is not None:
            updates["gmail"] = self._validate_gmail(
                gmail
            )

            # Changing the destination revokes the previous
            # authorization unless the backend explicitly grants it.
            updates["gmail_authorized"] = False

        if gmail_authorized is not None:
            if not isinstance(gmail_authorized, bool):
                raise TypeError(
                    "gmail_authorized must be a boolean"
                )

            updates["gmail_authorized"] = (
                gmail_authorized
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


    def delete_account(
        self,
        device_id: str,
    ) -> None:
        device_id = self._validate_device_id(device_id)
        device_reference = self._device_reference(
            device_id
        )
        account_reference = (
            self.database
            .collection(self.ACCOUNTS)
            .document(device_id)
        )

        # Deleting a Firestore document alone does not delete its
        # history and notification subcollections.
        self.database.recursive_delete(
            device_reference
        )
        account_reference.delete()

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
        sensor_values = self._validate_sensor_values(
            light_lux=light_lux,
            humidity_percent=humidity_percent,
            temperature_celsius=temperature_celsius,
            rain_detected=rain_detected,
        )

        return self.create_device_history(
            device_id=device_id,
            record_type="sensor",
            recorded_at=recorded_at,
            data=sensor_values,
        )

    def save_sensor_snapshot(
        self,
        device_id: str,
        sensor_data: Mapping[str, Any],
        *,
        captured_at: datetime | None = None,
    ) -> str | None:
        """Store one canonical five-minute RTDB sensor snapshot."""

        device_id = self._validate_device_id(device_id)

        if not isinstance(sensor_data, Mapping):
            raise TypeError("sensor_data must be a mapping")

        sensor_device_id = sensor_data.get("device_id")

        if sensor_device_id != device_id:
            raise ValueError(
                "sensor_data device_id must match the destination device"
            )

        sensor_values = self._validate_sensor_values(
            light_lux=sensor_data.get("light_lux"),
            humidity_percent=sensor_data.get("humidity_percent"),
            temperature_celsius=sensor_data.get("temperature_celsius"),
            rain_detected=sensor_data.get("rain_detected"),
            sensor_timestamp=sensor_data.get("timestamp"),
            require_sensor_timestamp=True,
        )

        captured_at = self._validate_datetime(
            captured_at,
            "captured_at",
        ) or datetime.now(timezone.utc)
        captured_at = captured_at.astimezone(timezone.utc)
        bucket_minute = (
            captured_at.minute
            // SENSOR_HISTORY_INTERVAL_MINUTES
        ) * SENSOR_HISTORY_INTERVAL_MINUTES
        bucket_start = captured_at.replace(
            minute=bucket_minute,
            second=0,
            microsecond=0,
        )
        snapshot_id = bucket_start.strftime("%Y%m%dT%H%MZ")
        snapshot_reference = (
            self._device_reference(device_id)
            .collection(self.SENSOR_HISTORY)
            .document(snapshot_id)
        )
        try:
            snapshot_reference.create({
                "device_id": device_id,
                "captured_at": captured_at,
                "bucket_start": bucket_start,
                "stored_at": firestore.SERVER_TIMESTAMP,
                "source": "realtime_database",
                **sensor_values,
            })
        except AlreadyExists:
            return None

        return snapshot_id

    def get_sensor_history(
        self,
        device_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        device_id = self._validate_device_id(device_id)
        limit = self._validate_limit(limit)
        snapshots = (
            self._device_reference(device_id)
            .collection(self.SENSOR_HISTORY)
            .order_by(
                "captured_at",
                direction=firestore.Query.DESCENDING,
            )
            .limit(limit)
            .stream()
        )

        return self._snapshots_to_list(snapshots)

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
        command: str | None = None,
        acknowledged: bool = False,
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

        if command is not None:
            command = command.strip().lower()

            if command not in {"open", "close"}:
                raise ValueError(
                    "command must be either 'open' or 'close'"
                )

        if not isinstance(acknowledged, bool):
            raise TypeError("acknowledged must be a boolean")

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
            "acknowledged": acknowledged,
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

        if command is not None:
            payload["command"] = command

        if status in self.TERMINAL_COMMAND_STATUSES:
            payload["completed_at"] = (
                firestore.SERVER_TIMESTAMP
            )

        # Prevent accidental replacement of an existing command.
        command_reference.create(payload)

        saved_command = self.get_command_history(
            command_id,
            device_id,
        )

        if saved_command is None:
            raise RuntimeError(
                "Command was created but could not be read"
            )

        return saved_command

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

    # =========================================================
    # Weather notifications
    #
    # Firestore path:
    # devices/{device_id}/notifications/{notification_id}
    # =========================================================

    def create_notification(
        self,
        alert: WeatherAlert,
        *,
        email_status: EmailStatus,
    ) -> bool:
        if not isinstance(alert, WeatherAlert):
            raise TypeError(
                "alert must be a WeatherAlert"
            )

        if not isinstance(email_status, EmailStatus):
            raise TypeError(
                "email_status must be an EmailStatus"
            )

        notification_reference = (
            self._notification_reference(
                alert.device_id,
                alert.alert_id,
            )
        )

        payload: dict[str, Any] = {
            "device_id": alert.device_id,
            "location_id": alert.location_id,
            "scan_id": alert.scan_id,
            "notification_type": (
                alert.alert_type.value
            ),
            "alert_key": alert.alert_key,
            "reason": alert.reason,
            "weather": alert.weather_snapshot(),
            "email": {
                "status": email_status.value,
                "attempt_count": 0,
                "gmail_message_id": None,
                "last_error": None,
                "last_attempt_at": None,
                "sent_at": None,
            },
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

        try:
            # create() fails if this deterministic notification ID already exists.
            notification_reference.create(payload)
        except AlreadyExists:
            return False

        return True


    def get_notification(
        self,
        device_id: str,
        notification_id: str,
    ) -> dict[str, Any] | None:
        snapshot = (
            self._notification_reference(
                device_id,
                notification_id,
            )
            .get()
        )

        return self._snapshot_to_dict(snapshot)


    def mark_email_sent(
        self,
        *,
        device_id: str,
        notification_id: str,
        gmail_message_id: str,
    ) -> None:
        gmail_message_id = (
            self._validate_required_text(
                gmail_message_id,
                "gmail_message_id",
                maximum_length=200,
            )
        )

        notification_reference = (
            self._notification_reference(
                device_id,
                notification_id,
            )
        )

        notification_reference.update({
            "email.status": EmailStatus.SENT.value,
            "email.attempt_count": (
                firestore.Increment(1)
            ),
            "email.gmail_message_id": (
                gmail_message_id
            ),
            "email.last_error": None,
            "email.last_attempt_at": (
                firestore.SERVER_TIMESTAMP
            ),
            "email.sent_at": (
                firestore.SERVER_TIMESTAMP
            ),
            "updated_at": (
                firestore.SERVER_TIMESTAMP
            ),
        })


    def mark_email_failed(
        self,
        *,
        device_id: str,
        notification_id: str,
        error_message: str,
    ) -> None:
        error_message = (
            self._validate_required_text(
                error_message,
                "error_message",
                maximum_length=500,
            )
        )

        notification_reference = (
            self._notification_reference(
                device_id,
                notification_id,
            )
        )

        notification_reference.update({
            "email.status": EmailStatus.FAILED.value,
            "email.attempt_count": (
                firestore.Increment(1)
            ),
            "email.gmail_message_id": None,
            "email.last_error": error_message,
            "email.last_attempt_at": (
                firestore.SERVER_TIMESTAMP
            ),
            "updated_at": (
                firestore.SERVER_TIMESTAMP
            ),
        })


    def get_device_notifications(
        self,
        device_id: str,
        *,
        notification_type: AlertType | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        device_id = self._validate_device_id(
            device_id
        )
        limit = self._validate_limit(limit)

        query = (
            self._device_reference(device_id)
            .collection(self.NOTIFICATIONS)
        )

        if notification_type is not None:
            if not isinstance(
                notification_type,
                AlertType,
            ):
                raise TypeError(
                    "notification_type must be an AlertType"
                )

            query = query.where(
                filter=FieldFilter(
                    "notification_type",
                    "==",
                    notification_type.value,
                )
            )

        snapshots = (
            query
            .order_by(
                "created_at",
                direction=firestore.Query.DESCENDING,
            )
            .limit(limit)
            .stream()
        )

        return self._snapshots_to_list(snapshots)


    def get_latest_forecast_notification(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        notifications = (
            self.get_device_notifications(
                device_id,
                notification_type=(
                    AlertType.NEAR_FORECAST_RAIN
                ),
                limit=1,
            )
        )

        if not notifications:
            return None

        return notifications[0]


    def get_latest_current_notification(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        notifications = self.get_device_notifications(
            device_id,
            notification_type=AlertType.CURRENT_RAIN,
            limit=1,
        )

        if not notifications:
            return None

        return notifications[0]

    # =========================================================
    # Locations and weather
    #
    # Firestore paths:
    # locations/{location_id}
    # locations/{location_id}/current/{scan_id}
    # locations/{location_id}/forecast/{scan_id}
    # =========================================================

    def set_location(
        self,
        *,
        location_id: str,
        name: str,
        latitude: float,
        longitude: float,
        timezone: str,
    ) -> None:
        location_id = self._validate_location_id(
            location_id
        )
        name = self._validate_required_text(
            name,
            "name",
            maximum_length=100,
        )
        timezone = self._validate_required_text(
            timezone,
            "timezone",
            maximum_length=100,
        )

        if not isinstance(latitude, (int, float)):
            raise TypeError(
                "latitude must be a number"
            )

        if not isinstance(longitude, (int, float)):
            raise TypeError(
                "longitude must be a number"
            )

        if not -90 <= latitude <= 90:
            raise ValueError(
                "latitude must be between -90 and 90"
            )

        if not -180 <= longitude <= 180:
            raise ValueError(
                "longitude must be between -180 and 180"
            )

        self._location_reference(location_id).set(
            {
                "location_id": location_id,
                "name": name,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "timezone": timezone,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )


    def get_location(
        self,
        location_id: str,
    ) -> dict[str, Any] | None:
        snapshot = (
            self._location_reference(location_id)
            .get()
        )

        return self._snapshot_to_dict(snapshot)


    def set_current_weather(
        self,
        *,
        location_id: str,
        weather: Mapping[str, Any],
        is_raining: bool,
        rain_started_at: datetime | None,
        notification_trigger: bool = False,
    ) -> str:
        if not isinstance(weather, Mapping):
            raise TypeError(
                "weather must be a mapping"
            )

        if not isinstance(is_raining, bool):
            raise TypeError(
                "is_raining must be a boolean"
            )

        if not isinstance(notification_trigger, bool):
            raise TypeError(
                "notification_trigger must be a boolean"
            )

        rain_started_at = self._validate_datetime(
            rain_started_at,
            "rain_started_at",
        )

        if is_raining and rain_started_at is None:
            raise ValueError(
                "rain_started_at is required while raining"
            )

        if not is_raining:
            rain_started_at = None

        current_reference = (
            self._location_reference(location_id)
            .collection("current")
            .document()
        )
        scan_id = current_reference.id

        if not scan_id:
            raise RuntimeError(
                "Firestore did not create a current scan ID"
            )

        payload = {
            "scan_id": scan_id,
            "scan_type": "current",
            **dict(weather),
            "is_raining": is_raining,
            "rain_started_at": rain_started_at,
            "scanned_at": firestore.SERVER_TIMESTAMP,
        }

        if notification_trigger:
            payload.update({
                "notification_trigger": True,
                "notification_status": "pending",
                "force_notify": True,
            })

        current_reference.create(payload)

        return scan_id


    def get_current_weather(
        self,
        location_id: str,
    ) -> dict[str, Any] | None:
        snapshots = list(
            self._location_reference(location_id)
            .collection("current")
            .order_by(
                "scanned_at",
                direction=firestore.Query.DESCENDING,
            )
            .limit(1)
            .stream()
        )

        if snapshots:
            return self._snapshot_to_dict(
                snapshots[0]
            )

        legacy_snapshot = (
            self._location_reference(location_id)
            .collection("weather")
            .document("current")
            .get()
        )

        return self._snapshot_to_dict(legacy_snapshot)


    def set_latest_forecast(
        self,
        *,
        location_id: str,
        forecasts: list[Mapping[str, Any]],
        notification_trigger: bool = False,
    ) -> str:
        if not isinstance(forecasts, list):
            raise TypeError(
                "forecasts must be a list"
            )

        if not isinstance(notification_trigger, bool):
            raise TypeError(
                "notification_trigger must be a boolean"
            )

        normalized_forecasts: list[dict[str, Any]] = []

        for forecast in forecasts:
            if not isinstance(forecast, Mapping):
                raise TypeError(
                    "each forecast must be a mapping"
                )

            normalized_forecasts.append(
                dict(forecast)
            )

        forecast_reference = (
            self._location_reference(location_id)
            .collection("forecast")
            .document()
        )
        scan_id = forecast_reference.id

        if not scan_id:
            raise RuntimeError(
                "Firestore did not create a forecast scan ID"
            )

        payload = {
            "scan_id": scan_id,
            "scan_type": "forecast",
            "items": normalized_forecasts,
            "forecast_count": len(
                normalized_forecasts
            ),
            "fetched_at": firestore.SERVER_TIMESTAMP,
            "scanned_at": firestore.SERVER_TIMESTAMP,
        }

        if notification_trigger:
            payload.update({
                "notification_trigger": True,
                "notification_status": "pending",
                "force_notify": True,
            })

        forecast_reference.create(payload)

        return scan_id


    def get_latest_forecast(
        self,
        location_id: str,
    ) -> dict[str, Any] | None:
        snapshots = list(
            self._location_reference(location_id)
            .collection("forecast")
            .order_by(
                "scanned_at",
                direction=firestore.Query.DESCENDING,
            )
            .limit(1)
            .stream()
        )

        if snapshots:
            return self._snapshot_to_dict(
                snapshots[0]
            )

        legacy_snapshot = (
            self._location_reference(location_id)
            .collection("forecasts")
            .document("latest")
            .get()
        )

        return self._snapshot_to_dict(legacy_snapshot)


    def get_locations(
        self,
    ) -> list[dict[str, Any]]:
        snapshots = (
            self.database
            .collection(self.LOCATIONS)
            .stream()
        )

        return self._snapshots_to_list(snapshots)

    def get_pending_weather_scans(
        self,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("limit must be an integer")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        pending: list[dict[str, Any]] = []

        for location in self.get_locations():
            location_id = location.get(
                "location_id"
            ) or location.get("document_id")

            if not isinstance(location_id, str):
                continue

            for scan_type in ("current", "forecast"):
                remaining = limit - len(pending)

                if remaining <= 0:
                    return pending

                snapshots = (
                    self._location_reference(location_id)
                    .collection(scan_type)
                    .where(
                        filter=FieldFilter(
                            "notification_status",
                            "==",
                            "pending",
                        )
                    )
                    .limit(remaining)
                    .stream()
                )

                for snapshot in snapshots:
                    data = self._snapshot_to_dict(snapshot)

                    if data is not None:
                        pending.append({
                            **data,
                            "scan_id": snapshot.id,
                            "scan_type": scan_type,
                            "location_id": location_id,
                        })

        return pending

    def get_weather_scan(
        self,
        *,
        location_id: str,
        scan_type: str,
        scan_id: str,
    ) -> dict[str, Any] | None:
        if scan_type not in {"current", "forecast"}:
            raise ValueError("scan_type must be current or forecast")

        scan_id = self._validate_required_text(
            scan_id,
            "scan_id",
            maximum_length=200,
        )
        snapshot = (
            self._location_reference(location_id)
            .collection(scan_type)
            .document(scan_id)
            .get()
        )
        return self._snapshot_to_dict(snapshot)

    def finish_weather_scan(
        self,
        *,
        location_id: str,
        scan_type: str,
        scan_id: str,
        results: list[Mapping[str, Any]],
        error: str | None = None,
    ) -> None:
        if scan_type not in {"current", "forecast"}:
            raise ValueError("scan_type must be current or forecast")

        scan_id = self._validate_required_text(
            scan_id,
            "scan_id",
            maximum_length=200,
        )
        payload: dict[str, Any] = {
            "notification_status": (
                "failed" if error else "processed"
            ),
            "notification_results": [
                dict(result) for result in results
            ],
            "notification_processed_at": (
                firestore.SERVER_TIMESTAMP
            ),
        }

        if error:
            payload["notification_error"] = error[:500]

        (
            self._location_reference(location_id)
            .collection(scan_type)
            .document(scan_id)
            .update(payload)
        )
