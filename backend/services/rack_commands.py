import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from google.api_core.exceptions import AlreadyExists

from backend.firebase import (
    FirestoreService,
    RealtimeFirebaseService,
)


class CommandConflictError(ValueError):
    """Raised when one idempotency key is reused for another command."""


class CommandDispatchError(RuntimeError):
    """Raised when a command could not be published to Firebase."""


class RackCommandService:
    ACTIONS = {
        "open": "extend",
        "close": "retract",
    }

    def __init__(
        self,
        realtime: RealtimeFirebaseService,
        firestore: FirestoreService,
    ) -> None:
        self.realtime = realtime
        self.firestore = firestore

    @staticmethod
    def _command_id(
        device_id: str,
        idempotency_key: str | None,
    ) -> str:
        if idempotency_key is None:
            return f"web_{uuid.uuid4().hex}"

        idempotency_key = idempotency_key.strip()

        if not idempotency_key:
            raise ValueError("Idempotency-Key must not be empty")

        if len(idempotency_key) > 200:
            raise ValueError(
                "Idempotency-Key must not exceed 200 characters"
            )

        digest = hashlib.sha256(
            f"{device_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()
        return f"web_{digest}"

    @classmethod
    def _validate_command(cls, command: str) -> str:
        command = command.strip().lower()

        if command not in cls.ACTIONS:
            raise ValueError(
                "command must be either 'open' or 'close'"
            )

        return command

    @classmethod
    def command_from_record(
        cls,
        record: dict[str, Any],
    ) -> str | None:
        command = record.get("command")

        if command in cls.ACTIONS:
            return command

        action = record.get("action")

        for candidate, candidate_action in cls.ACTIONS.items():
            if action == candidate_action:
                return candidate

        return None

    @staticmethod
    def status_from_record(record: dict[str, Any]) -> str:
        """Expose dispatch failure, otherwise keep status pending.

        Device_State has no command-correlated ACK, so a rack-state value
        must never promote web history to completed.
        """

        return (
            "failed"
            if record.get("status") == "failed"
            else "pending"
        )

    def send(
        self,
        *,
        device_id: str,
        command: str,
        requested_by: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        device_id = self.realtime._validate_device_id(device_id)
        command = self._validate_command(command)
        command_id = self._command_id(
            device_id,
            idempotency_key,
        )
        action = self.ACTIONS[command]
        lock = self.realtime.command_lock(device_id)

        with lock:
            existing = self.firestore.get_command_history(
                command_id,
                device_id,
            )

            if existing is not None:
                existing_command = self.command_from_record(existing)

                if existing_command != command:
                    raise CommandConflictError(
                        "Idempotency-Key was already used for "
                        "a different command"
                    )

                return self.response_from_record(existing)

            requested_at = datetime.now(timezone.utc)

            try:
                record = self.firestore.create_command_history(
                    command_id=command_id,
                    device_id=device_id,
                    action=action,
                    source="website",
                    reason="web_monitor_command",
                    requested_by=requested_by,
                    requested_at=requested_at,
                    command=command,
                    acknowledged=False,
                )
            except AlreadyExists:
                record = self.firestore.get_command_history(
                    command_id,
                    device_id,
                )

                if (
                    record is None
                    or self.command_from_record(record) != command
                ):
                    raise CommandConflictError(
                        "Idempotency-Key was already used"
                    )

                return self.response_from_record(record)

            try:
                self.realtime.set_rack_command(
                    device_id=device_id,
                    command=command,
                )
            except Exception as error:
                self.firestore.update_command_status(
                    command_id=command_id,
                    device_id=device_id,
                    status="failed",
                    error_code="firebase_dispatch_failed",
                )
                raise CommandDispatchError(
                    "Could not publish rack command to Firebase"
                ) from error

            return self.response_from_record(record)

    @classmethod
    def response_from_record(
        cls,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "command_id": record.get("command_id"),
            "device_id": record.get("device_id"),
            "command": cls.command_from_record(record),
            "action": record.get("action"),
            "mode": "manual",
            "status": cls.status_from_record(record),
            "acknowledged": False,
            "requested_at": record.get("requested_at"),
        }
