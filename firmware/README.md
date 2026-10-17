# ESP32 Ambulance Telemetry Firmware & BenchTwin Simulation

This directory contains two firmware implementations for the **Lane-Aware Intelligent Emergency Vehicle Alert & Adaptive Traffic Signal Clearance System**:

1. **Production Firmware (`firmware/esp32_ambulance/esp32_ambulance.ino` / `firmware/Esp32.ino`)**:
   Full physical firmware connecting to a real NEO-6M GPS module, Wi-Fi, and the FastAPI WebSocket backend (`/ws/ambulance`).
2. **BenchTwin Simulation Firmware (`firmware/esp32_benchtwin_sim/esp32_benchtwin_sim.ino` / `firmware/Esp32_BenchTwin_Sim.ino`)**:
   Standalone simulation firmware designed to run inside the **BenchTwin** 3D browser simulator without external library dependencies.

---

## 1. Physical Hardware Setup (Production Firmware)

### Hardware Wiring
| ESP32 Pin | Peripheral / Pin | Function | Notes |
| :--- | :--- | :--- | :--- |
| **GPIO 16 (RX2)** | NEO-6M TX | UART2 RX | Receives NMEA 0183 sentences at 9600 baud |
| **GPIO 17 (TX2)** | NEO-6M RX | UART2 TX | Transmits configuration commands to GPS |
| **GPIO 4** | Emergency Switch | Digital Input | Configured as `INPUT_PULLUP` to GND (LOW = EMERGENCY, HIGH = NORMAL) |
| **GPIO 2** | Status / Fix LED | Digital Output | Solid ON when 3D GPS fix is locked; OFF when acquiring/stale |
| **3V3 / 5V** | NEO-6M VCC | Power | Input supply |
| **GND** | NEO-6M GND / Switch GND | Ground | Common ground reference |

### Required Arduino Libraries (Physical ESP32)
Install via the Arduino IDE Library Manager or `arduino-cli`:
- **WebSockets** (v2.4.1+) by Markus Sattler (`WebSocketsClient.h`)
- **ArduinoJson** (v6.21.0+ or v7.x) by Benoit Blanchon
- **TinyGPSPlus** (v1.0.3+) by Mikal Hart
- **WiFi** (built into official ESP32 Arduino Core)

### Board Selection & Flashing
- **Board**: `ESP32 Dev Module`
- **Upload Speed**: `921600`
- **Flash Frequency**: `80MHz`
- **Port**: Connected COM port (e.g. `COM3` on Windows)

---

## 2. BenchTwin Simulation Setup

### Cause of BenchTwin Error
When attempting to compile production firmware in BenchTwin, the following error is raised:
```text
WebSocketsClient isn't a type BenchTwin knows
```
**Root Cause**: BenchTwin is an in-browser virtual microcontroller runtime. Its internal parser does not bundle third-party libraries such as Markus Sattler's `WebSockets` library (`WebSocketsClient`). Furthermore, browser sandbox restrictions prevent BenchTwin from opening raw TCP/IP sockets to external LAN IP addresses.

### Simulation Firmware Design (`esp32_benchtwin_sim.ino`)
- **Zero External Dependencies**: Relies exclusively on standard Arduino core functions.
- **Identical Pinout**: Uses GPIO 16 (RX2), GPIO 17 (TX2), GPIO 4 (Emergency Switch), and GPIO 2 (Status LED).
- **Interactive Switch Support**: Reading GPIO 4 responds to virtual switches in BenchTwin (toggling between EMERGENCY and NORMAL).
- **Realistic Telemetry**: Emits coordinates along the Bangalore test corridor (Lat: ~12.9716, Lng: ~77.5946, 45.2 km/h, heading 88.5°) matching the backend's `AmbulanceTelemetry` Pydantic model.
- **Serial Telemetry Stream**: Telemetry is logged to Serial Monitor at 115200 baud with human-readable diagnostic status and valid JSON strings.

### Running in BenchTwin
1. Open [BenchTwin](https://benchtwin.com).
2. Create or open an **ESP32** project.
3. Wire a virtual switch between **GPIO 4** and **GND**.
4. Open the code editor and paste the complete content of `firmware/esp32_benchtwin_sim/esp32_benchtwin_sim.ino`.
5. Click **Run / Start Simulation**.
6. Open the **Serial Monitor** at **115200 baud** to view real-time synthetic telemetry and JSON payloads.
7. Toggle the switch on GPIO 4 to verify emergency state transitions in real time.

