import os
import time
from pathlib import Path
from typing import Any, Callable

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, db


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class FirebaseServiceError(RuntimeError):
    """Lỗi khi khởi tạo hoặc sử dụng Firebase service."""


class RealtimeFirebaseService:
    APP_NAME = "smartdry-backend"

    INPUT_SENSOR = "Input_Sensor"
    INPUT_CONFIG = "Input_Config"
    OUTPUT_STATE = "Output_State"
    OUTPUT_FORECAST = "Output_Forecast"

    def __init__(
        self,
        database_url: str,
        service_account_path: str | Path,
    ) -> None:
        if not database_url:
            raise ValueError(
                "FIREBASE_DATABASE_URL không được để trống"
            )

        if not service_account_path:
            raise ValueError(
                "FIREBASE_SERVICE_ACCOUNT_KEY_PATH không được để trống"
            )

        key_path = Path(service_account_path)

        if not key_path.is_absolute():
            key_path = PROJECT_ROOT / key_path

        key_path = key_path.resolve()

        if not key_path.is_file():
            raise FileNotFoundError(
                f"Không tìm thấy Service Account: {key_path}"
            )

        self.database_url = database_url.rstrip("/")
        self.service_account_path = key_path
        self.app = self._initialize_app()

    @classmethod
    def from_env(cls) -> "FirebaseService":
        """Khởi tạo Firebase service từ code/.env."""

        database_url = os.getenv(
            "FIREBASE_DATABASE_URL",
            "",
        ).strip()

        service_account_path = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_KEY_PATH",
            "",
        ).strip()

        return cls(
            database_url=database_url,
            service_account_path=service_account_path,
        )

    def _initialize_app(self) -> firebase_admin.App:
        """Khởi tạo Firebase Admin SDK một lần."""

        try:
            return firebase_admin.get_app(self.APP_NAME)

        except ValueError:
            try:
                credential = credentials.Certificate(
                    str(self.service_account_path)
                )

                return firebase_admin.initialize_app(
                    credential,
                    {
                        "databaseURL": self.database_url,
                    },
                    name=self.APP_NAME,
                )

            except Exception as error:
                raise FirebaseServiceError(
                    f"Không thể khởi tạo Firebase: {error}"
                ) from error

    def _reference(self, path: str) -> db.Reference:
        """Tạo reference thuộc Firebase app hiện tại."""

        return db.reference(
            path,
            app=self.app,
        )

    @staticmethod
    def _validate_device_id(device_id: str) -> str:
        """Kiểm tra device_id có dùng được làm Firebase key không."""

        device_id = device_id.strip()

        if not device_id:
            raise ValueError("device_id không được để trống")

        invalid_characters = ".#$[]/"

        if any(
            character in device_id
            for character in invalid_characters
        ):
            raise ValueError(
                "device_id không được chứa . # $ [ ] hoặc /"
            )

        return device_id

    @staticmethod
    def _timestamp() -> int:
        """Trả về Unix timestamp theo giây."""

        return int(time.time())

    # =========================================================
    # Input_Sensor
    # =========================================================

    def set_sensor_data(
        self,
        device_id: str,
        light_lux: float,
        humidity_percent: float,
        temperature_celsius: float,
        rain_detected: bool,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)

        if light_lux < 0:
            raise ValueError("light_lux không được nhỏ hơn 0")

        if not 0 <= humidity_percent <= 100:
            raise ValueError(
                "humidity_percent phải nằm trong khoảng 0 đến 100"
            )

        if not -40 <= temperature_celsius <= 85:
            raise ValueError(
                "temperature_celsius phải nằm trong khoảng -40 đến 85"
            )

        if not isinstance(rain_detected, bool):
            raise TypeError("rain_detected phải là kiểu bool")

        payload: dict[str, Any] = {
            "device_id": device_id,
            "timestamp": self._timestamp(),
            "light_lux": light_lux,
            "humidity_percent": humidity_percent,
            "temperature_celsius": temperature_celsius,
            "rain_detected": rain_detected,
        }

        self._reference(
            f"{self.INPUT_SENSOR}/{device_id}"
        ).set(payload)

        return payload

    def get_sensor_data(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)

        result = self._reference(
            f"{self.INPUT_SENSOR}/{device_id}"
        ).get()

        if result is None:
            return None

        if not isinstance(result, dict):
            raise FirebaseServiceError(
                "Input_Sensor không đúng cấu trúc"
            )

        return result

    # =========================================================
    # Input_Config
    # =========================================================

    def set_device_config(
        self,
        device_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)

        payload = dict(config)

        # Ghi sau để caller không thể truyền sai device_id.
        payload["device_id"] = device_id
        payload["updated_at"] = self._timestamp()

        if not payload.get("mode"):
            raise ValueError("Config phải có trường mode")

        self._reference(
            f"{self.INPUT_CONFIG}/{device_id}"
        ).set(payload)

        return payload

    def get_device_config(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)

        result = self._reference(
            f"{self.INPUT_CONFIG}/{device_id}"
        ).get()

        if result is None:
            return None

        if not isinstance(result, dict):
            raise FirebaseServiceError(
                "Input_Config không đúng cấu trúc"
            )

        return result

    # =========================================================
    # Output_State
    # =========================================================

    def set_output_state(
        self,
        device_id: str,
        rack_state: str,
        reason: str,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)
        rack_state = rack_state.strip()
        reason = reason.strip()

        if not rack_state:
            raise ValueError("rack_state không được để trống")

        if not reason:
            raise ValueError("reason không được để trống")

        payload: dict[str, Any] = {
            "device_id": device_id,
            "updated_at": self._timestamp(),
            "rack_state": rack_state,
            "reason": reason,
        }

        self._reference(
            f"{self.OUTPUT_STATE}/{device_id}"
        ).set(payload)

        return payload

    def get_output_state(
        self,
        device_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)

        result = self._reference(
            f"{self.OUTPUT_STATE}/{device_id}"
        ).get()

        if result is None:
            return None

        if not isinstance(result, dict):
            raise FirebaseServiceError(
                "Output_State không đúng cấu trúc"
            )

        return result

    # =========================================================
    # Output_Forecast
    # =========================================================

    def create_forecast_notification(
        self,
        device_id: str,
        reason: str,
        forecast_within_minutes: int,
        rain_probability_percent: int | None,
    ) -> str:
        device_id = self._validate_device_id(device_id)
        reason = reason.strip()

        if not reason:
            raise ValueError("reason không được để trống")

        if forecast_within_minutes < 0:
            raise ValueError(
                "forecast_within_minutes không được nhỏ hơn 0"
            )

        if (
            rain_probability_percent is not None
            and not 0 <= rain_probability_percent <= 100
        ):
            raise ValueError(
                "rain_probability_percent phải từ 0 đến 100"
            )

        payload: dict[str, Any] = {
            "device_id": device_id,
            "notified_at": self._timestamp(),
            "reason": reason,
            "forecast_within_minutes": (
                forecast_within_minutes
            ),
        }

        # Firebase Realtime Database không lưu null.
        # Nếu None thì không thêm trường này vào payload.
        if rain_probability_percent is not None:
            payload["rain_probability_percent"] = (
                rain_probability_percent
            )

        notification_ref = self._reference(
            f"{self.OUTPUT_FORECAST}/{device_id}"
        ).push(payload)

        notification_id = notification_ref.key

        if notification_id is None:
            raise FirebaseServiceError(
                "Firebase không tạo được notification ID"
            )

        return notification_id

    def get_forecast_notification(
        self,
        device_id: str,
        notification_id: str,
    ) -> dict[str, Any] | None:
        device_id = self._validate_device_id(device_id)
        notification_id = notification_id.strip()

        if not notification_id:
            raise ValueError(
                "notification_id không được để trống"
            )

        result = self._reference(
            f"{self.OUTPUT_FORECAST}/{device_id}/{notification_id}"
        ).get()

        if result is None:
            return None

        if not isinstance(result, dict):
            raise FirebaseServiceError(
                "Output_Forecast không đúng cấu trúc"
            )

        return result

    def get_device_forecasts(
        self,
        device_id: str,
        limit: int = 10,
    ) -> dict[str, dict[str, Any]]:
        device_id = self._validate_device_id(device_id)

        if limit <= 0:
            raise ValueError("limit phải lớn hơn 0")

        result = (
            self._reference(
                f"{self.OUTPUT_FORECAST}/{device_id}"
            )
            .limit_to_last(limit)
            .get()
        )

        if result is None:
            return {}

        if not isinstance(result, dict):
            raise FirebaseServiceError(
                "Danh sách Output_Forecast không đúng cấu trúc"
            )

        return result

    # =========================================================
    # Realtime listener
    # =========================================================

    def listen_output_state(
        self,
        device_id: str,
        callback: Callable[[db.Event], None],
    ) -> db.ListenerRegistration:
        """Lắng nghe thay đổi Output_State theo thời gian thực."""

        device_id = self._validate_device_id(device_id)

        return self._reference(
            f"{self.OUTPUT_STATE}/{device_id}"
        ).listen(callback)