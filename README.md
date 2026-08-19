# Thiết Bị Phơi Đồ Thông Minh (SmartDry-Rack)

An IoT-based smart clothes drying system that automatically extends/retracts
a drying rack based on weather conditions, light, and humidity sensor data.

## Tech Stack

| Layer      | Technology                          |
|------------|-------------------------------------|
| Website    | React (Vite) + Firebase SDK         |
| Backend    | Python 3.13 + FastAPI               |
| Database   | Cloud Firestore + Firebase Realtime Database |
| Weather    | OpenWeather Current Weather API and 5 Day / 3 Hour Forecast API        |
| Firmware   | ESP32 (PlatformIO / Arduino)         |

## Project Structure

```
code/
├── .env                    # Environment variables (git-ignored)
├── .env.example            # Template for .env
├── .gitignore
├── firebase.json           # Firebase deployment configuration
├── requirements.txt        # Python dependencies
├── backend/                # Python backend (FastAPI + core logic)
│   ├── main.py                         # FastAPI app entry point
│   ├── config.py                       # Environment configuration
│   ├── models.py                       # Data models
│   ├── control_logic.py                # Rack control decisions
│   ├── firebase/                       # Firebase services and rules
│   ├── notifications/                  # Weather and Gmail notifications
│   └── openweather/                    # OpenWeather API client
├── scripts/
│   ├── authorize_gmail.py              # Gmail sender OAuth authorization
│   ├── authorize_account_gmail.py      # Account recipient authorization
│   ├── create_account.py               # Device account setup
│   └── delete_account.py               # Delete an account and device data
├── tests/                              # Unit and integration tests
├── website/                # React frontend (Vite)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── firebase.js     # Firebase client SDK init
│       ├── components/
│       ├── pages/
│       └── services/
├── run_dev.bat                       # Start backend and website
├── run_weather_notifications.bat     # Test weather notification checks
└── run_test.bat                      # Run the Python test suite
```

## Firebase Database Nodes

SmartDry uses both Firebase databases. Cloud Firestore stores accounts,
devices, the location catalog, append-only weather scans, notification history,
and operational history. Firebase Realtime Database carries the live sensor,
configuration, rack-state, and forecast values exchanged with the ESP32 and
website.

| Node              | Direction | Description                          |
|-------------------|-----------|--------------------------------------|
| `Input_Sensor`    | Device →  | Sensor readings (light, humidity)    |
| `Input_Config`    | User →    | Device configuration & thresholds    |
| `Output_State`    | → Device  | Rack state (extended/retracted)      |
| `Output_Forecast` | → User    | Rain probability notifications       |

### Firestore Account and Device Schema

`accounts/{device_id}` is the authentication source of truth and stores
`device_id`, `display_name`, `gmail`, `gmail_authorized`, `enabled`, timestamps,
and `last_login_at`.
`devices/{device_id}` stores only operational metadata: `location_id`,
timestamps, and its history, command, and notification subcollections. New
accounts are created with `location_id` on the device document; existing
device documents should be migrated to remove the old duplicated fields.

### Location Catalog

Weather notifications use the Firestore `locations` collection as a
location catalog. `LOCATION_ID` selects one document from the collection.
Each location document should contain a display name, timezone, and
coordinates:

```text
locations/location_hcm
  name: Ho Chi Minh City
  timezone: Asia/Ho_Chi_Minh
  latitude: 10.8231
  longitude: 106.6297

locations/location_hanoi
  name: Hanoi
  timezone: Asia/Ho_Chi_Minh
  latitude: 21.0278
  longitude: 105.8342
```

The selected document controls both the OpenWeather coordinates and the
location name and local time shown in notification emails. On every scheduled
check, the backend scans every document in `locations`, including locations
that currently have no assigned account. It then discovers all enabled
accounts and broadcasts any qualifying alert to the accounts assigned to each
location. OpenWeather is called once per location per current or forecast scan.

Weather data is append-only and uses a generated ID for each scan:

```text
locations/{location_id}/current/{scan_id}
locations/{location_id}/forecast/{scan_id}
devices/{device_id}/notifications/{notification_id}
```

Current and forecast scan documents contain `scan_id`, `scan_type`, and
`scanned_at`. Notification documents contain the source `scan_id`; their IDs
are unique to that scan, while `alert_key` continues to identify the same rain
event for duplicate prevention.

The account setup script contains matching presets for `location_hcm` and
`location_hanoi`. Add a preset there before using another location ID with the
script.

## Setup

### Backend (Python)

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
cp .env.example .env         # Edit with your keys
uvicorn backend.main:app --reload
```

### Create a Device Account

Run the setup utility from the project root to create a Firebase Auth login,
matching Firestore account/device records, and an optional location catalog
entry:

```bash
python scripts/create_account.py
```

It prompts only for the device details, location ID, and password. The chosen
location ID fills its name, coordinates, and timezone from the preset list.
Enabled accounts are discovered automatically by the notification scheduler;
the backend does not need to be restarted when another account is added.

To permanently remove an account, its Firebase Auth user, device data,
notification history, and other device subcollections, run:

```bash
python scripts/delete_account.py
```

The setup utility asks for the account Gmail and explicit authorization to send
weather emails to it. For an existing account, add or replace its authorized
Gmail with:

```bash
python scripts/authorize_account_gmail.py
```

Changing an account Gmail revokes its previous authorization. Until the backend
authorizes the new address, weather notifications are still stored in Firestore
but their email delivery status is `skipped`.

### Test Weather Notifications

After configuring `.env`, run:

```bat
run_weather_notifications.bat
```

The launcher starts one backend process, discovers every enabled Firebase
account, runs the current-weather and forecast checks immediately, and
temporarily changes both check intervals to one minute. It does not change
`.env`. A notification is created only when the configured rain threshold,
warning window, transition, and cooldown rules match.

The notification scheduler is controlled by `backend.main`. A transactional
Firestore lease ensures that only one running backend process broadcasts at a
time, including when Uvicorn has multiple workers. Gmail transient failures are
retried up to `GMAIL_MAX_RETRY_ATTEMPTS` by the Gmail API client.

### Website (React)

```bash
cd website
npm install
cp .env.example .env         # Edit with your Firebase client config
npm run dev
```

### Environment Variables

See [.env.example](.env.example) for all required variables.

## License

This project is for educational purposes (VLCCNTT course).
