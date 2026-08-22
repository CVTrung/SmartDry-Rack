import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.auth_dependency import get_current_account
from backend.main import app


class DeviceControlAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_current_account] = lambda: {
            "device_id": "device_001",
            "uid": "user_001",
        }
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_current_account, None)

    @patch("backend.dependencies.realtime_firebase_service")
    def test_get_rack_state_from_device_state(
        self,
        realtime: MagicMock,
    ) -> None:
        realtime.get_device_state.return_value = {
            "rack_state": "extended",
            "mode": "manual",
            "updated_at": 1786512000,
        }

        response = self.client.get("/api/rack/state")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "device_id": "device_001",
            "rack_state": "extended",
            "mode": "manual",
            "updated_at": 1786512000,
        })

    @patch("backend.dependencies.device_heartbeat_tracker")
    @patch("backend.dependencies.realtime_firebase_service")
    def test_get_device_status_uses_uptime_observer(
        self,
        realtime: MagicMock,
        tracker: MagicMock,
    ) -> None:
        realtime.get_sensor_timestamp.return_value = 24
        tracker.observe.return_value = {
            "device_id": "device_001",
            "status": "online",
            "online": True,
            "sensor_timestamp": 24,
            "last_change_observed_at": 1786512000,
            "stale_for_seconds": 0,
            "timeout_seconds": 15,
        }

        response = self.client.get("/api/device/status")

        self.assertEqual(response.status_code, 200)
        tracker.observe.assert_called_once_with("device_001", 24)
        self.assertTrue(response.json()["online"])

    @patch("backend.dependencies.firestore_service")
    @patch("backend.dependencies.realtime_firebase_service")
    def test_put_device_mode_persists_config_history(
        self,
        realtime: MagicMock,
        firestore: MagicMock,
    ) -> None:
        realtime.get_device_state.return_value = {
            "mode": "auto",
        }
        realtime.set_device_mode.return_value = {
            "device_id": "device_001",
            "mode": "manual",
            "updated_at": 1786512000,
        }

        response = self.client.put(
            "/api/device/config",
            json={"mode": "manual"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "manual")
        firestore.save_config_change.assert_called_once()

    @patch("backend.dependencies.rack_command_service")
    def test_post_command_returns_accepted_pending(
        self,
        command_service: MagicMock,
    ) -> None:
        requested_at = datetime.now(timezone.utc)
        command_service.send.return_value = {
            "command_id": "web_001",
            "device_id": "device_001",
            "command": "open",
            "action": "extend",
            "mode": "manual",
            "status": "pending",
            "acknowledged": False,
            "requested_at": requested_at,
        }

        response = self.client.post(
            "/api/rack/commands",
            headers={"Idempotency-Key": "request_001"},
            json={
                "command": "open",
                "client_request_id": "request_001",
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "pending")
        self.assertFalse(response.json()["acknowledged"])
        command_service.send.assert_called_once_with(
            device_id="device_001",
            command="open",
            requested_by="user_001",
            idempotency_key="request_001",
        )

    @patch("backend.dependencies.firestore_service")
    @patch("backend.dependencies.rack_command_service")
    def test_get_history_normalizes_command_dto(
        self,
        command_service: MagicMock,
        firestore: MagicMock,
    ) -> None:
        timestamp = datetime.now(timezone.utc)
        command_service.command_from_record.return_value = "close"
        command_service.status_from_record.return_value = "pending"
        firestore.get_device_commands.return_value = [{
            "command_id": "web_001",
            "device_id": "device_001",
            "action": "retract",
            "source": "website",
            "status": "completed",
            "acknowledged": False,
            "requested_at": timestamp,
            "updated_at": timestamp,
        }]

        response = self.client.get(
            "/api/history",
            params={"limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["limit"], 10)
        self.assertEqual(body["items"][0]["command"], "close")
        self.assertEqual(body["items"][0]["status"], "pending")
        self.assertFalse(body["items"][0]["acknowledged"])

    def test_rejects_mismatched_idempotency_values(self) -> None:
        response = self.client.post(
            "/api/rack/commands",
            headers={"Idempotency-Key": "header_value"},
            json={
                "command": "open",
                "client_request_id": "body_value",
            },
        )

        self.assertEqual(response.status_code, 409)

    def test_cors_allows_put_and_idempotency_header(self) -> None:
        response = self.client.options(
            "/api/device/config",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": (
                    "authorization,content-type,idempotency-key"
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "PUT",
            response.headers["access-control-allow-methods"],
        )
        self.assertIn(
            "Idempotency-Key",
            response.headers["access-control-allow-headers"],
        )


if __name__ == "__main__":
    unittest.main()
