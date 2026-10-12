# ESP32 + NEO-6M GPS Ambulance Telemetry Firmware

## Hardware Wiring
| ESP32 Pin | NEO-6M GPS Pin | Notes |
| :--- | :--- | :--- |
| **GPIO 16 (RX2)** | TX | Receives NMEA sentences from GPS |
| **GPIO 17 (TX2)** | RX | Transmits configuration to GPS |
| **3V3 / 5V** | VCC | NEO-6M input supply |
| **GND** | GND | Common ground |
| **GPIO 4** | Emergency Switch | Pull-up toggle switch to GND (LOW = EMERGENCY) |
| **GPIO 2** | Fix LED | Onboard LED: solid ON when 3D fix is locked |

## Required Arduino Libraries
- **TinyGPSPlus** (v1.0.3+) by Mikal Hart
- **WebSockets** (v2.4.1+) by Markus Sattler
- **ArduinoJson** (v6.21.0+ or v7.x) by Benoit Blanchon
- **WiFi** (built into ESP32 Arduino Core)

## Board Selection in Arduino IDE
- Board: `ESP32 Dev Module`
- Upload Speed: `921600`
- Flash Frequency: `80MHz`
- Port: Select corresponding COM port (e.g. `COM3` on Windows)

## Configuration
Edit `WIFI_SSID`, `WIFI_PASSWORD`, and `BACKEND_HOST` in `esp32_ambulance.ino`.
