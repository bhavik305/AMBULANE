/*
  =============================================================================
  Lane-Aware Intelligent Emergency Vehicle Alert System
  BENCHTWIN SIMULATION FIRMWARE — ESP32 Telemetry & Sensor Simulation
  =============================================================================

  PURPOSE & CONTEXT:
  ------------------
  This sketch is a standalone, simulator-compatible firmware created specifically
  for BenchTwin (and similar lightweight browser-based simulators).

  WHY THIS SEPARATE FILE IS NECESSARY:
  ------------------------------------
  In BenchTwin, compiling the production firmware fails with:
      "WebSocketsClient isn't a type BenchTwin knows"
  BenchTwin is an in-browser virtual microcontroller workbench that does not
  include the third-party 'WebSockets' library (by Markus Sattler), nor does it
  provide a full network socket stack to reach external LAN/WAN WebSocket servers.

  This simulation firmware:
  1. Compiles with ZERO external library dependencies (uses standard ESP32/Arduino core).
  2. Preserves the exact hardware pin configuration:
     - GPS RX2: GPIO 16 (NEO-6M TX)
     - GPS TX2: GPIO 17 (NEO-6M RX)
     - UART2 Baud: 9600
     - Emergency Switch: GPIO 4 (INPUT_PULLUP; LOW = Emergency ON)
     - Status/Fix LED:   GPIO 2 (OUTPUT; HIGH = Active/Locked)
  3. Supports interactive BenchTwin hardware testing:
     - Toggling GPIO 4 in BenchTwin toggles Emergency mode in real-time.
     - Status LED on GPIO 2 reflects simulated GPS fix state.
     - Listens on UART2 (GPIO 16/17) if virtual serial data is piped.
  4. Generates realistic, clearly labelled simulated ambulance telemetry
     matching the backend `AmbulanceTelemetry` contract (12.9716, 77.5946, 45 km/h, 90 deg).
  5. Emits structured JSON directly to the Serial Monitor at 115200 baud.
  6. DOES NOT simulate fake WebSocket connections or pretend network sockets succeeded.

  NOTE:
  For physical ESP32 hardware deployment with real NEO-6M GPS and real WebSocket
  streaming to the FastAPI backend, use the production firmware:
  `firmware/esp32_ambulance/esp32_ambulance.ino` (or `firmware/Esp32.ino`).
  =============================================================================
*/

#include <Arduino.h>
#include <HardwareSerial.h>

// ---------------------------------------------------------------------------
// Hardware Pin Definitions & Constants (Strictly preserved from production)
// ---------------------------------------------------------------------------
#define GPS_RX_PIN          16      // ESP32 RX2 <- NEO-6M TX (UART2)
#define GPS_TX_PIN          17      // ESP32 TX2 -> NEO-6M RX (UART2)
#define GPS_BAUD_RATE       9600    // Standard baud rate for NEO-6M
#define PIN_EMERGENCY_SW    4       // Toggle switch: LOW = EMERGENCY, HIGH = NORMAL
#define PIN_STATUS_LED      2       // Onboard Status / Fix indicator LED

// Telemetry interval in milliseconds (1 Hz transmission)
const unsigned long TELEMETRY_INTERVAL_MS = 1000;

// ---------------------------------------------------------------------------
// Simulated Route Coordinates (Bangalore Corridor used in backend test suite)
// ---------------------------------------------------------------------------
const double SIM_START_LAT  = 12.971598;
const double SIM_START_LNG  = 77.594562;
const double SIM_SPEED_KMH  = 45.2;
const double SIM_HEADING    = 88.5;

// Step delta per second (~12.5 m/s at 45 km/h along heading ~88.5 deg)
const double LAT_STEP_PER_SEC = 0.000003;
const double LNG_STEP_PER_SEC = 0.000112;

// ---------------------------------------------------------------------------
// Global Simulation State
// ---------------------------------------------------------------------------
HardwareSerial simGpsSerial(2);

unsigned long lastTelemetrySendTime = 0;
unsigned long simStepCount = 0;
double currentSimLat = SIM_START_LAT;
double currentSimLng = SIM_START_LNG;
bool realUartBytesDetected = false;

// ---------------------------------------------------------------------------
// Helper: Format double to string with specific precision (safe without sprintf %f issues)
// ---------------------------------------------------------------------------
String formatDouble(double val, int decimals) {
  return String(val, decimals);
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=======================================================");
  Serial.println("  Lane-Aware Intelligent Emergency Vehicle Alert System");
  Serial.println("  [BENCHTWIN SIMULATION FIRMWARE — STANDALONE]");
  Serial.println("=======================================================");
  Serial.println("ENVIRONMENT NOTICE:");
  Serial.println("  - Simulator:        BenchTwin / Web-based ESP32 simulator");
  Serial.println("  - Telemetry Mode:   SYNTHETIC AMBULANCE TELEMETRY");
  Serial.println("  - WebSocket Status: DISABLED (BenchTwin does not support WebSocketsClient)");
  Serial.println("  - Target Interface: Serial Monitor output @ 115200 baud");
  Serial.println("-------------------------------------------------------");
  Serial.printf("PIN CONFIGURATION:\n");
  Serial.printf("  - GPIO %d: Emergency Switch (INPUT_PULLUP, LOW=Active)\n", PIN_EMERGENCY_SW);
  Serial.printf("  - GPIO %d: Fix / Status LED (OUTPUT)\n", PIN_STATUS_LED);
  Serial.printf("  - GPIO %d: GPS RX2 (UART2 @ %d baud)\n", GPS_RX_PIN, GPS_BAUD_RATE);
  Serial.printf("  - GPIO %d: GPS TX2 (UART2 @ %d baud)\n", GPS_TX_PIN, GPS_BAUD_RATE);
  Serial.println("=======================================================\n");

  // Configure GPIOs
  pinMode(PIN_EMERGENCY_SW, INPUT_PULLUP);
  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, HIGH); // Solid ON in simulation indicating ready

  // Initialize UART2 on hardware pins 16 & 17
  simGpsSerial.begin(GPS_BAUD_RATE, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  Serial.println("[SIM-INIT] HardwareSerial 2 initialized on GPIO 16 (RX) / 17 (TX).");
  Serial.println("[SIM-INIT] Ready. Emitting simulated telemetry at 1 Hz...\n");
}

// ---------------------------------------------------------------------------
// Generate & Emit Simulated Telemetry
// ---------------------------------------------------------------------------
void emitSimulatedTelemetry() {
  // Read physical/simulated emergency switch pin
  // Active LOW with internal pull-up: LOW = EMERGENCY, HIGH = NORMAL
  int rawSwitchVal = digitalRead(PIN_EMERGENCY_SW);
  bool isEmergency = (rawSwitchVal == LOW);

  // Advance simulated coordinates along corridor
  currentSimLat += LAT_STEP_PER_SEC;
  currentSimLng += LNG_STEP_PER_SEC;
  simStepCount++;

  // Wrap around after 120 steps (~2 km corridor traverse) to keep simulation running cleanly
  if (simStepCount > 120) {
    simStepCount = 0;
    currentSimLat = SIM_START_LAT;
    currentSimLng = SIM_START_LNG;
    Serial.println("\n[SIM-INFO] Route boundary reached; loop reset to start waypoint.\n");
  }

  // Generate synthetic Unix timestamp (offset relative to millis)
  // Base: 1750000000.0 (simulated epoch seconds)
  double simTimestamp = 1750000000.0 + ((double)millis() / 1000.0);

  // Toggle LED briefly to indicate telemetry transmission heartbeat
  digitalWrite(PIN_STATUS_LED, LOW);
  delay(20);
  digitalWrite(PIN_STATUS_LED, HIGH);

  // 1. Human-Readable Diagnostic Log (Explicitly labelled as SIMULATED)
  Serial.println("----------------------------------------------------------------");
  Serial.printf("[SIMULATED TELEMETRY #%lu] — SOURCE: BENCHTWIN SYNTHETIC ENGINE\n", simStepCount);
  Serial.printf("  Data Status:      SIMULATED (No physical NEO-6M satellite fix)\n");
  Serial.printf("  Latitude:         %s deg\n", formatDouble(currentSimLat, 6).c_str());
  Serial.printf("  Longitude:        %s deg\n", formatDouble(currentSimLng, 6).c_str());
  Serial.printf("  Speed:            %.1f km/h\n", SIM_SPEED_KMH);
  Serial.printf("  Heading:          %.1f deg\n", SIM_HEADING);
  Serial.printf("  Emergency Switch: %s (GPIO 4 raw: %d)\n", isEmergency ? "ACTIVE [EMERGENCY]" : "NORMAL", rawSwitchVal);
  Serial.printf("  Timestamp (ts):   %s\n", formatDouble(simTimestamp, 3).c_str());
  Serial.printf("  UART2 State:      %s\n", realUartBytesDetected ? "External serial bytes detected" : "Simulated GPS stream");
  Serial.printf("  Network Notice:   WebSocketsClient not available in BenchTwin (simulated)\n");

  // 2. Strict JSON string matching FastAPI backend `models.AmbulanceTelemetry`
  // Schema: {"lat": float, "lng": float, "speed_kmh": float, "heading_deg": float, "emergency": bool, "ts": float}
  String jsonPayload = "{";
  jsonPayload += "\"lat\":" + formatDouble(currentSimLat, 6) + ",";
  jsonPayload += "\"lng\":" + formatDouble(currentSimLng, 6) + ",";
  jsonPayload += "\"speed_kmh\":" + formatDouble(SIM_SPEED_KMH, 1) + ",";
  jsonPayload += "\"heading_deg\":" + formatDouble(SIM_HEADING, 1) + ",";
  jsonPayload += "\"emergency\":" + String(isEmergency ? "true" : "false") + ",";
  jsonPayload += "\"ts\":" + formatDouble(simTimestamp, 3);
  jsonPayload += "}";

  Serial.print("[JSON PAYLOAD]   ");
  Serial.println(jsonPayload);
  Serial.println("----------------------------------------------------------------\n");
}

// ---------------------------------------------------------------------------
// Main Loop
// ---------------------------------------------------------------------------
void loop() {
  // Check if any UART2 serial bytes are sent to GPIO 16 (for BenchTwin serial inject testing)
  while (simGpsSerial.available() > 0) {
    char c = simGpsSerial.read();
    realUartBytesDetected = true;
    // Echo any received raw bytes for debugging if needed
    (void)c;
  }

  // Periodic Telemetry Generation (1 Hz)
  unsigned long now = millis();
  if (now - lastTelemetrySendTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetrySendTime = now;
    emitSimulatedTelemetry();
  }
}
