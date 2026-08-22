# SmartDry-Rack (Thiết Bị Phơi Đồ Thông Minh)

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
│   ├── main.py                         # App startup, middleware and runner lifecycle
│   ├── config.py                       # Environment configuration
│   ├── dependencies.py                 # Shared Firebase, weather and device services
│   ├── models.py                       # Weather and notification domain models
│   ├── schemas.py                      # HTTP request schemas
│   ├── routers/                        # API endpoints grouped by feature
│   │   ├── auth.py
│   │   ├── sensors.py
│   │   ├── devices.py
│   │   ├── rack.py
│   │   └── weather.py
│   ├── services/                       # Sensor, device and rack application logic
│   ├── firebase/                       # Firebase services and rules
│   ├── notifications/                  # Weather notification workflow
│   │   ├── policy.py                   # Rain rules and cooldown
│   │   ├── email.py                    # Gmail formatting and delivery
│   │   ├── broadcast.py                # Scan and account broadcasting
│   │   └── runner.py                   # Scheduling, lease and construction
│   └── openweather/                    # OpenWeather API client
├── scripts/
│   ├── authorize_gmail.py              # Gmail sender OAuth authorization
│   ├── create_account.py               # Device account setup
│   ├── delete_account.py               # Delete an account and device data
│   ├── inject_fake_sensor.py            # Inject one fake RTDB sensor snapshot
│   └── inject_fake_weather.py          # Inject fake weather into Firestore
├── tests/                              # Unit and integration tests
├── simulator/                          # ESP32 firmware and Wokwi circuit simulation
│   ├── platformio.ini                  # ESP32 board, framework and library configuration
│   ├── build.bat                       # Windows script for building firmware with PlatformIO
│   ├── libraries.txt                   # Libraries used by the Wokwi simulation
│   ├── diagram.json                    # Wokwi wiring diagram and component configuration
│   ├── wokwi.toml                      # Wokwi simulation project configuration
│   ├── wokwi-project.txt               # Wokwi project information
│   ├── src/
│   │   └── main.cpp                    # Main firmware: reads sensors, controls the rack and connects to Firebase
│   ├── rain-sensor/                    # Custom rain sensor component for Wokwi
│   │   ├── rain-sensor.chip.c          # Simulation logic for the rain sensor
│   │   ├── rain-sensor.chip.json       # Component interface and pin definitions
│   │   └── wokwi-api.h                 # Wokwi API used by the custom component
│   ├── include/                        # Shared firmware header files
│   ├── lib/                            # Local PlatformIO libraries
│   └── test/                           # Firmware test directory
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

## Simulator

The `simulator/` directory contains the ESP32 firmware and the Wokwi
simulation used to test the smart drying rack without physical hardware. The
firmware is built with PlatformIO and uses the Arduino framework.

### Firmware

The main firmware is located at `simulator/src/main.cpp`. It connects the
ESP32 to Wi-Fi and Firebase, reads the DHT22 temperature and humidity sensor,
light sensor, and rain sensor, and controls the rack through a servo motor.
The firmware also supports a manual control button, status LED, and I2C LCD
display. Sensor readings and rack state are synchronized with the backend
through Firebase Realtime Database.

### Wokwi Simulation

The circuit and component connections are defined in
`simulator/diagram.json`. The custom rain sensor used by the simulation is
implemented in `simulator/rain-sensor/`, with its behavior defined in
`rain-sensor.chip.c` and its pin interface defined in
`rain-sensor.chip.json`. Wokwi-specific project settings are stored in
`wokwi.toml` and `wokwi-project.txt`.

### Build the Firmware

From the project root, run the following commands:

```bash
cd simulator
pio run
```

On Windows, `simulator/build.bat` provides the same PlatformIO build command.
The required dependencies are declared in `platformio.ini`, including the
DHT sensor, servo, MQTT, JSON, Firebase, and LCD libraries.

## Firebase Database Nodes

SmartDry uses Firebase Authentication and both Firebase databases. Cloud
Firestore stores accounts, devices, the location catalog, append-only weather
scans, notification history, and operational history. Firebase Realtime
Database is limited to the device's live sensor and control state.

| Node                           | Direction            | Description |
|--------------------------------|----------------------|-------------|
| `Input_Sensor/{device_id}`     | ESP32 → backend      | Latest light, humidity, temperature, rain and uptime values |
| `Device_State/{device_id}`     | ESP32 ↔ backend      | Canonical `mode`, requested/current `rack_state`, device ID and update time |

`Device_State` replaces the former `Input_Config` and `Output_State` split.
The backend reads and updates this one node for `GET /api/rack/state`,
`GET/PUT /api/device/config`, and `POST /api/rack/commands`. The ESP32 reads
`mode` and `rack_state` from the same node and writes its latest physical or
automatic state back to it.

Weather forecasts and user notifications are not stored in
`Output_Forecast`. They are stored in Firestore under the location weather
history and `devices/{device_id}/notifications/{notification_id}` so that
Realtime Database remains focused on live device state.

### Sensor synchronization flow

The website does not open a Realtime Database connection. FastAPI owns the
Firebase listener for `Input_Sensor/{device_id}` and sends authenticated sensor
events to the website through `GET /api/sensors/stream` using Server-Sent
Events. This keeps Firebase credentials, device scoping, and validation in the
backend.

The backend also reads the latest RTDB snapshot for every enabled account once
every five minutes and stores it at:

```text
devices/{device_id}/sensor_history/{five_minute_bucket}
```

Each document contains the sensor values, ESP32 uptime timestamp, capture time,
five-minute bucket, storage time, and `source=realtime_database`. The bucket ID
makes repeated scans by a restarted or duplicate backend process idempotent
within the same five-minute window. Before saving, the backend compares the
RTDB uptime timestamp with the newest Firestore sensor record and ignores an
unchanged timestamp. A lower changed value is accepted because ESP32 uptime
resets after a device reboot. Firestore also creates each bucket only once, so
an existing history document is never overwritten.

To test this flow, start the backend and inject one fake RTDB snapshot:

```powershell
python scripts/inject_fake_sensor.py --device-id device_001
```

Add `--rain-detected` to simulate rain, or override values with
`--light-lux`, `--humidity-percent`, and `--temperature-celsius`. The script
writes only `Input_Sensor/{device_id}`. It does not write Firestore directly;
the backend creates the `sensor_history` document during its next five-minute
snapshot. Starting or restarting the backend runs the first snapshot
immediately. The device ID must belong to an enabled Firestore account because
the backend discovers sensor-history targets from enabled accounts.

### Backend responsibility boundaries

- `main.py` creates the FastAPI app and manages background jobs.
- `dependencies.py` owns shared service instances so routers do not create
  separate Firebase or weather clients.
- `routers/` handles authentication, HTTP input, status codes, and responses.
- `services/` contains reusable sensor, device heartbeat, and rack-command
  behavior.
- `firebase/`, `openweather/`, and `notifications/` remain the external-system
  adapters already used by the project.

This deliberately keeps the backend shallow. `FirestoreService` remains one
compatibility facade for existing callers; it can be split later only when a
specific feature needs an independent repository.

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

The setup utility records the notification Gmail but leaves it unauthorized.
After creating the account, run the single Gmail authorization flow:

```bash
python scripts/authorize_gmail.py
```

This command first validates or creates the backend sender OAuth token. It then
loads the one account selected by `DEVICE_ID`, asks for its notification Gmail,
and stores explicit recipient authorization. Use `--force` only when the sender
OAuth account itself must be authorized again.

Changing an account Gmail revokes its previous authorization. Until the backend
authorizes the new address, weather notifications are still stored in Firestore
but their email delivery status is `skipped`.

### Inject Fake Weather for an Immediate Backend Notification

Start or restart the backend, then create fake current and forecast rain scans
directly in Firestore:

```bash
python scripts/inject_fake_weather.py
```

The default writes HCM and Hanoi (`location_hn` maps to the canonical
`location_hanoi`) using the normal scan paths:

```text
locations/{location_id}/current/{scan_id}
locations/{location_id}/forecast/{scan_id}
```

The script marks these scans with `notification_status=pending`. The running
backend checks pending canonical scans every two seconds, evaluates their fake
payloads with the normal alert policy, and creates normal notification history:

```text
devices/{device_id}/notifications/{notification_id}
```

The backend then sends email to enabled authorized accounts assigned to that
location and updates the same scan to `notification_status=processed` or
`failed`. The script waits up to 15 seconds and prints that status; use
`--wait-seconds 0` to write the scans without waiting. The script writes only
weather scans and never calls Gmail directly.

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
