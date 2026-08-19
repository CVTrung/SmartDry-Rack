import unittest

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists

from backend.firebase.firestore_service import (
    FirestoreService,
)
from backend.models import (
    AlertType,
    EmailStatus,
    WeatherAlert,
)


class FirestoreNotificationTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        # Skip __init__ to prevent real Firebase access.
        self.service = object.__new__(
            FirestoreService
        )

        self.service.app = MagicMock()
        self.service.database = MagicMock()

        self.now = datetime(
            2026,
            8,
            16,
            10,
            0,
            tzinfo=timezone.utc,
        )

        self.alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=self.now,
            condition="Rain",
            rain_amount_mm=1.5,
            scan_id="current_scan_001",
        )

    def test_creates_notification(
        self,
    ) -> None:
        reference = MagicMock()

        with patch.object(
            self.service,
            "_notification_reference",
            return_value=reference,
        ):
            created = (
                self.service.create_notification(
                    self.alert,
                    email_status=(
                        EmailStatus.PENDING
                    ),
                )
            )

        self.assertTrue(created)

        reference.create.assert_called_once()

        payload = reference.create.call_args.args[0]

        self.assertEqual(
            payload["device_id"],
            "device_001",
        )
        self.assertEqual(
            payload["location_id"],
            "location_hcm",
        )
        self.assertEqual(
            payload["scan_id"],
            "current_scan_001",
        )
        self.assertEqual(
            payload["notification_type"],
            "current_rain",
        )
        self.assertEqual(
            payload["alert_key"],
            self.alert.alert_key,
        )
        self.assertEqual(
            payload["reason"],
            "Rain is happening now",
        )

        self.assertEqual(
            payload["weather"]["condition"],
            "Rain",
        )
        self.assertEqual(
            payload["weather"]["rain_amount_mm"],
            1.5,
        )

        self.assertEqual(
            payload["email"]["status"],
            "pending",
        )
        self.assertEqual(
            payload["email"]["attempt_count"],
            0,
        )
        self.assertIsNone(
            payload["email"]["gmail_message_id"]
        )

        self.assertIs(
            payload["created_at"],
            firestore.SERVER_TIMESTAMP,
        )
        self.assertIs(
            payload["updated_at"],
            firestore.SERVER_TIMESTAMP,
        )

    def test_scan_ids_create_distinct_notification_ids(
        self,
    ) -> None:
        next_scan_alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=self.now,
            condition="Rain",
            rain_amount_mm=1.5,
            scan_id="current_scan_002",
        )

        self.assertEqual(
            self.alert.alert_key,
            next_scan_alert.alert_key,
        )
        self.assertNotEqual(
            self.alert.alert_id,
            next_scan_alert.alert_id,
        )

    def test_existing_notification_returns_false(
        self,
    ) -> None:
        reference = MagicMock()
        reference.create.side_effect = (
            AlreadyExists(
                "Notification already exists"
            )
        )

        with patch.object(
            self.service,
            "_notification_reference",
            return_value=reference,
        ):
            created = (
                self.service.create_notification(
                    self.alert,
                    email_status=(
                        EmailStatus.PENDING
                    ),
                )
            )

        self.assertFalse(created)

    def test_rejects_invalid_email_status(
        self,
    ) -> None:
        with self.assertRaises(TypeError):
            self.service.create_notification(
                self.alert,
                email_status="pending",  # type: ignore
            )

    def test_gets_notification(
        self,
    ) -> None:
        reference = MagicMock()
        snapshot = MagicMock()

        snapshot.exists = True
        snapshot.id = self.alert.alert_id
        snapshot.to_dict.return_value = {
            "device_id": "device_001",
            "notification_type": "current_rain",
        }

        reference.get.return_value = snapshot

        with patch.object(
            self.service,
            "_notification_reference",
            return_value=reference,
        ):
            result = self.service.get_notification(
                "device_001",
                self.alert.alert_id,
            )

        self.assertIsNotNone(result)

        assert result is not None

        self.assertEqual(
            result["document_id"],
            self.alert.alert_id,
        )
        self.assertEqual(
            result["notification_type"],
            "current_rain",
        )

    def test_marks_email_sent(
        self,
    ) -> None:
        reference = MagicMock()

        with patch.object(
            self.service,
            "_notification_reference",
            return_value=reference,
        ):
            self.service.mark_email_sent(
                device_id="device_001",
                notification_id=(
                    self.alert.alert_id
                ),
                gmail_message_id=(
                    "gmail_message_001"
                ),
            )

        reference.update.assert_called_once()

        updates = reference.update.call_args.args[0]

        self.assertEqual(
            updates["email.status"],
            "sent",
        )
        self.assertEqual(
            updates["email.gmail_message_id"],
            "gmail_message_001",
        )
        self.assertIsNone(
            updates["email.last_error"]
        )
        self.assertIs(
            updates["email.sent_at"],
            firestore.SERVER_TIMESTAMP,
        )
        self.assertIn(
            "email.attempt_count",
            updates,
        )

    def test_marks_email_failed(
        self,
    ) -> None:
        reference = MagicMock()

        with patch.object(
            self.service,
            "_notification_reference",
            return_value=reference,
        ):
            self.service.mark_email_failed(
                device_id="device_001",
                notification_id=(
                    self.alert.alert_id
                ),
                error_message=(
                    "Gmail API returned HTTP 429"
                ),
            )

        reference.update.assert_called_once()

        updates = reference.update.call_args.args[0]

        self.assertEqual(
            updates["email.status"],
            "failed",
        )
        self.assertEqual(
            updates["email.last_error"],
            "Gmail API returned HTTP 429",
        )
        self.assertIsNone(
            updates["email.gmail_message_id"]
        )
        self.assertIn(
            "email.attempt_count",
            updates,
        )
        self.assertIs(
            updates["email.last_attempt_at"],
            firestore.SERVER_TIMESTAMP,
        )

    def test_lists_forecast_notifications(
        self,
    ) -> None:
        device_reference = MagicMock()
        collection = MagicMock()
        filtered_query = MagicMock()
        ordered_query = MagicMock()
        limited_query = MagicMock()
        snapshot = MagicMock()

        device_reference.collection.return_value = (
            collection
        )

        collection.where.return_value = (
            filtered_query
        )

        filtered_query.order_by.return_value = (
            ordered_query
        )

        ordered_query.limit.return_value = (
            limited_query
        )

        limited_query.stream.return_value = [
            snapshot
        ]

        snapshot.exists = True
        snapshot.id = "notification_001"
        snapshot.to_dict.return_value = {
            "notification_type": (
                "near_forecast_rain"
            ),
            "created_at": self.now,
        }

        with patch.object(
            self.service,
            "_device_reference",
            return_value=device_reference,
        ):
            results = (
                self.service.get_device_notifications(
                    "device_001",
                    notification_type=(
                        AlertType.NEAR_FORECAST_RAIN
                    ),
                    limit=10,
                )
            )

        device_reference.collection.assert_called_once_with(
            "notifications"
        )

        collection.where.assert_called_once()

        filtered_query.order_by.assert_called_once_with(
            "created_at",
            direction=(
                firestore.Query.DESCENDING
            ),
        )

        ordered_query.limit.assert_called_once_with(
            10
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["document_id"],
            "notification_001",
        )

    def test_gets_latest_forecast_notification(
        self,
    ) -> None:
        expected = {
            "document_id": "notification_001",
            "notification_type": (
                "near_forecast_rain"
            ),
            "created_at": self.now,
        }

        with patch.object(
            self.service,
            "get_device_notifications",
            return_value=[expected],
        ) as get_notifications:
            result = (
                self.service
                .get_latest_forecast_notification(
                    "device_001"
                )
            )

        self.assertEqual(result, expected)

        get_notifications.assert_called_once_with(
            "device_001",
            notification_type=(
                AlertType.NEAR_FORECAST_RAIN
            ),
            limit=1,
        )

    def test_latest_forecast_returns_none(
        self,
    ) -> None:
        with patch.object(
            self.service,
            "get_device_notifications",
            return_value=[],
        ):
            result = (
                self.service
                .get_latest_forecast_notification(
                    "device_001"
                )
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
