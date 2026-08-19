import unittest

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from firebase_admin import firestore

from backend.firebase.firestore_service import (
    FirestoreService,
)


class FirestoreWeatherTests(unittest.TestCase):
    def setUp(self) -> None:
        # Skip __init__ to avoid real Firebase access.
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

    def test_sets_location(self) -> None:
        reference = MagicMock()

        with patch.object(
            self.service,
            "_location_reference",
            return_value=reference,
        ):
            self.service.set_location(
                location_id="location_hcm",
                name="Ho Chi Minh City",
                latitude=10.7769,
                longitude=106.7009,
                timezone="Asia/Ho_Chi_Minh",
            )

        reference.set.assert_called_once()

        payload = reference.set.call_args.args[0]

        self.assertEqual(
            payload["location_id"],
            "location_hcm",
        )
        self.assertEqual(
            payload["name"],
            "Ho Chi Minh City",
        )
        self.assertEqual(
            payload["latitude"],
            10.7769,
        )
        self.assertEqual(
            payload["longitude"],
            106.7009,
        )
        self.assertEqual(
            payload["timezone"],
            "Asia/Ho_Chi_Minh",
        )
        self.assertIs(
            payload["updated_at"],
            firestore.SERVER_TIMESTAMP,
        )

        self.assertTrue(
            reference.set.call_args.kwargs["merge"]
        )

    def test_rejects_invalid_coordinates(self) -> None:
        with self.assertRaises(ValueError):
            self.service.set_location(
                location_id="location_hcm",
                name="Ho Chi Minh City",
                latitude=91,
                longitude=106.7009,
                timezone="Asia/Ho_Chi_Minh",
            )

        with self.assertRaises(ValueError):
            self.service.set_location(
                location_id="location_hcm",
                name="Ho Chi Minh City",
                latitude=10.7769,
                longitude=181,
                timezone="Asia/Ho_Chi_Minh",
            )

    def test_gets_location(self) -> None:
        reference = MagicMock()
        snapshot = MagicMock()

        snapshot.exists = True
        snapshot.id = "location_hcm"
        snapshot.to_dict.return_value = {
            "name": "Ho Chi Minh City",
            "latitude": 10.7769,
            "longitude": 106.7009,
        }

        reference.get.return_value = snapshot

        with patch.object(
            self.service,
            "_location_reference",
            return_value=reference,
        ):
            result = self.service.get_location(
                "location_hcm"
            )

        self.assertIsNotNone(result)

        assert result is not None

        self.assertEqual(
            result["document_id"],
            "location_hcm",
        )
        self.assertEqual(
            result["name"],
            "Ho Chi Minh City",
        )

    def test_sets_current_weather(self) -> None:
        location_reference = MagicMock()
        weather_reference = MagicMock()

        (
            location_reference
            .collection.return_value
            .document.return_value
        ) = weather_reference
        weather_reference.id = "current_scan_001"

        weather = {
            "condition": "Rain",
            "temperature_c": 28.5,
            "rain_amount_mm": 1.2,
            "observed_at": self.now,
        }

        with patch.object(
            self.service,
            "_location_reference",
            return_value=location_reference,
        ):
            result = self.service.set_current_weather(
                location_id="location_hcm",
                weather=weather,
                is_raining=True,
                rain_started_at=self.now,
            )

        location_reference.collection.assert_called_once_with(
            "current"
        )
        (
            location_reference
            .collection.return_value
            .document.assert_called_once_with()
        )

        payload = weather_reference.create.call_args.args[0]

        self.assertEqual(result, "current_scan_001")
        self.assertEqual(payload["scan_id"], result)
        self.assertEqual(payload["scan_type"], "current")

        self.assertEqual(
            payload["condition"],
            "Rain",
        )
        self.assertTrue(
            payload["is_raining"]
        )
        self.assertEqual(
            payload["rain_started_at"],
            self.now,
        )
        self.assertIs(
            payload["scanned_at"],
            firestore.SERVER_TIMESTAMP,
        )

    def test_dry_weather_clears_rain_started_at(
        self,
    ) -> None:
        location_reference = MagicMock()
        weather_reference = MagicMock()

        (
            location_reference
            .collection.return_value
            .document.return_value
        ) = weather_reference
        weather_reference.id = "current_scan_002"

        with patch.object(
            self.service,
            "_location_reference",
            return_value=location_reference,
        ):
            self.service.set_current_weather(
                location_id="location_hcm",
                weather={"condition": "Clear"},
                is_raining=False,
                rain_started_at=self.now,
            )

        payload = weather_reference.create.call_args.args[0]

        self.assertFalse(
            payload["is_raining"]
        )
        self.assertIsNone(
            payload["rain_started_at"]
        )

    def test_raining_requires_start_time(self) -> None:
        with self.assertRaises(ValueError):
            self.service.set_current_weather(
                location_id="location_hcm",
                weather={"condition": "Rain"},
                is_raining=True,
                rain_started_at=None,
            )

    def test_gets_current_weather(self) -> None:
        location_reference = MagicMock()
        current_collection = MagicMock()
        snapshot = MagicMock()

        snapshot.exists = True
        snapshot.id = "current_scan_001"
        snapshot.to_dict.return_value = {
            "condition": "Rain",
            "is_raining": True,
            "rain_started_at": self.now,
        }

        location_reference.collection.return_value = (
            current_collection
        )
        (
            current_collection.order_by.return_value
            .limit.return_value.stream.return_value
        ) = [snapshot]

        with patch.object(
            self.service,
            "_location_reference",
            return_value=location_reference,
        ):
            result = self.service.get_current_weather(
                "location_hcm"
            )

        self.assertIsNotNone(result)

        assert result is not None

        self.assertEqual(
            result["document_id"],
            "current_scan_001",
        )
        self.assertTrue(
            result["is_raining"]
        )

    def test_sets_latest_forecast(self) -> None:
        location_reference = MagicMock()
        forecast_reference = MagicMock()

        (
            location_reference
            .collection.return_value
            .document.return_value
        ) = forecast_reference
        forecast_reference.id = "forecast_scan_001"

        forecasts = [
            {
                "forecast_at": self.now,
                "condition": "Rain",
                "rain_probability_percent": 80,
            },
            {
                "forecast_at": self.now,
                "condition": "Clouds",
                "rain_probability_percent": 30,
            },
        ]

        with patch.object(
            self.service,
            "_location_reference",
            return_value=location_reference,
        ):
            result = self.service.set_latest_forecast(
                location_id="location_hcm",
                forecasts=forecasts,
            )

        location_reference.collection.assert_called_once_with(
            "forecast"
        )
        (
            location_reference
            .collection.return_value
            .document.assert_called_once_with()
        )

        payload = forecast_reference.create.call_args.args[0]

        self.assertEqual(result, "forecast_scan_001")
        self.assertEqual(payload["scan_id"], result)
        self.assertEqual(payload["scan_type"], "forecast")

        self.assertEqual(
            payload["forecast_count"],
            2,
        )
        self.assertEqual(
            payload["items"],
            forecasts,
        )
        self.assertIs(
            payload["fetched_at"],
            firestore.SERVER_TIMESTAMP,
        )

    def test_gets_latest_forecast(self) -> None:
        location_reference = MagicMock()
        forecast_collection = MagicMock()
        snapshot = MagicMock()

        snapshot.exists = True
        snapshot.id = "forecast_scan_001"
        snapshot.to_dict.return_value = {
            "forecast_count": 1,
            "items": [
                {
                    "condition": "Rain",
                    "rain_probability_percent": 80,
                }
            ],
        }

        location_reference.collection.return_value = (
            forecast_collection
        )
        (
            forecast_collection.order_by.return_value
            .limit.return_value.stream.return_value
        ) = [snapshot]

        with patch.object(
            self.service,
            "_location_reference",
            return_value=location_reference,
        ):
            result = self.service.get_latest_forecast(
                "location_hcm"
            )

        self.assertIsNotNone(result)

        assert result is not None

        self.assertEqual(
            result["document_id"],
            "forecast_scan_001",
        )
        self.assertEqual(
            result["forecast_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
