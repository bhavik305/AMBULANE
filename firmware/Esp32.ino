/*
  =============================================================================
  Lane-Aware Intelligent Emergency Vehicle Alert System
  STEP 3 — ESP32 + NEO-6M GPS Ambulance Telemetry Firmware
  =============================================================================

  Hardware Specifications:
  -------------------------
  - Microcontroller: ESP32 DevKit V1 (30-pin / 36-pin)
  - GPS Module:      u-blox NEO-6M GPS
  - GPS Interface:   UART2 (HardwareSerial 2)
  - ESP32 GPS RX2:   GPIO 16 (Connects to NEO-6M TX pin)
  - ESP32 GPS TX2:   GPIO 17 (Connects to NEO-6M RX pin)
  - Emergency Switch:GPIO 4  (Pull-up toggle switch to GND; LOW = Emergency ON)
  - Fix Status LED:  GPIO 2  (On-board LED; solid ON when GPS fix valid)

  Required Arduino Libraries:
  ---------------------------
  1. TinyGPSPlus      by Mikal Hart (v1.0.3+)
  2. WebSockets       by Markus Sattler (v2.4.1+)
  3. ArduinoJson      by Benoit Blanchon (v6.21.0+ or v7.x)
  4. WiFi             (Built-in ESP32 core)

  Target Endpoint:
  ----------------
  WebSocket: ws://<BACKEND_HOST>:8000/ws/ambulance
  JSON Payload:
  {
    "lat": 12.971598,
    "lng": 77.594562,
    "speed_kmh": 45.2,
    "heading_deg": 88.5,
    "emergency": true,
    "ts": 1750000000.123
  }
  =============================================================================
*/

#include <WiFi.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ---------------------------------------------------------------------------
// Pin Definitions & Hardware Constants
// ---------------------------------------------------------------------------
#define GPS_RX_PIN          16      // ESP32 RX2 <- NEO-6M TX
#define GPS_TX_PIN          17      // ESP32 TX2 -> NEO-6M RX
#define GPS_BAUD_RATE       9600    // Default baud rate for NEO-6M
#define PIN_EMERGENCY_SW    4       // Toggle switch: LOW = EMERGENCY, HIGH = NORMAL
#define PIN_STATUS_LED      2       // Status / Fix indicator LED

// ---------------------------------------------------------------------------
// Network & Server Configuration
// (Update with your Wi-Fi credentials and backend server address)
// ---------------------------------------------------------------------------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char* BACKEND_HOST = "192.168.1.100";  // IP address of computer running FastAPI
const int   BACKEND_PORT = 8000;
const char* WS_PATH      = "/ws/ambulance";

// ---------------------------------------------------------------------------
// Transmission Timing & Fix Thresholds
// ---------------------------------------------------------------------------
const unsigned long TELEMETRY_INTERVAL_MS = 1000;  // 1 Hz transmission
const unsigned long MAX_GPS_AGE_MS        = 3000;  // Reject fixes older than 3 seconds

// ---------------------------------------------------------------------------
// Global Objects
// ---------------------------------------------------------------------------
HardwareSerial gpsSerial(2);
TinyGPSPlus gps;
WebSocketsClient webSocket;

unsigned long lastTelemetrySendTime = 0;
bool isWsConnected = false;

// ---------------------------------------------------------------------------
// Helper: Convert TinyGPSPlus GPS Date & Time to Unix Epoch Timestamp (seconds)
// ---------------------------------------------------------------------------
double getUnixTimestamp(TinyGPSPlus &gpsInstance) {
  if (!gpsInstance.date.isValid() || !gpsInstance.time.isValid()) {
    // If GPS time is not yet resolved, return fallback local device time
    return (double)millis() / 1000.0;
  }

  struct tm t;
  t.tm_year = gpsInstance.date.year() - 1900;
  t.tm_mon  = gpsInstance.date.month() - 1;
  t.tm_mday = gpsInstance.date.day();
  t.tm_hour = gpsInstance.time.hour();
  t.tm_min  = gpsInstance.time.minute();
  t.tm_sec  = gpsInstance.time.second();
  t.tm_isdst = 0;

  time_t epoch = mktime(&t);
  double fraction = (double)gpsInstance.time.centisecond() / 100.0;
  return (double)epoch + fraction;
}

// ---------------------------------------------------------------------------
// WebSocket Event Handler
// ---------------------------------------------------------------------------
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      isWsConnected = false;
      Serial.println("[WS] Disconnected from backend server!");
      break;

    case WStype_CONNECTED:
      isWsConnected = true;
      Serial.printf("[WS] Connected to backend endpoint: %s\n", WS_PATH);
      break;

    case WStype_TEXT:
      Serial.printf("[WS] Server ACK / Message received: %s\n", payload);
      break;

    case WStype_ERROR:
      Serial.println("[WS] WebSocket Error encountered!");
      break;

    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// Wi-Fi Connection Initialisation
// ---------------------------------------------------------------------------
void connectWiFi() {
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 15000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Connection timed out. Will retry in main loop.");
  }
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=======================================================");
  Serial.println("Lane-Aware Intelligent Emergency Vehicle System - ESP32");
  Serial.println("=======================================================");

  pinMode(PIN_EMERGENCY_SW, INPUT_PULLUP);
  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, LOW);

  // Initialize GPS UART2 on GPIO 16 (RX) and GPIO 17 (TX)
  Serial.printf("[GPS] Initializing NEO-6M UART2: RX=%d, TX=%d @ %d baud\n",
                GPS_RX_PIN, GPS_TX_PIN, GPS_BAUD_RATE);
  gpsSerial.begin(GPS_BAUD_RATE, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  // Initialise Wi-Fi
  connectWiFi();

  // Initialise WebSocket Client
  Serial.printf("[WS] Configuring WebSocket client: %s:%d%s\n",
                BACKEND_HOST, BACKEND_PORT, WS_PATH);
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, WS_PATH);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);
}

// ---------------------------------------------------------------------------
// Transmit Telemetry (strictly validates GPS fix before sending)
// ---------------------------------------------------------------------------
void sendTelemetryIfValid() {
  // RULE 1: Ensure GPS has a valid location fix and age is fresh
  if (!gps.location.isValid()) {
    digitalWrite(PIN_STATUS_LED, LOW);
    Serial.println("[GPS] Waiting for 3D fix (satellites acquiring)...");
    return;
  }

  if (gps.location.age() > MAX_GPS_AGE_MS) {
    digitalWrite(PIN_STATUS_LED, LOW);
    Serial.printf("[GPS] Stale GPS fix detected (age: %lu ms > %lu ms limit). Skipping.\n",
                  gps.location.age(), MAX_GPS_AGE_MS);
    return;
  }

  // Visual LED indicator: ON when valid fix is available
  digitalWrite(PIN_STATUS_LED, HIGH);

  // RULE 2: Read emergency switch state (active LOW with pull-up)
  bool emergencyState = (digitalRead(PIN_EMERGENCY_SW) == LOW);

  // Extract coordinates, speed, and course
  double lat = gps.location.lat();
  double lng = gps.location.lng();
  double speedKmh = gps.speed.isValid() ? gps.speed.kmph() : 0.0;
  double headingDeg = gps.course.isValid() ? gps.course.deg() : 0.0;
  double timestamp = getUnixTimestamp(gps);

  // Build JSON telemetry matching models.AmbulanceTelemetry exactly
  StaticJsonDocument<256> doc;
  doc["lat"]         = lat;
  doc["lng"]         = lng;
  doc["speed_kmh"]   = speedKmh;
  doc["heading_deg"] = headingDeg;
  doc["emergency"]   = emergencyState;
  doc["ts"]          = timestamp;

  String jsonString;
  serializeJson(doc, jsonString);

  // Send over WebSocket if connected
  if (isWsConnected) {
    webSocket.sendTXT(jsonString);
    Serial.printf("[TX] Sent Telemetry -> Lat: %.6f, Lng: %.6f, Spd: %.1f km/h, Crs: %.1f deg, Emg: %d\n",
                  lat, lng, speedKmh, headingDeg, emergencyState);
  } else {
    Serial.println("[TX] Cannot send: WebSocket not connected. Buffering skipped.");
  }
}

// ---------------------------------------------------------------------------
// Main Loop
// ---------------------------------------------------------------------------
void loop() {
  // Feed GPS characters from NEO-6M hardware serial into TinyGPSPlus parser
  while (gpsSerial.available() > 0) {
    char c = gpsSerial.read();
    gps.encode(c);
  }

  // Handle WebSocket background tasks
  webSocket.loop();

  // Handle Wi-Fi auto-reconnect if lost
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastWiFiCheck = 0;
    if (millis() - lastWiFiCheck > 10000) {
      lastWiFiCheck = millis();
      Serial.println("[WiFi] Reconnecting...");
      WiFi.reconnect();
    }
  }

  // Periodic Telemetry Transmission
  unsigned long now = millis();
  if (now - lastTelemetrySendTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetrySendTime = now;
    sendTelemetryIfValid();
  }
}
