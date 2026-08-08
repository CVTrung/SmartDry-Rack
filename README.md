# Thiết Bị Phơi Đồ Thông Minh (Smart Clothes Drying Rack)

An IoT-based smart clothes drying system that automatically extends/retracts
a drying rack based on weather conditions, light, and humidity sensor data.

## Tech Stack

| Layer      | Technology                          |
|------------|-------------------------------------|
| Website    | React (Vite) + Firebase SDK         |
| Backend    | Python 3.13 + FastAPI               |
| Database   | Firebase Realtime Database           |
| Weather    | OpenWeather One Call API 4.0         |
| Firmware   | ESP32 (PlatformIO / Arduino)         |

## Project Structure

```
code/
├── .env                    # Environment variables (git-ignored)
├── .env.example            # Template for .env
├── .gitignore
├── requirements.txt        # Python dependencies
├── database.rules.json     # Firebase Realtime DB rules
├── backend/                # Python backend (FastAPI + core logic)
│   ├── main.py             # FastAPI app entry point
│   ├── models.py           # Data models
│   ├── firebase_service.py # Firebase Realtime DB operations
│   ├── openweather_service.py # OpenWeather API 4.0 client
│   └── control_logic.py    # Rack extend/retract decision logic
├── website/                # React frontend (Vite)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── firebase.js     # Firebase client SDK init
│       └── components/
├── firmware/               # ESP32 device firmware
│   └── platformio.ini
├── tests/
│   ├── sample_data.json    # Mock data for all 4 DB nodes
│   └── test_firebase.py
└── docs/
    └── Thiết bị phơi đồ thông minh.pdf
```

## Firebase Database Nodes

| Node              | Direction | Description                          |
|-------------------|-----------|--------------------------------------|
| `Input_Sensor`    | Device →  | Sensor readings (light, humidity)    |
| `Input_Config`    | User →    | Device configuration & thresholds    |
| `Output_State`    | → Device  | Rack state (extended/retracted)      |
| `Output_Forecast` | → User    | Rain probability notifications       |

## Setup

### Backend (Python)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # Edit with your keys
uvicorn backend.main:app --reload
```

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
