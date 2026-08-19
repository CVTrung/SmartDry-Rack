# Thay đổi mới so với `main`

## Những cập nhập quan trọng ở Frontend

- Hoàn thiện Dashboard với cảm biến realtime qua SSE, kết nối API dự báo mưa hiện có và hiển thị trạng thái giàn phơi.
- Mock các trạng thái ESP32, heartbeat, lệnh Phơi/Thu, ACK, lỗi và timeout.
- Mock dữ liệu gửi về ESP32 (đóng / thu đồ) trong History Page theo thiết bị nhờ `localStorage` của trình duyệt.
- Thêm cache dữ liệu cảm biến gần nhất khi chuyển trang (không bị mất).

## Cập nhập ở Backend

- Thêm endpoint SSE `GET /api/sensors/stream` có xác thực theo `device_id`.
- Thêm `SensorEventStream` để chuyển Firebase listener thành SSE (Server gửi 1 chiều cho client realtime, hình dung là khi server listen có event mới thì server gửi thông điệp qua endpoint SSE), kèm heartbeat và tự đóng listener.

## NHỮNG GÌ BACKEND CÒN THIẾU

Bảng dưới đây phản ánh trạng thái hiện tại của Live Mode và tiến độ Mock Mode của Front-end.

| Tính năng | Trạng thái Live Mode | Backend có thiếu? | Trạng thái Mock ở Frontend |
|-----------|----------------------|-------------------|---------------------|
| Cảm biến realtime | Đã nối qua `/api/sensors/stream` bằng SSE | Không | Không cần mock |
| Dự báo mưa | Đã nối qua `/api/weather/forecast` | Không | Không cần mock |
| Thời tiết hiện tại | Backend có `/api/weather/current`, Front-end chưa sử dụng | Không | Không cần mock |
| Trạng thái giàn phơi | Chưa nối | Thiếu API hoặc SSE đọc `Output_State` | Đã hoàn thành mock `rackState` |
| Trạng thái ESP32 và heartbeat | Chưa nối | Thiếu service và API hoặc SSE cho `Device_Status` | Đã hoàn thành mock heartbeat và trạng thái online |
| Lệnh Phơi đồ và Thu đồ | Chưa nối | Thiếu API tạo command, gửi lệnh đến ESP32 và nhận ACK | Đã hoàn thành mock thành công, thất bại và timeout |
| Lịch sử hoạt động | Chưa nối | Có `FirestoreService` nhưng thiếu API lịch sử và chưa ghi command/ACK thực tế | Đã hoàn thành mock bằng `localStorage` |
| Cấu hình auto/manual | Chưa nối | Có Firebase service nhưng thiếu API đọc và cập nhật cấu hình | Chưa triển khai giao diện mock |

Các nhóm Front-end đã hoàn thành ở Mock Mode:

- Trạng thái kết nối ESP32.
- Trạng thái giàn phơi.
- Điều khiển Phơi đồ và Thu đồ.
- ACK, lỗi và timeout của command.
- Lịch sử hoạt động.

## Đề Xuất Implementation Cho Backend

### Thứ tự ưu tiên

| Ưu tiên | Backend cần thực hiện | API đề xuất |
|---------|-----------------------|-------------|
| P0 | Tiếp nhận lệnh Phơi đồ và Thu đồ | `POST /api/rack/commands` |
| P0 | Nhận ACK, lỗi và timeout từ ESP32 | Listener tại `Command_Ack/{device_id}` |
| P1 | Trả trạng thái kết nối ESP32 | `GET /api/device/status` hoặc SSE |
| P1 | Trả trạng thái giàn phơi | `GET /api/rack/state` hoặc SSE |
| P1 | Trả lịch sử hoạt động | `GET /api/history?limit=50` |
| P2 | Đọc và cập nhật chế độ auto/manual | `GET /api/device/config`, `PUT /api/device/config` |

### Cấu trúc Firebase đề xuất

```text
Device_Status/{device_id}
Device_Commands/{device_id}/{command_id}
Command_Ack/{device_id}/{command_id}
Output_State/{device_id}
```

### Luồng xử lý command (Tham khảo)

```text
Front-end gửi POST command
    → Backend tạo command_id
    → Backend lưu Firestore với status=pending
    → Backend ghi Device_Commands
    → ESP32 nhận và thực hiện lệnh
    → ESP32 ghi Command_Ack
    → Backend cập nhật completed, failed hoặc timeout
    → Backend cập nhật Output_State
    → Front-end nhận kết quả qua API hoặc SSE
```

Backend có thể tái sử dụng các hàm hiện có trong `FirestoreService`:

- `create_command_history()`
- `update_command_status()`
- `get_device_commands()`
- `save_state_change()`


