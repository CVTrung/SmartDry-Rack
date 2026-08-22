import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.services.rack_commands import (
    CommandConflictError,
    RackCommandService,
)


class RackCommandServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.realtime = MagicMock()
        self.firestore = MagicMock()
        self.realtime._validate_device_id.return_value = (
            "device_001"
        )
        self.realtime.command_lock.return_value = threading.Lock()
        self.service = RackCommandService(
            realtime=self.realtime,
            firestore=self.firestore,
        )

    def test_persists_then_dispatches_pending_command(self) -> None:
        requested_at = datetime.now(timezone.utc)
        self.firestore.get_command_history.return_value = None
        command_record = {
            "command_id": "web_test",
            "device_id": "device_001",
            "command": "open",
            "action": "extend",
            "status": "pending",
            "acknowledged": False,
            "requested_at": requested_at,
        }
        calls = []

        def create_history(**kwargs):
            calls.append("history")
            return command_record

        def dispatch_command(**kwargs):
            calls.append("dispatch")

        self.firestore.create_command_history.side_effect = (
            create_history
        )
        self.realtime.set_rack_command.side_effect = (
            dispatch_command
        )

        result = self.service.send(
            device_id="device_001",
            command="open",
            requested_by="user_001",
        )

        self.firestore.create_command_history.assert_called_once()
        self.realtime.set_rack_command.assert_called_once_with(
            device_id="device_001",
            command="open",
        )
        self.assertEqual(calls, ["history", "dispatch"])
        self.assertEqual(
            self.firestore.create_command_history.call_args.kwargs[
                "action"
            ],
            "extend",
        )
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["acknowledged"])

    def test_idempotent_retry_does_not_dispatch_again(self) -> None:
        self.firestore.get_command_history.return_value = {
            "command_id": "web_existing",
            "device_id": "device_001",
            "command": "close",
            "action": "retract",
            "status": "completed",
            "acknowledged": True,
        }

        result = self.service.send(
            device_id="device_001",
            command="close",
            requested_by="user_001",
            idempotency_key="request_001",
        )

        self.assertEqual(result["command"], "close")
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["acknowledged"])
        self.realtime.set_rack_command.assert_not_called()
        self.firestore.create_command_history.assert_not_called()

    def test_idempotency_key_cannot_change_command(self) -> None:
        self.firestore.get_command_history.return_value = {
            "command_id": "web_existing",
            "device_id": "device_001",
            "command": "open",
            "action": "extend",
            "status": "pending",
        }

        with self.assertRaises(CommandConflictError):
            self.service.send(
                device_id="device_001",
                command="close",
                requested_by="user_001",
                idempotency_key="request_001",
            )

        self.realtime.set_rack_command.assert_not_called()

if __name__ == "__main__":
    unittest.main()
