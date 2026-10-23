# ESP32 Junction Traffic Signal Hardware Controller

This module provides the firmware for the **Junction Traffic Signal Controller** (`firmware/esp32_junction/esp32_junction.ino`).

> [!IMPORTANT]
> **Architectural Separation**: This firmware is completely separate from the Ambulance GPS ESP32 (`firmware/esp32_ambulance/`). The junction controller operates at the intersection, while the ambulance ESP32 is vehicle-mounted for GPS tracking.

---

## 1. Tabletop Hardware Pinout & Wiring

Designed for low-voltage LED model demonstrations with current-limiting resistors (220Ω – 330Ω).

| ESP32 Pin | Function | Color | Description |
| :--- | :--- | :--- | :--- |
| **GPIO 25** | Approach A Green | 🟢 Green | Emergency Lane Green Light |
| **GPIO 26** | Approach A Yellow | 🟡 Yellow | Emergency Lane Amber / Caution |
| **GPIO 27** | Approach A Red | 🔴 Red | Emergency Lane Red / Stop |
| **GPIO 14** | Approach B Green | 🟢 Green | Cross-Street Green Light |
| **GPIO 12** | Approach B Yellow | 🟡 Yellow | Cross-Street Amber / Caution |
| **GPIO 13** | Approach B Red | 🔴 Red | Cross-Street Red / Stop |
| **GPIO 2** | Status / Heartbeat | 🔵 Blue | Solid when WebSocket is connected |
| **GND** | Common Ground | — | Connect to LED cathode rails |

---

## 2. Safety State Machine & Interlocks

The firmware maintains an autonomous local state machine:
- **`STATE_A_GREEN`**: Approach A Green (10s), Approach B Red.
- **`STATE_A_YELLOW`**: Approach A Yellow (3s), Approach B Red.
- **`STATE_ALL_RED_TO_B`**: All Red clearance (1.5s).
- **`STATE_B_GREEN`**: Approach B Green (7s), Approach A Red.
- **`STATE_B_YELLOW`**: Approach B Yellow (3s), Approach A Red.
- **`STATE_ALL_RED_TO_A`**: All Red clearance (1.5s).
- **`STATE_PRIORITY_HOLD`**: Preempted state granting green to Approach A for approaching emergency vehicle.

### Hardware Safety Interlocks:
- **Zero-Conflicting Greens**: In `setLights()`, software and hardware check guarantees that Approach A Green and Approach B Green can **never** be energized simultaneously. If an anomaly occurs, the controller automatically forces all-red.
- **Fail-Safe Timeout**: If connection drops for $>15$ seconds or a priority request expires, the controller automatically clears priority and restores autonomous safe cycling.
- **Replay Protection**: Unique `request_id` tracking rejects duplicate and expired requests.

---

## 3. Communication Protocol

### Priority Request (`Backend -> ESP32` over `/ws/junction/{junction_id}`):
```json
{
  "type": "priority_request",
  "request_id": "REQ_1792685000_a1b2c3",
  "junction_id": "JUNC_01",
  "approach_id": "NORTH_SOUTH",
  "ambulance_id": "AMB01",
  "eta_s": 14.2,
  "expiry_ts": 1792685025.0,
  "auth_token": "EVAS_ESP32_SECURE_TOKEN_2026"
}
```

### Telemetry Packet (`ESP32 -> Backend`):
```json
{
  "type": "junction_telemetry",
  "junction_id": "JUNC_01",
  "current_state": "PRIORITY_HOLD",
  "priority_active": true,
  "active_approach": "NORTH_SOUTH",
  "lights": {
    "approach_a": {"red": false, "yellow": false, "green": true},
    "approach_b": {"red": true, "yellow": false, "green": false}
  },
  "uptime_s": 128
}
```

---

## 4. Compilation & Flashing Instructions

Compile and upload via `arduino-cli`:
```bash
# Compile firmware
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/esp32_junction/esp32_junction.ino

# Flash to connected COM port (e.g. COM5)
arduino-cli upload -p COM5 --fqbn esp32:esp32:esp32 firmware/esp32_junction/esp32_junction.ino
```
