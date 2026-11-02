// STEP 3 — Phone-based ambulance GPS client with Leaflet Map & Offline LAN Tile Support
// Reuses the EXISTING backend contract: WS /ws/ambulance
// Sends the SAME normalized telemetry as the ESP32 + NEO-6M.

const $ = (id) => document.getElementById(id);
const toastEl = $("toast");

let ws = null;
let watchId = null;
let msgCount = 0;
let emergencyOn = false;
let lastPosition = null;
let lastSendMs = 0;
let sendIntervalMs = 1500;

// Dynamic origin & WebSocket host resolution (supports localhost, 10.x.x.x, 192.168.x.x)
const origin = window.location.origin || (window.location.protocol + "//" + (window.location.host || "localhost:8000"));
const wsProto = window.location.protocol === "https:" ? "wss://" : "ws:";
const wsHost = window.location.host || (window.location.hostname ? (window.location.hostname + (window.location.port ? ":" + window.location.port : "")) : "localhost:8000");
const wsUrl = `${wsProto}//${wsHost}/ws/ambulance`;

// Default coordinates (Corridor coordinates for demo & fallback)
const DEFAULT_LAT = 9.4580;
const DEFAULT_LNG = 76.4407;

// Leaflet Map state
let leafletMap = null;
let ambMarker = null;

function setConn(connected, text) {
  $("connStatus").textContent = text;
  $("statusDot").classList.toggle("live", connected);
  $("backendHost").textContent = wsHost;
}

function setGps(text) {
  $("gpsStatus").textContent = text;
}

function fmt(v, digits = 6) {
  return (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(digits);
}

function show(text, kind) {
  if (!toastEl) return;
  toastEl.textContent = text;
  toastEl.style.borderColor = kind === "error" ? "#ef4444" : "#334155";
  toastEl.hidden = false;
  clearTimeout(show._t);
  show._t = setTimeout(() => { toastEl.hidden = true; }, 3500);
}

function initAmbulanceMap() {
  if (leafletMap || !window.L || !window.L.map) return;
  const mapEl = $("map");
  if (!mapEl) return;

  try {
    // 1. Initialize map immediately and unconditionally with default coords
    leafletMap = L.map("map", {
      zoomControl: true,
      attributionControl: true
    }).setView([DEFAULT_LAT, DEFAULT_LNG], 16);

    // 2. Primary tile URL: Local backend proxy
    const primaryTileUrl = `${origin}/api/map/tiles/{z}/{x}/{y}.png`;
    const tileLayer = L.tileLayer(primaryTileUrl, {
      maxZoom: 19,
      crossOrigin: true,
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution: "&copy; <a href='https://www.openstreetmap.org/copyright' target='_blank'>OpenStreetMap</a> contributors"
    }).addTo(leafletMap);

    // Failover handler for tiles
    let failoverCount = 0;
    tileLayer.on("tileerror", () => {
      failoverCount++;
      if (failoverCount === 3) {
        console.warn("Local tile proxy error; failing over to direct OSM...");
        tileLayer.setUrl("https://tile.openstreetmap.org/{z}/{x}/{y}.png");
      } else if (failoverCount > 6) {
        console.warn("Failing over to CartoDB Voyager...");
        tileLayer.setUrl("https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png");
      }
    });

    // 3. Ambulance Marker
    const ambIcon = L.divIcon({
      className: "custom-amb-marker",
      html: `<div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;background:#EF4444;border:3px solid #FFF;border-radius:50%;box-shadow:0 0 14px rgba(239,68,68,0.8);font-size:20px;">🚑</div>`,
      iconSize: [40, 40],
      iconAnchor: [20, 20]
    });
    ambMarker = L.marker([DEFAULT_LAT, DEFAULT_LNG], { icon: ambIcon }).addTo(leafletMap);
    ambMarker.bindPopup("<b>Ambulance AMB01</b><br>Standby");

    // 4. Staggered invalidations for mobile browsers
    setTimeout(() => { if (leafletMap) leafletMap.invalidateSize(true); }, 250);
    setTimeout(() => { if (leafletMap) leafletMap.invalidateSize(true); }, 600);

    // 5. Mobile viewport resize and orientation listeners
    window.addEventListener("resize", () => {
      if (leafletMap) leafletMap.invalidateSize(true);
    });
    window.addEventListener("orientationchange", () => {
      setTimeout(() => { if (leafletMap) leafletMap.invalidateSize(true); }, 300);
    });

    if (window.ResizeObserver && mapEl) {
      new ResizeObserver(() => {
        if (leafletMap) leafletMap.invalidateSize(true);
      }).observe(mapEl);
    }
  } catch (err) {
    console.error("Error initializing ambulance Leaflet map:", err);
  }
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
  $("headingValue").textContent = fmt(heading, 0) + "°" + ((pos.coords.heading == null) ? " (unavailable -> 0)" : "");
  $("msgCount").textContent = msgCount;

  // Update Leaflet marker position
  if (leafletMap && ambMarker && pos.coords.latitude && pos.coords.longitude) {
    const latLng = [pos.coords.latitude, pos.coords.longitude];
    ambMarker.setLatLng(latLng);
    ambMarker.setPopupContent(`<b>Ambulance AMB01</b><br>Speed: ${fmt(speedKmh, 1)} km/h<br>Emergency: ${emergencyOn ? "YES" : "NO"}`);
  }

  // Throttle sends to configured interval
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

let simulatedTimer = null;

function startGps() {
  $("startBtn").disabled = true;
  $("stopBtn").disabled = false;
  setGps("GPS: WAITING");

  // Check for secure context on mobile
  const isSecure = window.isSecureContext !== false;

  if (!navigator.geolocation || !isSecure) {
    const reason = !isSecure ? "Insecure HTTP context (LAN)" : "Geolocation unsupported";
    console.warn(`Geolocation unavailable: ${reason}. Activating fallback simulated telemetry.`);
    setGps(`GPS: SIMULATED (${reason})`);
    show(`${reason} — Using Corridor Demo Telemetry`, "error");

    let simLat = DEFAULT_LAT;
    let simLng = DEFAULT_LNG;
    let step = 0;

    simulatedTimer = setInterval(() => {
      step++;
      simLat += 0.00008 * Math.cos(step * 0.1);
      simLng += 0.00008 * Math.sin(step * 0.1);
      const fakePos = {
        coords: {
          latitude: simLat,
          longitude: simLng,
          accuracy: 5.0,
          speed: 11.5, // ~41 km/h
          heading: (step * 5) % 360,
        }
      };
      updateUI(fakePos);
    }, sendIntervalMs);

    connectWs();
    return;
  }

  watchId = navigator.geolocation.watchPosition(
    (pos) => {
      setGps("GPS: AVAILABLE");
      updateUI(pos);
    },
    (err) => {
      let msg = "GPS error";
      if (err.code === 1) {
        msg = "Permission denied / Insecure origin";
        console.warn("Geolocation permission denied; activating demo coordinates.");
        // Fallback to simulated coordinates so LAN testing does not halt
        if (!simulatedTimer) {
          updateUI({
            coords: {
              latitude: DEFAULT_LAT,
              longitude: DEFAULT_LNG,
              accuracy: 10,
              speed: 10,
              heading: 90
            }
          });
        }
      } else if (err.code === 2) {
        msg = "Position unavailable";
      } else if (err.code === 3) {
        msg = "Timeout";
      }
      setGps("GPS: " + msg.toUpperCase());
      show(msg, "error");
    },
    { enableHighAccuracy: true, maximumAge: 1000, timeout: 10000 }
  );

  connectWs();
}

function stopGps() {
  if (watchId !== null) {
    navigator.geolocation.clearWatch(watchId);
    watchId = null;
  }
  if (simulatedTimer !== null) {
    clearInterval(simulatedTimer);
    simulatedTimer = null;
  }
  if (ws) {
    try { ws.close(); } catch (e) {}
    ws = null;
  }
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
    ws.onopen = () => {
      setConn(true, "CONNECTED");
      show("Connected to backend");
    };
    ws.onclose = () => {
      setConn(false, "DISCONNECTED");
    };
    ws.onerror = () => {
      setConn(false, "ERROR");
      show("WebSocket error", "error");
    };
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
  $("backendHost").textContent = wsHost;
  sendIntervalMs = parseInt($("intervalSlider").value, 10);
  $("intervalLabel").textContent = sendIntervalMs + " ms";
  $("intervalValue").textContent = sendIntervalMs + " ms";

  // Initialize Leaflet Map immediately on page load
  initAmbulanceMap();
});
