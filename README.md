# AMBULANE: Lane-Aware Intelligent Emergency Vehicle Alert & Clearance System

AMBULANE is a real-time, lane-aware intelligent alert and clearance system designed to detect approaching emergency vehicles (such as ambulances) and guide forward road traffic to safely clear the road corridor.

---

## System Architecture

```
Ambulance NEO-6M GPS
        ↓ (UART2: GPIO 16 RX / GPIO 17 TX @ 9600 baud)
      ESP32 Microcontroller (TinyGPSPlus fix validation & emergency switch)
        ↓ (WebSocket: ws://<backend-host>:8000/ws/ambulance)
  FastAPI Backend
        ↓
  Step 4: State Management & Validation
          - Coordinate bounds [-90, 90] & [-180, 180]
          - Timestamp & staleness filtering
        ↓
  Step 5: Route Engine (OSRM + Geometry)
          - Polyline route generation
          - Road corridor orthogonal distance calculation
        ↓
  Step 6: Vehicle Matching Engine
          - Forward trajectory / ahead evaluation
          - Corridor containment & heading alignment

Participant Phone Camera
        ↓ (POST /api/camera/frame/{vehicle_id})
  Step 7: Camera Reception
          - In-memory MIME, magic byte, and size validation
          - Privacy-compliant processing (no persistent storage)
        ↓
  Step 8: AI Lane/Path Estimation
          - Road ROI masking & HLS/HSV color extraction
          - Canny edge & Hough line boundary fitting
          - Lateral offset estimation (CENTER / LEFT / RIGHT)
```

---

## Directory Structure

```
├── backend/
│   ├── ai/
│   │   ├── lane_detection.py      # Computer Vision lane detection & lateral offset
│   │   ├── lane_model.py          # Model loader scaffold with weight inspection
│   │   └── preprocessing.py       # Frame decoding & road ROI extraction
│   ├── api/
│   │   ├── ambulance.py           # WebSocket endpoint /ws/ambulance
│   │   ├── camera.py              # REST endpoint POST /api/camera/frame/{id}
│   │   └── vehicle.py             # WebSocket endpoint /ws/vehicle/{id}
│   ├── main.py                    # FastAPI application entry point
│   ├── matching_engine.py         # Multi-factor spatial matching engine
│   ├── models.py                  # Pydantic data models & validation
│   ├── requirements.txt           # Python dependencies
│   ├── route_engine.py            # OSRM route & corridor geometry engine
│   ├── test_*.py                  # Unit and integration test suites
│   └── websocket_manager.py       # Central WebSocket connection & state manager
├── firmware/
│   ├── esp32_ambulance/
│   │   └── esp32_ambulance.ino   # ESP32 + NEO-6M GPS Arduino C++ firmware
│   ├── Esp32.ino                  # Standalone ESP32 sketch
│   └── README.md                  # Wiring diagram, pinout, & board guide
├── frontend/
│   └── ambulance/                 # Browser-based ambulance GPS transmitter test UI
└── .gitignore
```

---

## Quickstart

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Run Test Suites
```bash
cd backend
python -m pytest -v
```

### 3. Launch Backend
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
API documentation available at `http://localhost:8000/docs`.

---

## Hardware Configuration (Ambulance Unit)

| ESP32 Pin | NEO-6M GPS Pin | Description |
| :--- | :--- | :--- |
| **GPIO 16 (RX2)** | TX | Receives NMEA sentences |
| **GPIO 17 (TX2)** | RX | Transmits configuration |
| **GPIO 4** | Emergency Switch | Pull-up toggle to GND (LOW = EMERGENCY) |
| **GPIO 2** | Fix LED | Solid ON when 3D GPS fix is valid |
| **3.3V / 5V** | VCC | Power |
| **GND** | GND | Common Ground |
