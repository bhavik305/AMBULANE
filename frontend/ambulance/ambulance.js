// STEP 3 — temporary phone-based ambulance GPS client.
// Reuses the EXISTING backend contract: WS /ws/ambulance
// Sends the SAME normalized telemetry as the future ESP32 + NEO-6M.

const $ = (id) => document.getElementById(id);
const toastEl = $("toast");

let ws = null;
let watchId = null;
let msgCount = 0;
let emergencyOn = false;
let lastPosition = null;
let lastSendMs = 0;
let sendIntervalMs = 1500;

const backendHost = location.host || "localhost:8000";
const wsUrl = (location.protocol === "https:" ? "wss://" : "ws://") + backendHost + "/ws/ambulance";

function setConn(connected, text) {
  $("connStatus").textContent = text;
  $("statusDot").classList.toggle("live", connected);
  $("backendHost").textContent = backendHost;
}

function setGps(text) {
  $("gpsStatus").textContent = text;
}

function fmt(v, digits = 6) {
  return (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(digits);
}

function show(text, kind) {
  toastEl.textContent = text;
  toastEl.style.borderColor = kind === "error" ? "#ef4444" : "#334155";
  toastEl.hidden = false;
  clearTimeout(show._t);
  show._t = setTimeout(() => { toastEl.hidden = true; }, 3000);
}

function updateUI(pos) {
  if (!pos) return;
  lastPosition = pos;
  $("latValue").textContent = fmt(pos.coords.latitude, 6);
  $("lngValue").textContent = fmt(pos.coords.longitude, 6);
  $("accValue").textContent = (pos.coords.accuracy == null ? "—" : fmt(pos.coords.accuracy, 1)) + " m";
  const speedKmh = (pos.coords.speed == null) ? 0 : (pos.coords.speed * 3.6);
  const heading = (pos.coords.heading == null) ? 0 : pos.coords.heading;
  $("speedValue").textContent = fmt(speedKmh, 1) + " km/h" + ((pos.coords.speed == null) ? " (unavailable -> 0)" : "");
  $("headingValue").textContent = fmt(heading, 0) + "deg" + ((pos.coords.heading == null) ? " (unavailable -> 0)" : "");
  $("msgCount").textContent = msgCount;
  // Throttle sends to the configured interval (default ~1.5 s).
  const now = Date.now();
  if (now - lastSendMs >= sendIntervalMs) {
    lastSendMs = now;
    sendTelemetry(pos);
  }
}

function sendTelemetry(pos) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const speedKmh = (pos.coords.speed == null) ? 0 : (pos.coords.speed * 3.6);
  const heading = (pos.coords.heading == null) ? 0 : pos.coords.heading;
  const payload = {
    lat: pos.coords.latitude,
    lng: pos.coords.longitude,
    speed_kmh: speedKmh,
    heading_deg: heading,
    emergency: emergencyOn,
    ts: Date.now() / 1000,
    source: "phone"
  };
  try {
    ws.send(JSON.stringify(payload));
    msgCount++;
    $("msgCount").textContent = msgCount;
  } catch (e) {
    show("Send failed: " + e.message, "error");
  }
}

function startGps() {
  if (!navigator.geolocation) {
    show("Geolocation not supported on this device", "error");
    return;
  }
  $("startBtn").disabled = true;
  $("stopBtn").disabled = false;
  setGps("GPS: WAITING");
  watchId = navigator.geolocation.watchPosition(
    (pos) => { setGps("GPS: AVAILABLE"); updateUI(pos); },
    (err) => {
      let msg = "GPS error";
      if (err.code === 1) msg = "Permission denied";
      else if (err.code === 2) msg = "Position unavailable";
      else if (err.code === 3) msg = "Timeout";
      setGps("GPS: " + msg.toUpperCase());
      show(msg, "error");
    },
    { enableHighAccuracy: true, maximumAge: 1000, timeout: 10000 }
  );
  connectWs();
}

function stopGps() {
  if (watchId !== null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
  if (ws) { try { ws.close(); } catch (e) {} ws = null; }
  setConn(false, "DISCONNECTED");
  setGps("GPS: STOPPED");
  $("startBtn").disabled = false;
  $("stopBtn").disabled = true;
  $("latValue").textContent = "—";
  $("lngValue").textContent = "—";
}

function connectWs() {
  if (ws && ws.readyState === WebSocket.OPEN) return;
  setConn(false, "CONNECTING...");
  try {
    ws = new WebSocket(wsUrl);
    ws.onopen = () => { setConn(true, "CONNECTED"); show("Connected to backend"); };
    ws.onclose = () => { setConn(false, "DISCONNECTED"); };
    ws.onerror = () => { setConn(false, "ERROR"); show("WebSocket error", "error"); };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "ack") show("Backend accepted telemetry");
      } catch (e) {}
    };
  } catch (e) {
    show("WebSocket creation failed: " + e.message, "error");
    setConn(false, "DISCONNECTED");
  }
}

$("startBtn").addEventListener("click", startGps);
$("stopBtn").addEventListener("click", stopGps);

$("emergencyToggle").addEventListener("click", () => {
  emergencyOn = !emergencyOn;
  $("emergencyToggle").textContent = "EMERGENCY: " + (emergencyOn ? "ON" : "OFF");
  $("emergencyToggle").classList.toggle("off", !emergencyOn);
  $("emergencyValue").textContent = emergencyOn ? "ON" : "OFF";
  if (lastPosition) sendTelemetry(lastPosition);
  show("Emergency " + (emergencyOn ? "ON" : "OFF"));
});

$("intervalSlider").addEventListener("input", (e) => {
  sendIntervalMs = parseInt(e.target.value, 10);
  $("intervalLabel").textContent = sendIntervalMs + " ms";
  $("intervalValue").textContent = sendIntervalMs + " ms";
});

window.addEventListener("load", () => {
  $("backendHost").textContent = backendHost;
  sendIntervalMs = parseInt($("intervalSlider").value, 10);
  $("intervalLabel").textContent = sendIntervalMs + " ms";
  $("intervalValue").textContent = sendIntervalMs + " ms";
});