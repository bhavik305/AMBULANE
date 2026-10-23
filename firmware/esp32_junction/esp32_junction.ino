/*
 * ======================================================================================
 * Lane-Aware Intelligent Emergency Vehicle Alert & Adaptive Traffic Signal Clearance System
 * 
 * MODULE: Junction ESP32 Traffic-Signal Hardware Controller
 * FILE:   firmware/esp32_junction/esp32_junction.ino
 * 
 * HARDWARE SCOPE:
 * - Low-voltage tabletop LED model for demonstration and educational testing.
 * - Conflicting greens are mathematically and logically locked out by hardware safety checks.
 * - Tabletop LED pinouts use current-limiting resistors (220 - 330 ohm).
 * 
 * LED PIN MAPPING:
 * - Approach A (Emergency Lane: North-South):
 *     GPIO 25: Green LED
 *     GPIO 26: Yellow LED
 *     GPIO 27: Red LED
 * - Approach B (Cross Street: East-West):
 *     GPIO 14: Green LED
 *     GPIO 12: Yellow LED
 *     GPIO 13: Red LED
 * - Status / Heartbeat:
 *     GPIO 2:  Onboard Blue LED
 * ======================================================================================
 */

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// -----------------------------------------------------------------------------
// Pin Configuration (Tabletop Model LEDs)
// -----------------------------------------------------------------------------
#define PIN_LED_A_GREEN   25
#define PIN_LED_A_YELLOW  26
#define PIN_LED_A_RED     27

#define PIN_LED_B_GREEN   14
#define PIN_LED_B_YELLOW  12
#define PIN_LED_B_RED     13

#define PIN_LED_STATUS    2

// -----------------------------------------------------------------------------
// Network & Authentication Configuration
// (Configure for local Wi-Fi or provide via runtime config)
// -----------------------------------------------------------------------------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASS     = "YOUR_WIFI_PASSWORD";

const char* BACKEND_HOST  = "192.168.1.100";  // Set to backend server IP
const uint16_t BACKEND_PORT = 8000;
const char* JUNCTION_ID   = "JUNC_01";
const char* AUTH_TOKEN    = "EVAS_ESP32_SECURE_TOKEN_2026";

// -----------------------------------------------------------------------------
// Traffic Signal State Machine Definitions
// -----------------------------------------------------------------------------
enum SignalState {
  STATE_A_GREEN,         // Approach A Green, B Red (Normal)
  STATE_A_YELLOW,        // Approach A Yellow, B Red
  STATE_ALL_RED_TO_B,    // All-Red clearance before B
  STATE_B_GREEN,         // Approach B Green, A Red (Normal)
  STATE_B_YELLOW,        // Approach B Yellow, A Red
  STATE_ALL_RED_TO_A,    // All-Red clearance before A
  STATE_PRIORITY_HOLD,   // Priority clearance: Approach A Green, B Red
  STATE_FAILSAFE_CYCLE   // Failsafe state on communication failure
};

SignalState currentState = STATE_A_GREEN;
unsigned long stateEnteredAtMs = 0;

// Priority tracking
bool priorityActive = false;
char currentRequestId[48] = "";
char lastProcessedRequestId[48] = "";
unsigned long priorityExpiresAtMs = 0;
unsigned long lastHeartbeatReceivedMs = 0;
unsigned long lastTelemetrySentMs = 0;

WebSocketsClient webSocket;

// -----------------------------------------------------------------------------
// Hardware Interlock & LED Actuation
// Enforces that conflicting green lights can NEVER be illuminated together.
// -----------------------------------------------------------------------------
void setLights(bool a_red, bool a_yel, bool a_grn, bool b_red, bool b_yel, bool b_grn) {
  // CRITICAL FAIL-SAFE INTERLOCK: Prevent conflicting greens
  if (a_grn && b_grn) {
    a_grn = false;
    b_grn = false;
    a_red = true;
    b_red = true;
  }

  // Actuate Approach A
  digitalWrite(PIN_LED_A_RED,    a_red ? HIGH : LOW);
  digitalWrite(PIN_LED_A_YELLOW, a_yel ? HIGH : LOW);
  digitalWrite(PIN_LED_A_GREEN,  a_grn ? HIGH : LOW);

  // Actuate Approach B
  digitalWrite(PIN_LED_B_RED,    b_red ? HIGH : LOW);
  digitalWrite(PIN_LED_B_YELLOW, b_yel ? HIGH : LOW);
  digitalWrite(PIN_LED_B_GREEN,  b_grn ? HIGH : LOW);
}

const char* getStateName(SignalState st) {
  switch (st) {
    case STATE_A_GREEN:        return "A_GREEN";
    case STATE_A_YELLOW:       return "A_YELLOW";
    case STATE_ALL_RED_TO_B:   return "ALL_RED";
    case STATE_B_GREEN:        return "B_GREEN";
    case STATE_B_YELLOW:       return "B_YELLOW";
    case STATE_ALL_RED_TO_A:   return "ALL_RED";
    case STATE_PRIORITY_HOLD:  return "PRIORITY_HOLD";
    case STATE_FAILSAFE_CYCLE: return "FAILSAFE_CYCLE";
    default:                   return "UNKNOWN";
  }
}

// -----------------------------------------------------------------------------
// Telemetry Reporting to Backend
// -----------------------------------------------------------------------------
void sendTelemetry() {
  StaticJsonDocument<384> doc;
  doc["type"] = "junction_telemetry";
  doc["junction_id"] = JUNCTION_ID;
  doc["current_state"] = getStateName(currentState);
  doc["priority_active"] = priorityActive;
  doc["active_approach"] = (currentState == STATE_B_GREEN || currentState == STATE_B_YELLOW) ? "EAST_WEST" : "NORTH_SOUTH";

  JsonObject lights = doc.createNestedObject("lights");
  JsonObject appA = lights.createNestedObject("approach_a");
  appA["red"]    = (digitalRead(PIN_LED_A_RED) == HIGH);
  appA["yellow"] = (digitalRead(PIN_LED_A_YELLOW) == HIGH);
  appA["green"]  = (digitalRead(PIN_LED_A_GREEN) == HIGH);

  JsonObject appB = lights.createNestedObject("approach_b");
  appB["red"]    = (digitalRead(PIN_LED_B_RED) == HIGH);
  appB["yellow"] = (digitalRead(PIN_LED_B_YELLOW) == HIGH);
  appB["green"]  = (digitalRead(PIN_LED_B_GREEN) == HIGH);

  doc["uptime_s"] = millis() / 1000;

  String output;
  serializeJson(doc, output);
  webSocket.sendTXT(output);
  lastTelemetrySentMs = millis();
}

void sendAcknowledgement(const char* reqId, bool accepted, const char* reason) {
  StaticJsonDocument<256> doc;
  doc["type"] = "junction_ack";
  doc["junction_id"] = JUNCTION_ID;
  doc["request_id"] = reqId;
  doc["status"] = accepted ? "ACCEPTED" : "REJECTED";
  doc["reason"] = reason;
  doc["current_state"] = getStateName(currentState);

  String output;
  serializeJson(doc, output);
  webSocket.sendTXT(output);
}

// -----------------------------------------------------------------------------
// Message Validation & Priority Request Handling
// -----------------------------------------------------------------------------
void handleIncomingMessage(const char* payload) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.println("[ESP32] JSON parse failure");
    return;
  }

  const char* type = doc["type"] | "";

  if (strcmp(type, "priority_request") == 0) {
    const char* reqId = doc["request_id"] | "";
    const char* token = doc["auth_token"] | "";
    float eta_s = doc["eta_s"] | 0.0f;

    // 1. Authenticate Request
    if (strcmp(token, AUTH_TOKEN) != 0) {
      Serial.println("[ESP32] Unauthorized priority request rejected");
      sendAcknowledgement(reqId, false, "INVALID_AUTH_TOKEN");
      return;
    }

    // 2. Idempotency / Replay protection
    if (strcmp(reqId, lastProcessedRequestId) == 0 && priorityActive) {
      sendAcknowledgement(reqId, true, "ALREADY_ACTIVE");
      return;
    }

    // 3. Accept and transition to Priority Sequence
    strncpy(currentRequestId, reqId, sizeof(currentRequestId) - 1);
    strncpy(lastProcessedRequestId, reqId, sizeof(lastProcessedRequestId) - 1);
    priorityActive = true;
    priorityExpiresAtMs = millis() + 25000;  // 25s timeout

    Serial.printf("[ESP32] Priority ACCEPTED: Req=%s, ETA=%.1fs\n", reqId, eta_s);
    sendAcknowledgement(reqId, true, "PRIORITY_SEQUENCE_INITIATED");

    // Immediate transition step if Approach B is currently Green
    if (currentState == STATE_B_GREEN) {
      currentState = STATE_B_YELLOW;
      stateEnteredAtMs = millis();
    }
    sendTelemetry();

  } else if (strcmp(type, "priority_clear") == 0) {
    const char* token = doc["auth_token"] | "";
    if (strcmp(token, AUTH_TOKEN) == 0 && priorityActive) {
      Serial.println("[ESP32] Priority clear command received");
      priorityActive = false;
      currentState = STATE_A_YELLOW;
      stateEnteredAtMs = millis();
      sendTelemetry();
    }
  }
}

// -----------------------------------------------------------------------------
// WebSocket Event Handler
// -----------------------------------------------------------------------------
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("[ESP32] WebSocket Disconnected");
      digitalWrite(PIN_LED_STATUS, LOW);
      break;
    case WStype_CONNECTED:
      Serial.println("[ESP32] WebSocket Connected to Backend!");
      digitalWrite(PIN_LED_STATUS, HIGH);
      lastHeartbeatReceivedMs = millis();
      sendTelemetry();
      break;
    case WStype_TEXT:
      lastHeartbeatReceivedMs = millis();
      handleIncomingMessage((const char*)payload);
      break;
    default:
      break;
  }
}

// -----------------------------------------------------------------------------
// State Machine Execution Loop
// -----------------------------------------------------------------------------
void updateStateMachine() {
  unsigned long now = millis();
  unsigned long elapsed = now - stateEnteredAtMs;

  // Fail-safe expiry check for active priority
  if (priorityActive && now > priorityExpiresAtMs) {
    Serial.println("[ESP32] Priority window expired; restoring safe cycling");
    priorityActive = false;
    currentState = STATE_A_YELLOW;
    stateEnteredAtMs = now;
  }

  // Handle active states
  switch (currentState) {
    case STATE_A_GREEN:
      setLights(false, false, true, true, false, false);
      if (priorityActive) {
        currentState = STATE_PRIORITY_HOLD;
        stateEnteredAtMs = now;
      } else if (elapsed > 10000) {  // 10s Green A
        currentState = STATE_A_YELLOW;
        stateEnteredAtMs = now;
        sendTelemetry();
      }
      break;

    case STATE_A_YELLOW:
      setLights(false, true, false, true, false, false);
      if (elapsed > 3000) {  // 3s Yellow A
        currentState = STATE_ALL_RED_TO_B;
        stateEnteredAtMs = now;
        sendTelemetry();
      }
      break;

    case STATE_ALL_RED_TO_B:
      setLights(true, false, false, true, false, false);
      if (elapsed > 1500) {  // 1.5s All-Red clearance
        currentState = STATE_B_GREEN;
        stateEnteredAtMs = now;
        sendTelemetry();
      }
      break;

    case STATE_B_GREEN:
      setLights(true, false, false, false, false, true);
      if (priorityActive) {
        // Emergency approaching: preemptively clear B with Yellow
        currentState = STATE_B_YELLOW;
        stateEnteredAtMs = now;
        sendTelemetry();
      } else if (elapsed > 7000) {  // 7s Green B
        currentState = STATE_B_YELLOW;
        stateEnteredAtMs = now;
        sendTelemetry();
      }
      break;

    case STATE_B_YELLOW:
      setLights(true, false, false, false, true, false);
      if (elapsed > 3000) {  // 3s Yellow B
        currentState = STATE_ALL_RED_TO_A;
        stateEnteredAtMs = now;
        sendTelemetry();
      }
      break;

    case STATE_ALL_RED_TO_A:
      setLights(true, false, false, true, false, false);
      if (elapsed > 1500) {  // 1.5s All-Red clearance
        if (priorityActive) {
          currentState = STATE_PRIORITY_HOLD;
        } else {
          currentState = STATE_A_GREEN;
        }
        stateEnteredAtMs = now;
        sendTelemetry();
      }
      break;

    case STATE_PRIORITY_HOLD:
      // EMERGENCY PRIORITY ACTIVE: Approach A Green, Cross-Street Red
      setLights(false, false, true, true, false, false);
      if (!priorityActive) {
        currentState = STATE_A_YELLOW;
        stateEnteredAtMs = now;
        sendTelemetry();
      }
      break;

    case STATE_FAILSAFE_CYCLE:
      // Flashing Yellow for cross-intersection caution
      if ((now / 500) % 2 == 0) {
        setLights(false, true, false, false, true, false);
      } else {
        setLights(false, false, false, false, false, false);
      }
      break;
  }
}

// -----------------------------------------------------------------------------
// Arduino Setup & Main Loop
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n[ESP32] Initializing Junction Traffic Signal Hardware...");

  // Configure LED pins
  pinMode(PIN_LED_A_GREEN,  OUTPUT);
  pinMode(PIN_LED_A_YELLOW, OUTPUT);
  pinMode(PIN_LED_A_RED,    OUTPUT);
  pinMode(PIN_LED_B_GREEN,  OUTPUT);
  pinMode(PIN_LED_B_YELLOW, OUTPUT);
  pinMode(PIN_LED_B_RED,    OUTPUT);
  pinMode(PIN_LED_STATUS,   OUTPUT);

  // Initial Lamp Test: All Red
  setLights(true, false, false, true, false, false);
  delay(800);

  // Connect to Wi-Fi if credentials configured
  if (strlen(WIFI_SSID) > 0 && strcmp(WIFI_SSID, "YOUR_WIFI_SSID") != 0) {
    Serial.printf("[ESP32] Connecting to Wi-Fi '%s'...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
  } else {
    Serial.println("[ESP32] Standalone/Model Mode (Configure WiFi credentials for cloud sync)");
  }

  // Initialize WebSocket connection to Backend
  char wsPath[64];
  snprintf(wsPath, sizeof(wsPath), "/ws/junction/%s", JUNCTION_ID);
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, wsPath);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);

  currentState = STATE_A_GREEN;
  stateEnteredAtMs = millis();
}

void loop() {
  webSocket.loop();
  updateStateMachine();

  // Periodic Telemetry heartbeat every 2000ms
  if (millis() - lastTelemetrySentMs > 2000) {
    sendTelemetry();
  }
}
