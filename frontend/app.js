/**
 * Lane-Aware EVAS — Interactive Web Application Engine
 * Implements Driver HUD, Camera AI Neural Lane HUD, Junction Traffic Signal Controller,
 * Live Map (Leaflet) & FastAPI WebSocket/REST Integration.
 */

(() => {
  'use strict';

  // --- Utility Selector ---
  const $ = (id) => document.getElementById(id);

  // --- Application State ---
  const state = {
    currentTab: 'driver',
    operatingMode: 'NORMAL_VEHICLE',
    myVehicleId: 'V002',
    myAmbulanceId: 'AMB01',
    assignedAmbulanceLane: 'CENTER',
    myLane: 2,
    speedKmh: null,
    headingDeg: 0,
    myPosition: null, // Acquired from browser GPS if enabled
    originLocation: null,
    destinationLocation: null,
    activeRoutePoints: [],
    activeJourney: null,
    useBackend: true,
    isSoundEnabled: true,
    isVibrationEnabled: true,
    activeAlert: null,
    wsConnected: false,
    ws: null,
    wsReconnectTimer: null,
    wsMsgCount: 0,
    simTimer: null,
    isPlayingSim: false,
    isDemoModeActive: false,
    tileUrl: localStorage.getItem('evas_tile_url') || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    routingUrl: localStorage.getItem('evas_routing_url') || 'https://router.project-osrm.org',

    // Fleet state received from FastAPI backend (null/empty until valid telemetry arrives)
    ambulance: null,
    vehicles: {},
    junction: null,
    routeCorridor: null,

    // Camera AI State
    camera: {
      sourceType: 'physical_usb_camera_0',
      fps: 0,
      lane: null,
      confidence: null,
      offsetM: null,
      latencyMs: null,
      modelType: 'PyTorch TorchScript',
      lighting: 'NORMAL'
    }
  };

  // --- Sound Synthesizer (Web Audio API) ---
  let audioCtx = null;
  let sirenOsc = null;
  let sirenGain = null;
  let sirenModTimer = null;

  function initAudio() {
    if (!audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        audioCtx = new AudioContext();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
  }

  function startSirenSound() {
    if (!state.isSoundEnabled) return;
    initAudio();
    if (!audioCtx || sirenOsc) return;

    try {
      sirenOsc = audioCtx.createOscillator();
      sirenGain = audioCtx.createGain();

      sirenOsc.type = 'sawtooth';
      sirenGain.gain.setValueAtTime(0.15, audioCtx.currentTime);

      sirenOsc.connect(sirenGain);
      sirenGain.connect(audioCtx.destination);
      sirenOsc.start();

      let freqHigh = false;
      sirenModTimer = setInterval(() => {
        if (!sirenOsc || !audioCtx) return;
        const now = audioCtx.currentTime;
        const targetFreq = freqHigh ? 800 : 1200;
        sirenOsc.frequency.linearRampToValueAtTime(targetFreq, now + 0.4);
        freqHigh = !freqHigh;
      }, 400);
    } catch (e) {
      console.warn('Audio playback not permitted yet:', e);
    }
  }

  function stopSirenSound() {
    if (sirenModTimer) {
      clearInterval(sirenModTimer);
      sirenModTimer = null;
    }
    if (sirenOsc) {
      try {
        sirenOsc.stop();
        sirenOsc.disconnect();
      } catch (e) {}
      sirenOsc = null;
      sirenGain = null;
    }
  }

  function triggerVibration() {
    if (state.isVibrationEnabled && navigator.vibrate) {
      navigator.vibrate([300, 100, 300, 100, 500]);
    }
  }

  // --- Toast Notice ---
  function showToast(msg) {
    const toast = $('toastNotice');
    if (!toast) return;
    toast.textContent = msg;
    toast.style.display = 'block';
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => {
      toast.style.display = 'none';
    }, 2800);
  }

  // --- Geographic Coordinate Validation ---
  function isValidCoordinate(lat, lng) {
    if (typeof lat !== 'number' || typeof lng !== 'number') return false;
    if (isNaN(lat) || isNaN(lng)) return false;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return false;
    // Reject exact 0,0 null-island default error
    if (lat === 0 && lng === 0) return false;
    return true;
  }

  // --- Browser Real GPS Geolocation (Participant Mobile Tracking) ---
  let geoWatchId = null;
  function startBrowserGeolocation() {
    if (!navigator.geolocation) {
      if ($('hudGpsStatus')) $('hudGpsStatus').textContent = 'UNSUPPORTED';
      if ($('ambCurrentGpsLabel')) $('ambCurrentGpsLabel').textContent = 'Geolocation not supported by browser';
      return;
    }
    if (geoWatchId !== null) return;

    geoWatchId = navigator.geolocation.watchPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        if (isValidCoordinate(lat, lng)) {
          state.myPosition = { lat, lng };
          if (pos.coords.speed !== null && !isNaN(pos.coords.speed)) {
            state.speedKmh = Math.round(pos.coords.speed * 3.6);
          }
          if (pos.coords.heading !== null && !isNaN(pos.coords.heading)) {
            state.headingDeg = Math.round(pos.coords.heading);
          }

          if ($('hudGpsStatus')) {
            $('hudGpsStatus').textContent = `LOCKED (${lat.toFixed(4)}, ${lng.toFixed(4)})`;
            $('hudGpsStatus').style.color = '#4ade80';
          }
          if ($('ambCurrentGpsLabel')) {
            $('ambCurrentGpsLabel').textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)} (±${Math.round(pos.coords.accuracy || 5)}m)`;
          }

          if (state.operatingMode === 'AMBULANCE') {
            if (!state.ambulance) {
              state.ambulance = {
                id: state.myAmbulanceId || 'AMB01',
                lat: lat,
                lng: lng,
                speedKmh: state.speedKmh || 0,
                headingDeg: state.headingDeg || 0,
                lane: state.assignedAmbulanceLane || 'CENTER',
                emergency: Boolean(state.activeJourney && state.activeJourney.is_active)
              };
            } else {
              state.ambulance.lat = lat;
              state.ambulance.lng = lng;
              if (state.speedKmh !== null) state.ambulance.speedKmh = state.speedKmh;
              if (state.headingDeg !== null) state.ambulance.headingDeg = state.headingDeg;
            }
            if ($('ambSpeedVal')) $('ambSpeedVal').textContent = state.speedKmh !== null ? state.speedKmh : '0';
            if ($('ambHeadingVal')) $('ambHeadingVal').textContent = state.headingDeg !== null ? state.headingDeg : '0';
          } else {
            // Register or update ourselves in local vehicle registry
            if (!state.vehicles[state.myVehicleId]) {
              state.vehicles[state.myVehicleId] = {
                id: state.myVehicleId,
                lat: lat,
                lng: lng,
                speedKmh: state.speedKmh || 0,
                headingDeg: state.headingDeg || 0,
                lane: state.myLane
              };
            } else {
              state.vehicles[state.myVehicleId].lat = lat;
              state.vehicles[state.myVehicleId].lng = lng;
              if (state.speedKmh !== null) state.vehicles[state.myVehicleId].speedKmh = state.speedKmh;
              if (state.headingDeg !== null) state.vehicles[state.myVehicleId].headingDeg = state.headingDeg;
            }
          }
          renderHUD();
          updateMapMarkers();
          sendTelemetryToBackend();
        }
      },
      (err) => {
        console.debug('Browser geolocation status:', err.message);
        if ($('hudGpsStatus')) {
          $('hudGpsStatus').textContent = 'PERMISSION DENIED / UNAVAILABLE';
          $('hudGpsStatus').style.color = '#f87171';
        }
        if ($('ambCurrentGpsLabel')) {
          $('ambCurrentGpsLabel').textContent = 'GPS permission denied or unavailable';
        }
      },
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 }
    );
  }


  // --- Distance Math ---
  function haversineMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  // --- Alert Calculation & Test Mode Fallback ---
  function recalculateAlert() {
    // In live mode with backend active, the backend matching engine is the sole source of truth.
    if (state.useBackend && state.wsConnected) return;

    // Only evaluate client-side alert if a test demonstration scenario is explicitly active
    if (!state.isDemoModeActive || !state.ambulance || !state.vehicles[state.myVehicleId]) {
      if (!state.activeAlert) {
        renderHUD();
        updateMapMarkers();
      }
      return;
    }

    const myVeh = state.vehicles[state.myVehicleId];
    const amb = state.ambulance;
    if (!isValidCoordinate(amb.lat, amb.lng) || !isValidCoordinate(myVeh.lat, myVeh.lng)) return;

    const dist = haversineMeters(amb.lat, amb.lng, myVeh.lat, myVeh.lng);
    const isAhead = myVeh.lat > amb.lat;
    const isSameLane = myVeh.lane === amb.lane;

    if (amb.emergency && isAhead && isSameLane && dist <= 600) {
      const relSpeed = Math.max(((amb.speedKmh || 60) - (myVeh.speedKmh || 40)) * 1000 / 3600, 5.0);
      const eta = Math.max(1, Math.round(dist / relSpeed));

      state.activeAlert = {
        toId: state.myVehicleId,
        ambulanceId: amb.id || 'AMB01',
        distance: Math.round(dist),
        eta: eta,
        ambulanceLane: amb.lane || 2,
        emergencyState: true,
        humanMessage: 'Emergency vehicle approaching in your lane. Safely clear the path.'
      };
      startSirenSound();
      triggerVibration();
    } else {
      state.activeAlert = null;
      stopSirenSound();
    }

    renderHUD();
    updateMapMarkers();
  }

  function stepSimulation() {
    // Only advance simulated positions when an explicit test fixture is running
    if (!state.isPlayingSim || !state.isDemoModeActive) return;
    if (!state.ambulance) return;

    state.ambulance.lat += 0.00012;
    if (state.ambulance.lat > 12.9800) {
      state.ambulance.lat = 12.9716;
    }

    Object.values(state.vehicles).forEach(v => {
      v.lat += 0.00004;
      if (v.lat > 12.9820) v.lat = 12.9720;
    });

    recalculateAlert();
  }

  function toggleSimulationPlayback() {
    state.isPlayingSim = !state.isPlayingSim;
    const icon = $('playIcon');
    const txt = $('playText');

    if (state.isPlayingSim) {
      if (icon) icon.textContent = '⏸';
      if (txt) txt.textContent = 'Pause';
      showToast('Demonstration Step Playing');
      if (!state.simTimer) {
        state.simTimer = setInterval(stepSimulation, 1000);
      }
    } else {
      if (icon) icon.textContent = '▶';
      if (txt) txt.textContent = 'Play';
      showToast('Demonstration Step Paused');
      if (state.simTimer) {
        clearInterval(state.simTimer);
        state.simTimer = null;
      }
    }
  }

  function resetSimulationScenario() {
    if (state.simTimer) {
      clearInterval(state.simTimer);
      state.simTimer = null;
    }
    state.isPlayingSim = false;
    state.isDemoModeActive = false;

    // Reset state to empty live mode
    state.ambulance = null;
    state.vehicles = {};
    state.routeCorridor = null;
    state.activeAlert = null;
    stopSirenSound();

    if ($('hudModeBadge')) {
      $('hudModeBadge').textContent = 'LIVE';
      $('hudModeBadge').style.background = 'rgba(34, 197, 94, 0.15)';
      $('hudModeBadge').style.color = '#4ade80';
      $('hudModeBadge').style.borderColor = 'rgba(34, 197, 94, 0.3)';
    }
    if ($('demoSimControls')) $('demoSimControls').style.display = 'none';
    if ($('demoScenarioDetails')) $('demoScenarioDetails').style.display = 'none';

    renderHUD();
    updateMapMarkers();
    showToast('Reset to Live Backend Mode');
    pollBackendStatus();
  }

  // --- Lane Switching Logic ---
  function setMyLane(laneNum) {
    if (laneNum < 1) laneNum = 1;
    if (laneNum > 3) laneNum = 3;

    state.myLane = laneNum;
    if (state.vehicles[state.myVehicleId]) {
      state.vehicles[state.myVehicleId].lane = laneNum;
    }

    // Visual lane selection updates
    [1, 2, 3].forEach(n => {
      const seg = $(`lane${n}Btn`);
      const icon = $(`carIconL${n}`);
      if (seg) seg.classList.toggle('active-vehicle', n === laneNum);
      if (icon) icon.style.display = (n === laneNum) ? 'block' : 'none';
    });

    // Check if lane cleared
    if (state.activeAlert && state.myLane !== state.activeAlert.ambulanceLane) {
      showToast(`Lane cleared! Shifted safely to Lane ${laneNum}`);
      state.activeAlert = null;
      stopSirenSound();
    } else {
      showToast(`Switched to Lane ${laneNum}`);
    }

    // Sync with WebSocket backend if connected
    if (state.useBackend && state.ws && state.ws.readyState === WebSocket.OPEN) {
      sendTelemetryToBackend();
    }

    renderHUD();
    updateMapMarkers();
  }

  // --- WebSocket Connection Management ---
  function getWsBaseUrl() {
    const inputVal = $('wsUrlInput') ? $('wsUrlInput').value.trim() : '';
    if (inputVal) return inputVal;

    // Check for configured global environment variable or window config
    if (window.__EVAS_API_BASE_URL__) {
      return window.__EVAS_API_BASE_URL__.replace(/^http/, 'ws');
    }

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || 'localhost:8000';
    return `${proto}//${host}`;
  }

  function connectBackend() {
    const base = getWsBaseUrl();
    let url;
    if (state.operatingMode === 'AMBULANCE') {
      url = `${base}/ws/ambulance`;
    } else {
      url = `${base}/ws/vehicle/${state.myVehicleId}`;
    }

    showToast(`Connecting to ${url} ...`);
    $('wsStatusBadge').textContent = 'CONNECTING...';
    $('wsStatusBadge').style.color = 'var(--warning)';

    try {
      if (state.ws) {
        try { state.ws.close(); } catch (e) {}
        state.ws = null;
      }
      state.ws = new WebSocket(url);

      state.ws.onopen = () => {
        state.wsConnected = true;
        state.useBackend = true;
        $('backendToggle').checked = true;
        $('statusDot').style.backgroundColor = 'var(--safe)';
        $('statusDot').style.boxShadow = '0 0 8px var(--safe)';
        $('v2vStatusText').textContent = 'ONLINE';
        $('wsStatusBadge').textContent = 'CONNECTED';
        $('wsStatusBadge').style.color = 'var(--safe)';
        $('btnConnectWs').disabled = true;
        $('btnDisconnectWs').disabled = false;
        $('backendModeDesc').textContent = 'Live telemetry stream active';
        showToast('Connected to FastAPI Backend');

        // Immediately send vehicle state if coordinates are available
        sendTelemetryToBackend();
        pollBackendStatus();
      };

      state.ws.onmessage = (event) => {
        state.wsMsgCount++;
        $('wsMsgCount').textContent = state.wsMsgCount;
        try {
          const data = JSON.parse(event.data);
          handleBackendMessage(data);
        } catch (e) {
          console.error('Failed to parse backend message:', e);
        }
      };

      state.ws.onerror = (err) => {
        console.warn('WebSocket error:', err);
      };

      state.ws.onclose = () => {
        state.wsConnected = false;
        $('statusDot').style.backgroundColor = 'var(--text-muted)';
        $('statusDot').style.boxShadow = 'none';
        $('v2vStatusText').textContent = 'STANDALONE';
        $('wsStatusBadge').textContent = 'DISCONNECTED';
        $('wsStatusBadge').style.color = 'var(--text-muted)';
        $('btnConnectWs').disabled = false;
        $('btnDisconnectWs').disabled = true;
        updateMapTelemetryBanner();

        if (state.useBackend) {
          // Attempt auto-reconnect in 3s
          clearTimeout(state.wsReconnectTimer);
          state.wsReconnectTimer = setTimeout(() => {
            if (state.useBackend) connectBackend();
          }, 3000);
        }
      };
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
      showToast('WebSocket connection failed');
      updateMapTelemetryBanner();
    }
  }

  function disconnectBackend(userInitiated = false) {
    if (userInitiated) {
      state.useBackend = false;
      $('backendToggle').checked = false;
      $('backendModeDesc').textContent = 'Running standalone / disconnected';
    }
    clearTimeout(state.wsReconnectTimer);
    if (state.ws) {
      try { state.ws.close(); } catch (e) {}
      state.ws = null;
    }
    state.wsConnected = false;
    updateMapTelemetryBanner();
    showToast('Disconnected from Backend');
  }

  function sendTelemetryToBackend() {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;

    let lat = null;
    let lng = null;
    if (state.myPosition && isValidCoordinate(state.myPosition.lat, state.myPosition.lng)) {
      lat = state.myPosition.lat;
      lng = state.myPosition.lng;
    } else if (state.operatingMode === 'AMBULANCE' && state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
      lat = state.ambulance.lat;
      lng = state.ambulance.lng;
    } else if (state.vehicles[state.myVehicleId] && isValidCoordinate(state.vehicles[state.myVehicleId].lat, state.vehicles[state.myVehicleId].lng)) {
      lat = state.vehicles[state.myVehicleId].lat;
      lng = state.vehicles[state.myVehicleId].lng;
    }

    // Do not transmit fabricated coordinates if position has not been acquired
    if (!isValidCoordinate(lat, lng)) {
      return;
    }

    let payload;
    if (state.operatingMode === 'AMBULANCE') {
      payload = {
        type: 'telemetry',
        ambulance_id: state.myAmbulanceId || 'AMB01',
        lat: lat,
        lng: lng,
        speed_kmh: (state.speedKmh !== null && state.speedKmh !== undefined) ? state.speedKmh : 0.0,
        heading_deg: state.headingDeg || 0.0,
        emergency: Boolean(state.activeJourney && state.activeJourney.is_active),
        lane: state.assignedAmbulanceLane || 'CENTER',
        ts: Date.now() / 1000.0
      };
    } else {
      payload = {
        type: 'telemetry',
        vehicle_id: state.myVehicleId,
        lat: lat,
        lng: lng,
        speed_kmh: (state.speedKmh !== null && state.speedKmh !== undefined) ? state.speedKmh : 0.0,
        heading_deg: state.headingDeg || 0.0,
        lane: String(state.myLane),
        lane_confidence: (state.camera && state.camera.confidence !== null) ? state.camera.confidence : 0.95,
        ts: Date.now() / 1000.0
      };
    }

    try {
      state.ws.send(JSON.stringify(payload));
    } catch (e) {
      console.error('Failed to send telemetry:', e);
    }
  }

  function handleBackendMessage(data) {
    if (!data) return;

    // 1. Emergency Alert Target
    if (data.type === 'emergency_alert' || (data.to_id === state.myVehicleId && data.emergency_state === true)) {
      state.activeAlert = {
        toId: data.to_id,
        ambulanceId: data.ambulance_id || 'AMB01',
        distance: Math.round(data.distance || 0),
        eta: Math.round(data.eta || 0),
        ambulanceLane: data.ambulance_lane || 2,
        emergencyState: true,
        humanMessage: data.human_message || 'Emergency vehicle approaching in your lane.'
      };

      if (isValidCoordinate(data.ambulance_lat, data.ambulance_lon)) {
        if (!state.ambulance) {
          state.ambulance = {
            id: data.ambulance_id || 'AMB01',
            lat: data.ambulance_lat,
            lng: data.ambulance_lon,
            speedKmh: 60,
            headingDeg: 0,
            emergency: true,
            lane: data.ambulance_lane || 2
          };
        } else {
          state.ambulance.lat = data.ambulance_lat;
          state.ambulance.lng = data.ambulance_lon;
          state.ambulance.emergency = true;
          state.ambulance.lane = data.ambulance_lane || 2;
        }
      }

      startSirenSound();
      triggerVibration();
      renderHUD();
      updateMapMarkers();
      return;
    }

    // 2. Emergency Clearance
    if (data.type === 'emergency_clear' || (data.to_id === state.myVehicleId && data.emergency_state === false)) {
      state.activeAlert = null;
      stopSirenSound();
      renderHUD();
      updateMapMarkers();
      return;
    }

    // 3. Fleet & Junction Update
    if (data.type === 'fleet_update') {
      // Ambulance telemetry
      if (data.ambulance && isValidCoordinate(data.ambulance.lat, data.ambulance.lng)) {
        state.ambulance = {
          id: data.ambulance.id || 'AMB01',
          lat: data.ambulance.lat,
          lng: data.ambulance.lng,
          speedKmh: data.ambulance.speed_kmh || 0,
          headingDeg: data.ambulance.heading_deg || 0,
          lane: data.ambulance.lane || 2,
          emergency: data.ambulance.emergency ?? true
        };
      } else if (data.ambulance === null && !state.isDemoModeActive) {
        state.ambulance = null;
      }

      // Participating vehicles
      if (data.vehicles && typeof data.vehicles === 'object') {
        const freshVehicles = {};
        Object.entries(data.vehicles).forEach(([id, v]) => {
          if (v && isValidCoordinate(v.lat, v.lng)) {
            freshVehicles[id] = {
              id: id,
              lat: v.lat,
              lng: v.lng,
              speedKmh: v.speed_kmh || 0,
              headingDeg: v.heading_deg || 0,
              lane: v.lane !== undefined ? Number(v.lane) : 2
            };
          }
        });
        // Retain own phone GPS position if available
        if (state.myPosition && isValidCoordinate(state.myPosition.lat, state.myPosition.lng)) {
          freshVehicles[state.myVehicleId] = {
            id: state.myVehicleId,
            lat: state.myPosition.lat,
            lng: state.myPosition.lng,
            speedKmh: state.speedKmh || 0,
            headingDeg: state.headingDeg || 0,
            lane: state.myLane
          };
        }
        state.vehicles = freshVehicles;
      }

      // Junction signals
      if (data.junctions && data.junctions['JUNC_01']) {
        updateJunctionUI(data.junctions['JUNC_01']);
      }

      // Active Journey sync from backend
      if (data.active_journey !== undefined) {
        updateAmbulanceJourneyUI(data.active_journey);
      }

      // Route / Corridor geometry
      if (data.route && Array.isArray(data.route)) {
        state.routeCorridor = data.route;
      } else if (data.corridor && Array.isArray(data.corridor)) {
        state.routeCorridor = data.corridor;
      }

      renderHUD();
      updateMapMarkers();
      updateMapCorridor();
    }
  }

  // --- UI Rendering ---
  function renderHUD() {
    const hasAlert = !!state.activeAlert;
    const banner = $('alertBanner');
    const badge = $('navAlertBadge');
    const laneBadge = $('laneStatusBadge');
    const metrics = $('emergencyMetrics');
    const clearActions = $('clearActions');

    // 1. Alert Banner
    if (hasAlert) {
      banner.className = 'alert-banner emergency';
      $('alertTitle').textContent = 'Emergency Vehicle Approaching';
      $('alertSubtitle').textContent = state.activeAlert.humanMessage || 'Approaching behind in your lane';
      $('alertIcon').setAttribute('fill', '#EF4444');
      $('alertDistanceVal').textContent = `${state.activeAlert.distance} m`;
      $('alertEtaVal').textContent = `${state.activeAlert.eta} s`;
      $('alertAmbLaneVal').textContent = `L${state.activeAlert.ambulanceLane}`;

      metrics.style.display = 'grid';
      clearActions.style.display = 'flex';
      badge.classList.add('visible');
      laneBadge.className = 'lane-status-badge danger';
      laneBadge.textContent = 'SAME LANE';

      $('ambDistVal').textContent = state.activeAlert.distance;
      $('ambDistUnit').textContent = 'm';
      $('distIconBox').style.color = 'var(--emergency)';
    } else {
      banner.className = 'alert-banner safe';
      const isAmbEmergency = state.ambulance && state.ambulance.emergency;
      const hasActiveJourney = state.activeJourney && state.activeJourney.is_active;

      if (hasActiveJourney && isAmbEmergency) {
        $('alertTitle').textContent = 'Path is Clear';
        $('alertSubtitle').textContent = 'Emergency vehicle active in adjacent corridor.';
      } else if (hasActiveJourney) {
        $('alertTitle').textContent = 'Ambulance on Standby';
        $('alertSubtitle').textContent = 'Ambulance journey active in non-emergency standby.';
      } else {
        $('alertTitle').textContent = 'No active ambulance journey.';
        $('alertSubtitle').textContent = 'No emergency vehicle route corridor currently active.';
      }
      $('alertIcon').setAttribute('fill', '#22C55E');

      metrics.style.display = 'none';
      clearActions.style.display = 'none';
      badge.classList.remove('visible');
      laneBadge.className = 'lane-status-badge safe';
      laneBadge.textContent = 'CLEAR';

      // Distance to ambulance
      const myVeh = state.vehicles[state.myVehicleId] || state.myPosition;
      if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng) && myVeh && isValidCoordinate(myVeh.lat, myVeh.lng)) {
        const d = Math.round(haversineMeters(state.ambulance.lat, state.ambulance.lng, myVeh.lat, myVeh.lng));
        $('ambDistVal').textContent = d;
        $('ambDistUnit').textContent = 'm';
        $('distIconBox').style.color = 'var(--accent-cyan)';
      } else {
        $('ambDistVal').textContent = '—';
        $('ambDistUnit').textContent = '';
        $('distIconBox').style.color = 'var(--text-muted)';
      }
    }

    // Vehicle Speed Display
    if ($('speedVal')) {
      $('speedVal').textContent = (state.speedKmh !== null && state.speedKmh !== undefined) ? state.speedKmh : '—';
    }

    // 2. Ambulance Lane Beacon on Road lanes
    const ambEmergency = state.ambulance && state.ambulance.emergency;
    const ambLane = state.ambulance ? (state.ambulance.lane || 2) : 0;
    [1, 2, 3].forEach(n => {
      const beacon = $(`beaconLane${n}`);
      if (beacon) {
        beacon.style.display = (ambEmergency && n === ambLane) ? 'block' : 'none';
      }
    });

    // 3. Upcoming Junction HUD card
    if (state.junction && isValidCoordinate(state.junction.lat, state.junction.lng)) {
      $('hudJunctionCard').style.display = 'block';
      $('hudJuncStatusBadge').textContent = state.junction.currentState || 'NORMAL_CYCLE';

      if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
        const distToJunc = Math.round(haversineMeters(state.ambulance.lat, state.ambulance.lng, state.junction.lat, state.junction.lng));
        const speedMs = Math.max(5.0, ((state.ambulance.speedKmh || 50) * 1000) / 3600);
        const etaToJunc = Math.max(0, Math.round(distToJunc / speedMs));
        $('hudJuncEta').textContent = `${etaToJunc} s`;
      } else {
        $('hudJuncEta').textContent = '—';
      }

      $('hudJuncPriority').textContent = state.junction.priorityActive
        ? 'PRIORITY HOLD'
        : (state.junction.currentState === 'PRIORITY_TRANSITION' ? 'TRANSITION' : 'IDLE');

      const aLights = (state.junction.lights && state.junction.lights.approach_a) || {};
      $('hudLampRed').className = `mini-lamp red ${aLights.red ? 'on' : ''}`;
      $('hudLampYellow').className = `mini-lamp yellow ${aLights.yellow ? 'on' : ''}`;
      $('hudLampGreen').className = `mini-lamp green ${aLights.green ? 'on' : ''}`;
    } else {
      $('hudJuncEta').textContent = '—';
      $('hudJuncPriority').textContent = 'IDLE';
    }

    // 4. Update HUD Status fields (Normal Vehicle)
    const myVeh = state.vehicles[state.myVehicleId] || state.myPosition;
    if ($('hudGpsCoords')) {
      if (myVeh && isValidCoordinate(myVeh.lat, myVeh.lng)) {
        $('hudGpsCoords').textContent = `${myVeh.lat.toFixed(5)}, ${myVeh.lng.toFixed(5)}`;
        $('hudGpsCoords').style.color = '#4ADE80';
      } else {
        $('hudGpsCoords').textContent = 'Waiting for GPS fix...';
        $('hudGpsCoords').style.color = 'var(--text-muted)';
      }
    }
    if ($('hudGpsStatus')) {
      if (myVeh && isValidCoordinate(myVeh.lat, myVeh.lng)) {
        $('hudGpsStatus').textContent = state.isDemoModeActive ? 'SIMULATED GPS' : 'LIVE GPS FIX';
        $('hudGpsStatus').style.color = '#4ADE80';
      } else {
        $('hudGpsStatus').textContent = 'WAITING FOR DATA';
        $('hudGpsStatus').style.color = 'var(--text-muted)';
      }
    }
    if ($('hudCamStatus')) {
      $('hudCamStatus').textContent = state.cameraEnabled ? 'CONNECTED (PHOTO 5s)' : 'STANDBY';
      $('hudCamStatus').style.color = state.cameraEnabled ? '#4ADE80' : 'var(--text-muted)';
    }
    if ($('hudConnStatus')) {
      $('hudConnStatus').textContent = state.wsConnected ? 'WEBSOCKET ONLINE' : 'DISCONNECTED';
      $('hudConnStatus').style.color = state.wsConnected ? '#4ADE80' : '#F87171';
    }
    if ($('hudLastUpdate')) {
      $('hudLastUpdate').textContent = new Date().toLocaleTimeString();
    }

    // 5. Update Ambulance Console Status fields
    if ($('ambConnStatus')) {
      $('ambConnStatus').textContent = state.wsConnected ? 'WEBSOCKET ONLINE' : 'DISCONNECTED';
      $('ambConnStatus').style.color = state.wsConnected ? '#4ADE80' : '#F87171';
    }
    if ($('ambLastUpdate')) {
      $('ambLastUpdate').textContent = new Date().toLocaleTimeString();
    }
    if ($('ambGpsCoords')) {
      if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
        const isStale = state.ambulance.ts && (Date.now() / 1000 - state.ambulance.ts > 20);
        $('ambGpsCoords').textContent = `${state.ambulance.lat.toFixed(5)}, ${state.ambulance.lng.toFixed(5)} ${isStale ? '[STALE >20s]' : ''}`;
        $('ambGpsCoords').style.color = isStale ? '#F59E0B' : '#38BDF8';
      } else {
        $('ambGpsCoords').textContent = 'Waiting for valid GPS signal...';
        $('ambGpsCoords').style.color = 'var(--text-muted)';
      }
    }
    if ($('ambCurrentLaneLabel')) {
      const lane = state.assignedAmbulanceLane || 'CENTER';
      const laneNum = lane === 'LEFT' ? 1 : (lane === 'CENTER' ? 2 : 3);
      $('ambCurrentLaneLabel').textContent = `${lane} (L${laneNum})`;
    }
  }

  // --- Junction Signal Controller UI ---
  function updateJunctionUI(jData) {
    if (!jData) return;
    if (!state.junction) {
      state.junction = {
        id: jData.junction_id || 'JUNC_01',
        lat: jData.lat || 12.9740,
        lng: jData.lng || 77.5950,
        currentState: 'NORMAL_CYCLE',
        priorityActive: false,
        hardwareMode: 'SIMULATED',
        lights: {
          approach_a: { red: false, yellow: false, green: true },
          approach_b: { red: true, yellow: false, green: false }
        }
      };
    }

    state.junction.currentState = jData.current_state || state.junction.currentState;
    state.junction.priorityActive = jData.priority_active ?? state.junction.priorityActive;
    state.junction.hardwareMode = jData.hardware_mode || state.junction.hardwareMode;
    state.junction.lights = jData.lights || state.junction.lights;
    if (jData.lat && jData.lng && isValidCoordinate(jData.lat, jData.lng)) {
      state.junction.lat = jData.lat;
      state.junction.lng = jData.lng;
    }

    // Hardware badge
    const hwBadge = $('esp32HwBadge');
    if (hwBadge) {
      if (state.junction.hardwareMode === 'PHYSICAL_ESP32') {
        hwBadge.className = 'badge-pill active';
        hwBadge.textContent = 'ESP32: CONNECTED';
      } else {
        hwBadge.className = 'badge-pill';
        hwBadge.textContent = 'AUTONOMOUS SIMULATION';
      }
    }

    // Sequence state pill
    if ($('juncStatePill')) $('juncStatePill').textContent = state.junction.currentState;
    if ($('juncStateDesc')) {
      if (state.junction.currentState === 'PRIORITY_HOLD') {
        $('juncStateDesc').textContent = 'EMERGENCY PREEMPTION ACTIVE • Approach A Green';
      } else if (state.junction.currentState === 'ALL_RED') {
        $('juncStateDesc').textContent = 'Safety clearance interval • Both approaches Red';
      } else if (state.junction.currentState === 'PRIORITY_TRANSITION') {
        $('juncStateDesc').textContent = 'Preempting Approach B • Yellow change interval';
      } else {
        $('juncStateDesc').textContent = 'Autonomous fixed-time cycle active';
      }
    }

    // Physical LED Signal Lamps (Approach A)
    const lA = (state.junction.lights && state.junction.lights.approach_a) || {};
    if ($('sigARed')) $('sigARed').className = `signal-lamp red ${lA.red ? 'on' : ''}`;
    if ($('sigAYellow')) $('sigAYellow').className = `signal-lamp yellow ${lA.yellow ? 'on' : ''}`;
    if ($('sigAGreen')) $('sigAGreen').className = `signal-lamp green ${lA.green ? 'on' : ''}`;
    if ($('labelAppA')) {
      $('labelAppA').textContent = lA.green ? 'GREEN (CLEARANCE)' : (lA.yellow ? 'AMBER / CAUTION' : 'RED / STOP');
      $('labelAppA').style.color = lA.green ? 'var(--safe)' : (lA.yellow ? 'var(--warning)' : 'var(--emergency)');
    }

    // Physical LED Signal Lamps (Approach B)
    const lB = (state.junction.lights && state.junction.lights.approach_b) || {};
    if ($('sigBRed')) $('sigBRed').className = `signal-lamp red ${lB.red ? 'on' : ''}`;
    if ($('sigBYellow')) $('sigBYellow').className = `signal-lamp yellow ${lB.yellow ? 'on' : ''}`;
    if ($('sigBGreen')) $('sigBGreen').className = `signal-lamp green ${lB.green ? 'on' : ''}`;
    if ($('labelAppB')) {
      $('labelAppB').textContent = lB.green ? 'GREEN (CROSS-TRAFFIC)' : (lB.yellow ? 'AMBER / CAUTION' : 'RED / STOP');
      $('labelAppB').style.color = lB.green ? 'var(--safe)' : (lB.yellow ? 'var(--warning)' : 'var(--emergency)');
    }

    // Distance and ETA (only calculated when both positions are valid)
    if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng) && isValidCoordinate(state.junction.lat, state.junction.lng)) {
      const distToJunc = Math.round(haversineMeters(state.ambulance.lat, state.ambulance.lng, state.junction.lat, state.junction.lng));
      const speedMs = Math.max(5.0, ((state.ambulance.speedKmh || 50) * 1000) / 3600);
      const etaToJunc = Math.max(0, Math.round(distToJunc / speedMs));
      if ($('juncDistVal')) $('juncDistVal').textContent = `${distToJunc} m`;
      if ($('juncEtaVal')) $('juncEtaVal').textContent = `${etaToJunc} s`;
    } else {
      if ($('juncDistVal')) $('juncDistVal').textContent = '— m';
      if ($('juncEtaVal')) $('juncEtaVal').textContent = '— s';
    }

    const pBadge = $('priorityStatusBadge');
    if (pBadge) {
      if (state.junction.priorityActive) {
        pBadge.className = 'badge-pill active';
        pBadge.textContent = 'PRIORITY_HOLD ACTIVE';
      } else if (state.junction.currentState === 'PRIORITY_TRANSITION') {
        pBadge.className = 'badge-pill active';
        pBadge.textContent = 'PRIORITY TRANSITION';
      } else {
        pBadge.className = 'badge-pill';
        pBadge.textContent = 'IDLE';
      }
    }

    // Sync Ambulance Junction Card
    if ($('ambJuncStatusBadge')) $('ambJuncStatusBadge').textContent = state.junction.currentState || 'NORMAL_CYCLE';
    const ambLamps = (state.junction.lights && state.junction.lights.approach_a) || {};
    if ($('ambLampRed')) $('ambLampRed').className = `mini-lamp red ${ambLamps.red ? 'on' : ''}`;
    if ($('ambLampYellow')) $('ambLampYellow').className = `mini-lamp yellow ${ambLamps.yellow ? 'on' : ''}`;
    if ($('ambLampGreen')) $('ambLampGreen').className = `mini-lamp green ${ambLamps.green ? 'on' : ''}`;

    if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng) && isValidCoordinate(state.junction.lat, state.junction.lng)) {
      const distToJunc = Math.round(haversineMeters(state.ambulance.lat, state.ambulance.lng, state.junction.lat, state.junction.lng));
      const speedMs = Math.max(5.0, ((state.ambulance.speedKmh || 50) * 1000) / 3600);
      const etaToJunc = Math.max(0, Math.round(distToJunc / speedMs));
      if ($('ambJuncEta')) $('ambJuncEta').textContent = `${etaToJunc} s`;
    } else {
      if ($('ambJuncEta')) $('ambJuncEta').textContent = '—';
    }

    if ($('ambJuncPriority')) {
      $('ambJuncPriority').textContent = state.junction.priorityActive
        ? 'PRIORITY HOLD'
        : (state.junction.currentState === 'PRIORITY_TRANSITION' ? 'TRANSITION' : 'IDLE');
    }
  }

  // --- Camera AI Telemetry & Stream Ingestion ---
  let cameraPollTimer = null;

  async function pollCameraTelemetry() {
    try {
      const res = await fetch('/api/camera/status');
      if (!res.ok) return;
      const data = await res.json();

      const isEnabled = Boolean(data.camera_enabled);
      state.cameraEnabled = isEnabled;

      // Update Power Badge & Buttons
      if ($('cameraAccessPill')) {
        if (!isEnabled) {
          $('cameraAccessPill').textContent = 'ACCESS: DISABLED (OFF)';
          $('cameraAccessPill').style.background = 'rgba(239, 68, 68, 0.2)';
          $('cameraAccessPill').style.color = '#f87171';
          $('cameraAccessPill').style.borderColor = 'rgba(239, 68, 68, 0.4)';
        } else if (data.camera_status === 'CAMERA_UNAVAILABLE') {
          $('cameraAccessPill').textContent = 'CAMERA UNAVAILABLE';
          $('cameraAccessPill').style.background = 'rgba(239, 68, 68, 0.2)';
          $('cameraAccessPill').style.color = '#f87171';
          $('cameraAccessPill').style.borderColor = 'rgba(239, 68, 68, 0.4)';
        } else {
          $('cameraAccessPill').textContent = 'ACCESS: ACTIVE (PHOTO 5s)';
          $('cameraAccessPill').style.background = 'rgba(34, 197, 94, 0.2)';
          $('cameraAccessPill').style.color = '#4ade80';
          $('cameraAccessPill').style.borderColor = 'rgba(34, 197, 94, 0.4)';
        }
      }

      if ($('btnCameraTurnOn') && $('btnCameraTurnOff')) {
        if (isEnabled) {
          $('btnCameraTurnOn').classList.add('active');
          $('btnCameraTurnOff').classList.remove('active');
        } else {
          $('btnCameraTurnOff').classList.add('active');
          $('btnCameraTurnOn').classList.remove('active');
        }
      }

      if ($('cameraAccessStatusText')) {
        if (!isEnabled) {
          $('cameraAccessStatusText').innerHTML = 'Camera access is <strong>DISABLED</strong>. Camera hardware is completely stopped.';
        } else if (data.camera_status === 'CAMERA_UNAVAILABLE') {
          $('cameraAccessStatusText').innerHTML = '<span style="color: #f87171;"><strong>CAMERA_UNAVAILABLE:</strong> No physical camera detected. Real frames required; no synthetic frames fabricated in live mode.</span>';
        } else {
          $('cameraAccessStatusText').innerHTML = 'Vehicle camera captures <strong>1 still photo every 5s</strong> for ML lane inference. Video recording/streaming strictly disabled.';
        }
      }

      if ($('cameraSourceBadge')) {
        $('cameraSourceBadge').textContent = isEnabled
          ? (data.source_type ? data.source_type.toUpperCase() : 'UNKNOWN')
          : 'OFFLINE';
      }
      if ($('cameraFpsPill')) {
        if (!isEnabled) {
          $('cameraFpsPill').textContent = 'OFF';
        } else if (data.next_capture_in_s !== undefined && data.next_capture_in_s !== null) {
          $('cameraFpsPill').textContent = `NEXT PHOTO: ${data.next_capture_in_s.toFixed(1)}s`;
        } else {
          $('cameraFpsPill').textContent = 'STILL PHOTO (5s)';
        }
      }
      if ($('retentionToggle') && data.diagnostic_retention !== undefined) {
        $('retentionToggle').checked = Boolean(data.diagnostic_retention);
      }
      if ($('camCaptureStatus')) {
        $('camCaptureStatus').textContent = data.last_capture_status === 'SUCCESS'
          ? `SUCCESS (${(data.inference_latency_ms || 0).toFixed(1)} ms)`
          : (data.camera_status || 'IDLE');
        $('camCaptureStatus').style.color = data.last_capture_status === 'SUCCESS' ? 'var(--safe)' : 'var(--warning)';
      }
      if ($('camLastCaptureTime')) {
        $('camLastCaptureTime').textContent = data.last_capture_time
          ? new Date(data.last_capture_time * 1000).toLocaleTimeString()
          : '—';
      }
      if ($('camModelBadge')) {
        $('camModelBadge').textContent = data.model_type === 'pytorch_lane_net' ? 'PyTorch CNN (LaneFeatureNet)' : 'Classical CV';
      }
      if ($('camLaneVal')) {
        const hasValidLane = isEnabled && data.lane && data.lane !== 'UNKNOWN' && (data.lane_confidence || 0) >= 0.45;
        $('camLaneVal').textContent = isEnabled ? (hasValidLane ? data.lane : 'Lane not detected') : 'STANDBY';
        $('camLaneVal').style.color = hasValidLane ? (data.lane === 'CENTER' ? 'var(--safe)' : 'var(--warning)') : 'var(--text-muted)';
      }
      if ($('camConfVal')) {
        $('camConfVal').textContent = isEnabled ? `${Math.round((data.lane_confidence || 0) * 100)}%` : '—';
      }
      if ($('camOffsetVal')) {
        const off = data.lateral_offset_m || 0.0;
        $('camOffsetVal').textContent = isEnabled ? `${off >= 0 ? '+' : ''}${off} m` : '—';
      }
      if ($('camLatencyVal')) {
        $('camLatencyVal').textContent = isEnabled ? `${data.inference_latency_ms || 0.0} ms` : '—';
      }
      if ($('camLightVal')) {
        $('camLightVal').textContent = isEnabled ? (data.lighting_condition || 'NORMAL') : 'STANDBY';
      }

      // Refresh camera preview snapshot
      if (state.currentTab === 'camera') {
        const feed = $('cameraLiveFeed');
        if (feed) {
          if (isEnabled) {
            feed.src = `/api/camera/preview?t=${Date.now()}`;
          } else {
            feed.src = '/api/camera/preview';
          }
        }
      }
    } catch (e) {}
  }

  // ==========================================================================
  // OPENSTREETMAP + LEAFLET INTERACTIVE MAP & OSRM ROUTE ENGINE (PHASES 2, 4)
  // ==========================================================================
  let leafletMap = null;
  let tileLayer = null;
  let ambMarker = null;
  let myVehicleMarker = null;
  let destMarker = null;
  let junctionMarker = null;
  let vehicleMarkers = {};
  let corridorPolyline = null;
  let isMapInitializing = false;

    function attachMapToCurrentView() {
    const mapWrapper = $('mapSharedWrapper');
    if (!mapWrapper) return;

    let targetSlot = null;
    if (state.currentTab === 'map') {
      targetSlot = $('tabMapSlot');
    } else if (state.currentTab === 'driver') {
      if (state.operatingMode === 'AMBULANCE') {
        targetSlot = $('ambulanceMapSlot');
      } else {
        targetSlot = $('vehicleMapSlot');
      }
    }

    if (targetSlot && mapWrapper.parentElement !== targetSlot) {
      targetSlot.appendChild(mapWrapper);
    }

    if (leafletMap) {
      setTimeout(() => {
        leafletMap.invalidateSize(true);
      }, 50);
    }
  }

  function initLeafletMap() {
    if (leafletMap || isMapInitializing) return;
    if (!window.L || !window.L.map) {
      setTimeout(initLeafletMap, 150);
      return;
    }

    const mapElem = $('map');
    if (!mapElem) return;

    isMapInitializing = true;
    try {
      let initialCenter = [12.9716, 77.5946];
      let initialZoom = 15;

      if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
        initialCenter = [state.ambulance.lat, state.ambulance.lng];
        initialZoom = 16;
      } else if (state.myPosition && isValidCoordinate(state.myPosition.lat, state.myPosition.lng)) {
        initialCenter = [state.myPosition.lat, state.myPosition.lng];
        initialZoom = 16;
      }

      leafletMap = L.map('map', {
        zoomControl: true,
        attributionControl: true,
      }).setView(initialCenter, initialZoom);

      tileLayer = L.tileLayer(state.tileUrl, {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors',
      }).addTo(leafletMap);

      tileLayer.on('tileerror', (err) => {
        console.warn('Map tile unavailable from provider:', err);
      });

      updateMapMarkers();
      updateMapCorridor();
      attachMapToCurrentView();
    } catch (err) {
      console.error('Error initializing Leaflet map:', err);
    } finally {
      isMapInitializing = false;
    }
  }

  function getLeafletAmbulanceIcon() {
    return L.divIcon({
      className: 'custom-leaflet-marker',
      html: `<div style="display:flex;align-items:center;justify-content:center;width:44px;height:44px;background:#EF4444;border:3px solid #FFFFFF;border-radius:50%;box-shadow:0 0 16px rgba(239,68,68,0.8);font-size:22px;cursor:pointer;">🚑</div>`,
      iconSize: [44, 44],
      iconAnchor: [22, 22]
    });
  }

  function getLeafletVehicleIcon(isTarget, label = '🚗') {
    const bg = isTarget ? '#6366F1' : '#0284C7';
    const border = isTarget ? '#A5B4FC' : '#FFFFFF';
    return L.divIcon({
      className: 'custom-leaflet-marker',
      html: `<div style="display:flex;align-items:center;justify-content:center;width:38px;height:38px;background:${bg};border:2.5px solid ${border};border-radius:50%;box-shadow:0 0 12px ${bg};font-size:18px;cursor:pointer;">${label}</div>`,
      iconSize: [38, 38],
      iconAnchor: [19, 19]
    });
  }

  function getLeafletDestIcon() {
    return L.divIcon({
      className: 'custom-leaflet-marker',
      html: `<div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;background:#F59E0B;border:2.5px solid #FFFFFF;border-radius:50%;box-shadow:0 0 14px rgba(245,158,11,0.7);font-size:20px;cursor:pointer;">🏥</div>`,
      iconSize: [40, 40],
      iconAnchor: [20, 20]
    });
  }

  function getLeafletJunctionIcon(isPriority) {
    const lamp = isPriority ? '#22C55E' : '#EF4444';
    return L.divIcon({
      className: 'custom-leaflet-marker',
      html: `<div style="display:flex;align-items:center;justify-content:center;width:34px;height:34px;background:#18181B;border:2.5px solid ${lamp};border-radius:8px;box-shadow:0 0 10px ${lamp};font-size:16px;cursor:pointer;">🚦</div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17]
    });
  }

  function updateMapMarkers() {
    if (!leafletMap) return;

    // 1. Ambulance Marker
    if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
      const ambPos = [state.ambulance.lat, state.ambulance.lng];
      const isStale = state.ambulance.ts && (Date.now() / 1000 - state.ambulance.ts > 20);
      const ambTooltip = `<b>Ambulance ${state.ambulance.id || 'AMB01'}</b><br>Mode: ${state.ambulance.emergency ? '🚨 EMERGENCY' : 'STANDBY'}<br>Lane: ${state.ambulance.lane || 2} ${isStale ? '<br><span style="color:#F59E0B">⚠️ STALE GPS (>20s)</span>' : ''}`;

      if (!ambMarker) {
        ambMarker = L.marker(ambPos, { icon: getLeafletAmbulanceIcon(), zIndexOffset: 1000 }).addTo(leafletMap);
        ambMarker.bindTooltip(ambTooltip);
      } else {
        ambMarker.setLatLng(ambPos);
        ambMarker.setTooltipContent(ambTooltip);
      }
    } else if (ambMarker) {
      leafletMap.removeLayer(ambMarker);
      ambMarker = null;
    }

    // 2. Destination Marker (from active journey or preview)
    let destLat = null;
    let destLng = null;
    let destName = 'Destination';
    if (state.activeJourney && isValidCoordinate(state.activeJourney.destination_lat, state.activeJourney.destination_lng)) {
      destLat = state.activeJourney.destination_lat;
      destLng = state.activeJourney.destination_lng;
      destName = state.activeJourney.destination_name || 'Hospital Destination';
    } else if (state.destinationLocation && isValidCoordinate(state.destinationLocation.lat, state.destinationLocation.lng)) {
      destLat = state.destinationLocation.lat;
      destLng = state.destinationLocation.lng;
      destName = state.destinationLocation.name || 'Selected Destination';
    } else if (state.activeRoutePoints.length >= 2) {
      const last = state.activeRoutePoints[state.activeRoutePoints.length - 1];
      destLat = last.lat;
      destLng = last.lng;
    }

    if (isValidCoordinate(destLat, destLng)) {
      if (!destMarker) {
        destMarker = L.marker([destLat, destLng], { icon: getLeafletDestIcon(), zIndexOffset: 900 }).addTo(leafletMap);
        destMarker.bindTooltip(`<b>🏥 ${destName}</b>`);
      } else {
        destMarker.setLatLng([destLat, destLng]);
        destMarker.setTooltipContent(`<b>🏥 ${destName}</b>`);
      }
    } else if (destMarker) {
      leafletMap.removeLayer(destMarker);
      destMarker = null;
    }

    // 3. Participant Vehicle Marker
    const myVeh = state.vehicles[state.myVehicleId] || state.myPosition;
    if (myVeh && isValidCoordinate(myVeh.lat, myVeh.lng)) {
      const myPos = [myVeh.lat, myVeh.lng];
      const isTarget = !!state.activeAlert;
      const myTooltip = `<b>Your Vehicle (${state.myVehicleId})</b><br>Lane: ${state.myLane}<br>${isTarget ? '⚠️ IN AMBULANCE CORRIDOR' : 'Path Clear'}`;

      if (!myVehicleMarker) {
        myVehicleMarker = L.marker(myPos, { icon: getLeafletVehicleIcon(true, '🚗'), zIndexOffset: 950 }).addTo(leafletMap);
        myVehicleMarker.bindTooltip(myTooltip);
      } else {
        myVehicleMarker.setLatLng(myPos);
        myVehicleMarker.setIcon(getLeafletVehicleIcon(isTarget, '🚗'));
        myVehicleMarker.setTooltipContent(myTooltip);
      }
    } else if (myVehicleMarker) {
      leafletMap.removeLayer(myVehicleMarker);
      myVehicleMarker = null;
    }

    // 4. Other Connected Vehicles
    const activeVids = new Set();
    Object.entries(state.vehicles).forEach(([vid, v]) => {
      if (vid === state.myVehicleId) return;
      if (v && isValidCoordinate(v.lat, v.lng)) {
        activeVids.add(vid);
        const vPos = [v.lat, v.lng];
        const vTooltip = `<b>Vehicle ${vid}</b><br>Lane: ${v.lane || 2}`;
        if (!vehicleMarkers[vid]) {
          vehicleMarkers[vid] = L.marker(vPos, { icon: getLeafletVehicleIcon(false, '🚘') }).addTo(leafletMap);
          vehicleMarkers[vid].bindTooltip(vTooltip);
        } else {
          vehicleMarkers[vid].setLatLng(vPos);
          vehicleMarkers[vid].setTooltipContent(vTooltip);
        }
      }
    });

    Object.keys(vehicleMarkers).forEach(vid => {
      if (!activeVids.has(vid)) {
        leafletMap.removeLayer(vehicleMarkers[vid]);
        delete vehicleMarkers[vid];
      }
    });

    // 5. Junction Marker
    if (state.junction && isValidCoordinate(state.junction.lat, state.junction.lng)) {
      const jPos = [state.junction.lat, state.junction.lng];
      const isPrio = state.junction.priorityActive;
      const jTooltip = `<b>Junction JUNC_01</b><br>Cycle: ${state.junction.currentState || 'NORMAL'}<br>Priority: ${isPrio ? 'GREEN CLEARANCE' : 'NORMAL CYCLE'}`;
      if (!junctionMarker) {
        junctionMarker = L.marker(jPos, { icon: getLeafletJunctionIcon(isPrio) }).addTo(leafletMap);
        junctionMarker.bindTooltip(jTooltip);
      } else {
        junctionMarker.setLatLng(jPos);
        junctionMarker.setIcon(getLeafletJunctionIcon(isPrio));
        junctionMarker.setTooltipContent(jTooltip);
      }
    }

    updateMapTelemetryBanner();
  }

  function updateMapCorridor() {
    if (!leafletMap) return;

    let pts = [];
    if (state.activeJourney && Array.isArray(state.activeJourney.route_points) && state.activeJourney.route_points.length >= 2) {
      pts = state.activeJourney.route_points;
    } else if (Array.isArray(state.activeRoutePoints) && state.activeRoutePoints.length >= 2) {
      pts = state.activeRoutePoints;
    }

    if (pts.length >= 2) {
      const latLngs = pts.map(p => [p.lat, p.lng]);
      if (!corridorPolyline) {
        corridorPolyline = L.polyline(latLngs, {
          color: '#38BDF8',
          weight: 6,
          opacity: 0.85,
          lineJoin: 'round',
        }).addTo(leafletMap);
      } else {
        corridorPolyline.setLatLngs(latLngs);
      }
      if ($('legendCorridorItem')) $('legendCorridorItem').style.display = 'flex';
    } else {
      if (corridorPolyline) {
        leafletMap.removeLayer(corridorPolyline);
        corridorPolyline = null;
      }
      if ($('legendCorridorItem')) $('legendCorridorItem').style.display = 'none';
    }
  }

  function updateMapTelemetryBanner() {
    const dot = $('mapStatusDot');
    const txt = $('mapStatusText');
    if (!dot || !txt) return;

    if (!state.wsConnected) {
      dot.className = 'status-indicator-dot waiting';
      txt.textContent = 'Disconnected from backend • Reconnecting...';
    } else if (state.isDemoModeActive) {
      dot.className = 'status-indicator-dot live';
      dot.style.background = '#eab308';
      txt.textContent = 'Demo Mode Active • Simulated Fleet Telemetry';
    } else if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
      dot.className = 'status-indicator-dot live';
      dot.style.background = '#22c55e';
      const ambId = state.ambulance.id || 'AMB01';
      const isEmg = state.ambulance.emergency ? 'EMERGENCY' : 'STANDBY';
      const isStale = state.ambulance.ts && (Date.now() / 1000 - state.ambulance.ts > 20);
      txt.textContent = `Live Telemetry Active • ${ambId} (${isEmg}) • ${Object.keys(state.vehicles).length} Connected Vehicles ${isStale ? '• [GPS STALE >20s]' : ''}`;
    } else {
      dot.className = 'status-indicator-dot waiting';
      const numVehicles = Object.keys(state.vehicles).length;
      txt.textContent = numVehicles > 0
        ? `Connected • ${numVehicles} vehicle(s) live • Waiting for ambulance journey...`
        : 'Waiting for live backend telemetry...';
    }
  }

  function centerOnAmbulance() {
    if (!leafletMap) {
      showToast('Map initializing...');
      return;
    }
    if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
      leafletMap.panTo([state.ambulance.lat, state.ambulance.lng]);
      showToast('Centered on Ambulance');
    } else {
      showToast('Waiting for live ambulance telemetry');
    }
  }

  function centerOnMe() {
    if (!leafletMap) {
      showToast('Map initializing...');
      return;
    }
    const myVeh = state.vehicles[state.myVehicleId] || state.myPosition;
    if (myVeh && isValidCoordinate(myVeh.lat, myVeh.lng)) {
      leafletMap.panTo([myVeh.lat, myVeh.lng]);
      showToast(`Centered on ${state.myVehicleId}`);
    } else {
      showToast(`Waiting for vehicle ${state.myVehicleId} GPS position`);
    }
  }

  function fitRouteBounds() {
    if (!leafletMap) return;
    if (corridorPolyline) {
      try {
        leafletMap.fitBounds(corridorPolyline.getBounds(), { padding: [40, 40] });
        showToast('Fitted map to road route');
        return;
      } catch (e) {}
    }

    const points = [];
    if (state.ambulance && isValidCoordinate(state.ambulance.lat, state.ambulance.lng)) {
      points.push([state.ambulance.lat, state.ambulance.lng]);
    }
    const myVeh = state.vehicles[state.myVehicleId] || state.myPosition;
    if (myVeh && isValidCoordinate(myVeh.lat, myVeh.lng)) {
      points.push([myVeh.lat, myVeh.lng]);
    }
    if (state.destinationLocation && isValidCoordinate(state.destinationLocation.lat, state.destinationLocation.lng)) {
      points.push([state.destinationLocation.lat, state.destinationLocation.lng]);
    }

    if (points.length >= 2) {
      leafletMap.fitBounds(L.latLngBounds(points), { padding: [50, 50] });
      showToast('Fitted map to active vehicle markers');
    } else if (points.length === 1) {
      leafletMap.panTo(points[0]);
    } else {
      showToast('No active route or markers to fit');
    }
  }

  // ==========================================================================
  // LOCATION AUTOCOMPLETE & NOMINATIM SEARCH
  // ==========================================================================
  const LOCATION_PRESETS = [
    { name: "Victoria Hospital, Fort", lat: 12.9641, lng: 77.5756, sub: "Emergency Hospital • Fort / City Market" },
    { name: "Bowring & Lady Curzon Hospital, Shivaji Nagar", lat: 12.9833, lng: 77.6053, sub: "Government Hospital • Tasker Town" },
    { name: "Manipal Hospital, Old Airport Road", lat: 12.9587, lng: 77.6483, sub: "Multispeciality Hospital • HAL" },
    { name: "Fortis Hospital, Bannerghatta Road", lat: 12.8932, lng: 77.5976, sub: "Super Speciality Hospital • Bannerghatta" },
    { name: "St. John's Medical College Hospital", lat: 12.9309, lng: 77.6209, sub: "Tertiary Hospital • Koramangala" },
    { name: "Apollo Hospital, Jayanagar", lat: 12.9298, lng: 77.5833, sub: "Speciality Hospital • 4th Block Jayanagar" },
    { name: "MG Road Metro Station", lat: 12.9754, lng: 77.6068, sub: "Corridor Intersection • MG Road" },
    { name: "Brigade Road & Residency Road Junction", lat: 12.9716, lng: 77.6070, sub: "Junction JUNC_01 • Bangalore CBD" },
    { name: "Kempegowda Bus Station Majestic", lat: 12.9778, lng: 77.5727, sub: "Central Transit Station" },
    { name: "Indiranagar 100 Feet Road", lat: 12.9698, lng: 77.6416, sub: "Major Commercial Corridor" }
  ];

  function parseCoordinatesString(text) {
    if (!text) return null;
    const parts = text.split(/[\s,]+/);
    if (parts.length >= 2) {
      const lat = parseFloat(parts[0]);
      const lng = parseFloat(parts[1]);
      if (isValidCoordinate(lat, lng)) {
        return { lat, lng, name: `GPS: ${lat.toFixed(4)}, ${lng.toFixed(4)}` };
      }
    }
    return null;
  }

  function setupLocationAutocomplete(inputId, dropdownId, onSelect) {
    const input = $(inputId);
    const dropdown = $(dropdownId);
    if (!input || !dropdown) return;

    let debounceTimer = null;

    function renderSuggestions(list) {
      if (!list || list.length === 0) {
        dropdown.style.display = 'none';
        dropdown.innerHTML = '';
        return;
      }

      dropdown.innerHTML = list.map((item, idx) => `
        <div class="suggestion-item" data-idx="${idx}">
          <span class="suggestion-title">${item.name}</span>
          <span class="suggestion-sub">${item.sub || `${item.lat.toFixed(4)}, ${item.lng.toFixed(4)}`}</span>
        </div>
      `).join('');
      dropdown.style.display = 'block';

      dropdown.querySelectorAll('.suggestion-item').forEach(el => {
        el.addEventListener('mousedown', (e) => {
          e.preventDefault();
          const idx = parseInt(el.getAttribute('data-idx'), 10);
          const selected = list[idx];
          if (selected) {
            input.value = selected.name;
            dropdown.style.display = 'none';
            onSelect(selected);
          }
        });
      });
    }

    input.addEventListener('focus', () => {
      const q = input.value.trim().toLowerCase();
      if (!q) {
        renderSuggestions(LOCATION_PRESETS.slice(0, 5));
      }
    });

    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      const q = input.value.trim();
      if (!q) {
        renderSuggestions(LOCATION_PRESETS.slice(0, 5));
        return;
      }

      const coords = parseCoordinatesString(q);
      if (coords) {
        renderSuggestions([coords]);
        return;
      }

      const filtered = LOCATION_PRESETS.filter(p =>
        p.name.toLowerCase().includes(q.toLowerCase()) ||
        (p.sub && p.sub.toLowerCase().includes(q.toLowerCase()))
      );

      renderSuggestions(filtered);

      if (q.length >= 3) {
        debounceTimer = setTimeout(async () => {
          try {
            const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q)}&countrycodes=in&limit=4`;
            const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
            if (res.ok) {
              const data = await res.json();
              const osmItems = data.map(item => ({
                name: item.display_name.split(',').slice(0, 2).join(','),
                lat: parseFloat(item.lat),
                lng: parseFloat(item.lon),
                sub: item.display_name
              }));
              const combined = [...filtered, ...osmItems];
              renderSuggestions(combined.slice(0, 6));
            }
          } catch (e) {}
        }, 350);
      }
    });

    input.addEventListener('blur', () => {
      setTimeout(() => {
        dropdown.style.display = 'none';
      }, 200);
    });
  }

  // ==========================================================================
  // AMBULANCE OPERATIONAL WORKFLOW & ROUTING (PHASE 3A)
  // ==========================================================================
  async function calculateRoutePreview() {
    const originText = ($('ambStartInput') ? $('ambStartInput').value.trim() : '');
    const destText = ($('ambDestInput') ? $('ambDestInput').value.trim() : '');
    const notice = $('ambRouteStatusNotice');

    function showNotice(msg, type = 'info') {
      if (!notice) return;
      notice.style.display = 'block';
      notice.style.color = type === 'error' ? '#F87171' : type === 'success' ? '#4ADE80' : '#38BDF8';
      notice.style.backgroundColor = type === 'error' ? 'rgba(239, 68, 68, 0.15)' : type === 'success' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(56, 189, 248, 0.15)';
      notice.style.border = `1px solid ${type === 'error' ? '#EF4444' : type === 'success' ? '#22C55E' : '#38BDF8'}`;
      notice.textContent = msg;
    }

    if (!originText || !destText) {
      showToast('Please provide both Start Location and Destination');
      showNotice('Please provide both Start Location and Destination', 'error');
      return;
    }

    // Resolve Origin Coordinates
    let startLat = state.originLocation ? state.originLocation.lat : null;
    let startLng = state.originLocation ? state.originLocation.lng : null;

    if (!isValidCoordinate(startLat, startLng)) {
      const parsed = parseCoordinatesString(originText);
      if (parsed) {
        startLat = parsed.lat;
        startLng = parsed.lng;
      } else if (state.myPosition && isValidCoordinate(state.myPosition.lat, state.myPosition.lng)) {
        startLat = state.myPosition.lat;
        startLng = state.myPosition.lng;
      } else {
        const found = LOCATION_PRESETS.find(p => p.name.toLowerCase().includes(originText.toLowerCase()));
        if (found) {
          startLat = found.lat;
          startLng = found.lng;
        }
      }
    }

    // Resolve Destination Coordinates
    let destLat = state.destinationLocation ? state.destinationLocation.lat : null;
    let destLng = state.destinationLocation ? state.destinationLocation.lng : null;

    if (!isValidCoordinate(destLat, destLng)) {
      const parsed = parseCoordinatesString(destText);
      if (parsed) {
        destLat = parsed.lat;
        destLng = parsed.lng;
      } else {
        const found = LOCATION_PRESETS.find(p => p.name.toLowerCase().includes(destText.toLowerCase()));
        if (found) {
          destLat = found.lat;
          destLng = found.lng;
        }
      }
    }

    if (!isValidCoordinate(startLat, startLng) || !isValidCoordinate(destLat, destLng)) {
      showToast('Resolving geographic coordinates...');
      showNotice('Resolving location coordinates via OpenStreetMap...', 'info');
      try {
        if (!isValidCoordinate(startLat, startLng)) {
          const res1 = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(originText)}&limit=1`);
          const data1 = await res1.json();
          if (data1 && data1.length > 0) {
            startLat = parseFloat(data1[0].lat);
            startLng = parseFloat(data1[0].lon);
          }
        }
        if (!isValidCoordinate(destLat, destLng)) {
          const res2 = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(destText)}&limit=1`);
          const data2 = await res2.json();
          if (data2 && data2.length > 0) {
            destLat = parseFloat(data2[0].lat);
            destLng = parseFloat(data2[0].lon);
          }
        }
      } catch (e) {}
    }

    if (!isValidCoordinate(startLat, startLng) || !isValidCoordinate(destLat, destLng)) {
      showToast('Could not resolve coordinates for start or destination.');
      showNotice('Could not resolve coordinates. Select from autocomplete or enter lat,lng (e.g. 12.9716, 77.5946)', 'error');
      return;
    }

    state.originLocation = { lat: startLat, lng: startLng, name: originText };
    state.destinationLocation = { lat: destLat, lng: destLng, name: destText };

    showToast('Calculating road-following route with OSRM...');
    showNotice('Calculating road route with OSRM...', 'info');

    let routeData = null;

    // Try OSRM directly first
    try {
      const osrmUrl = `${state.routingUrl.replace(/\/$/, '')}/route/v1/driving/${startLng.toFixed(6)},${startLat.toFixed(6)};${destLng.toFixed(6)},${destLat.toFixed(6)}?overview=full&geometries=geojson`;
      const res = await fetch(osrmUrl, { signal: AbortSignal.timeout(4500) });
      if (res.ok) {
        const json = await res.json();
        if (json.code === 'Ok' && json.routes && json.routes[0]) {
          const r = json.routes[0];
          const coords = r.geometry.coordinates; // [lng, lat]
          routeData = {
            points: coords.map(c => ({ lat: c[1], lng: c[0] })),
            distance_m: r.distance,
            duration_s: r.duration,
            source: 'OSRM'
          };
        }
      }
    } catch (e) {
      console.warn('Direct OSRM fetch failed, falling back to backend route endpoint:', e);
    }

    // Fallback to FastAPI backend /api/journey/route
    if (!routeData) {
      try {
        const backendRouteUrl = `/api/journey/route?origin_lat=${startLat}&origin_lng=${startLng}&dest_lat=${destLat}&dest_lng=${destLng}`;
        const res = await fetch(backendRouteUrl);
        if (res.ok) {
          const json = await res.json();
          if (json.points && json.points.length >= 2) {
            routeData = {
              points: json.points,
              distance_m: json.distance_meters,
              duration_s: json.duration_seconds,
              source: json.source || 'BACKEND'
            };
          }
        }
      } catch (e) {
        console.warn('Backend route calculation also failed:', e);
      }
    }

    if (!routeData || !routeData.points || routeData.points.length < 2) {
      showToast('Route calculation failed. Check network or server status.');
      showNotice('Routing unavailable. Check network or routing server.', 'error');
      return;
    }

    state.activeRoutePoints = routeData.points;
    const distKm = (routeData.distance_m / 1000).toFixed(1);
    const durationMin = Math.round(routeData.duration_s / 60);

    if ($('ambRouteDistVal')) $('ambRouteDistVal').textContent = `${distKm} km`;
    if ($('ambRouteEtaVal')) $('ambRouteEtaVal').textContent = `${durationMin} min`;
    if ($('btnStartJourney')) $('btnStartJourney').disabled = false;

    updateMapCorridor();
    updateMapMarkers();
    fitRouteBounds();

    showToast(`Route preview ready: ${distKm} km (~${durationMin} min)`);
    showNotice(`✓ Road route computed (${routeData.source}): ${distKm} km, ~${durationMin} min. Click "START JOURNEY" to dispatch clearance.`, 'success');
  }

  async function startEmergencyJourney() {
    const ambId = state.myAmbulanceId || 'AMB01';
    const origin = ($('ambStartInput') ? $('ambStartInput').value.trim() : '');
    const destination = ($('ambDestInput') ? $('ambDestInput').value.trim() : '');
    const notice = $('ambRouteStatusNotice');

    if (!origin || !destination) {
      showToast('Please enter both origin and destination');
      return;
    }

    if (!state.activeRoutePoints || state.activeRoutePoints.length < 2) {
      showToast('Please click "Calculate & Preview Route" first');
      return;
    }

    const startLat = state.activeRoutePoints[0].lat;
    const startLng = state.activeRoutePoints[0].lng;
    const destLat = state.activeRoutePoints[state.activeRoutePoints.length - 1].lat;
    const destLng = state.activeRoutePoints[state.activeRoutePoints.length - 1].lng;

    const distText = $('ambRouteDistVal')?.textContent || '0';
    const etaText = $('ambRouteEtaVal')?.textContent || '0';

    const payload = {
      ambulance_id: ambId,
      origin_name: origin,
      origin_lat: startLat,
      origin_lng: startLng,
      destination_name: destination,
      destination_lat: destLat,
      destination_lng: destLng,
      route_points: state.activeRoutePoints,
      distance_meters: parseFloat(distText) * 1000,
      duration_seconds: parseFloat(etaText) * 60,
      assigned_lane: state.assignedAmbulanceLane || 'CENTER',
      admin_pin: '9911'
    };

    showToast('Submitting Emergency Journey to Backend...');
    try {
      const res = await fetch('/api/journey/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        showToast('🚨 Emergency Journey Activated!');
        if (notice) {
          notice.style.display = 'block';
          notice.style.color = '#4ADE80';
          notice.style.backgroundColor = 'rgba(34, 197, 94, 0.15)';
          notice.style.border = '1px solid #22C55E';
          notice.textContent = `🚨 ACTIVE EMERGENCY JOURNEY: ${origin} → ${destination} (Lane: ${state.assignedAmbulanceLane})`;
        }
        updateAmbulanceJourneyUI(data);
      } else {
        showToast(`Failed to start journey: ${data.detail || 'Error'}`);
      }
    } catch (e) {
      showToast('Network error starting journey: ' + e.message);
    }
  }

  async function stopEmergencyJourney() {
    const ambId = state.myAmbulanceId || 'AMB01';
    showToast('Stopping Emergency Journey...');
    try {
      const res = await fetch('/api/journey/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ambulance_id: ambId, admin_pin: '9911' })
      });
      if (res.ok) {
        showToast('⏹ Emergency Journey Terminated.');
        const notice = $('ambRouteStatusNotice');
        if (notice) notice.style.display = 'none';
        state.activeRoutePoints = [];
        state.destinationLocation = null;
        updateAmbulanceJourneyUI(null);
      } else {
        showToast('Failed to stop journey');
      }
    } catch (e) {
      showToast('Network error stopping journey: ' + e.message);
    }
  }

  function updateAmbulanceJourneyUI(journey) {
    const badge = $('ambJourneyStatusBadge');
    const dot = $('ambStatusDot');
    const txt = $('ambStatusText');
    const btnStart = $('btnStartJourney');
    const btnStop = $('btnStopJourney');

    if (journey && journey.is_active) {
      state.activeJourney = journey;
      if (badge) badge.className = 'amb-status-badge active-journey';
      if (dot) dot.className = 'status-indicator-dot live';
      if (txt) txt.textContent = 'JOURNEY ACTIVE';
      if (btnStart) btnStart.disabled = true;
      if (btnStop) btnStop.disabled = false;
      if ($('ambRouteDistVal') && journey.distance_meters) {
        $('ambRouteDistVal').textContent = `${(journey.distance_meters / 1000).toFixed(1)} km`;
      }
      if ($('ambRouteEtaVal') && journey.duration_seconds) {
        $('ambRouteEtaVal').textContent = `${Math.round(journey.duration_seconds / 60)} min`;
      }
      if (Array.isArray(journey.route_points) && journey.route_points.length >= 2) {
        state.activeRoutePoints = journey.route_points;
      }
    } else {
      state.activeJourney = null;
      if (badge) badge.className = 'amb-status-badge';
      if (dot) dot.className = 'status-indicator-dot waiting';
      if (txt) txt.textContent = 'STANDBY';
      if (btnStart) btnStart.disabled = false;
      if (btnStop) btnStop.disabled = true;
    }
    updateMapCorridor();
    updateMapMarkers();
  }
  // ==========================================================================
  // OPERATING MODE SELECTOR (PHASE 3)
  // ==========================================================================
  async function switchOperatingMode(mode) {
    state.operatingMode = mode;

    if (state.currentTab !== 'driver') {
      switchTab('driver');
    }

    const btnVeh = $('btnModeVehicle');
    const btnAmb = $('btnModeAmbulance');
    const panelVeh = $('normalVehiclePanel');
    const panelAmb = $('ambulancePanel');

    if (mode === 'AMBULANCE') {
      if (btnAmb) btnAmb.classList.add('active');
      if (btnVeh) btnVeh.classList.remove('active');
      if (panelAmb) panelAmb.style.display = 'block';
      if (panelVeh) panelVeh.style.display = 'none';

      state.myVehicleId = 'AMB01';
      state.myAmbulanceId = 'AMB01';
      showToast('Switched to AMBULANCE MODE (AMB01)');

      // Register role on backend
      try {
        await fetch('/api/device/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            device_id: 'AMB01',
            role: 'AMBULANCE',
            admin_pin: '9911',
            configured_lane: state.assignedAmbulanceLane || 'CENTER'
          })
        });
      } catch (e) {}

      // Check for active journey from backend
      try {
        const res = await fetch('/api/journey/active');
        if (res.ok) {
          const data = await res.json();
          if (data.active && data.journey) {
            updateAmbulanceJourneyUI(data.journey);
          }
        }
      } catch (e) {}
    } else {
      if (btnVeh) btnVeh.classList.add('active');
      if (btnAmb) btnAmb.classList.remove('active');
      if (panelVeh) panelVeh.style.display = 'block';
      if (panelAmb) panelAmb.style.display = 'none';

      state.myVehicleId = 'V002';
      showToast('Switched to NORMAL VEHICLE MODE (V002)');

      // Register role on backend
      try {
        await fetch('/api/device/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            device_id: 'V002',
            role: 'NORMAL_VEHICLE'
          })
        });
      } catch (e) {}
    }

    attachMapToCurrentView();

    // Reconnect backend WebSocket for the selected role
    if (state.useBackend) {
      connectBackend();
    }

    syncDeviceAndAmbulanceHUD();
    renderHUD();
    updateMapMarkers();
  }

  // --- Navigation Tab Switching ---
  function switchTab(tabName) {
    state.currentTab = tabName;
    ['Driver', 'Camera', 'Junction', 'Map', 'Settings'].forEach(t => {
      const screen = $(`screen${t}`);
      const btn = $(`nav${t}Btn`);
      const isActive = t.toLowerCase() === tabName.toLowerCase();

      if (screen) screen.classList.toggle('active', isActive);
      if (btn) btn.classList.toggle('active', isActive);
    });

    attachMapToCurrentView();

    if (tabName === 'camera') {
      pollCameraTelemetry();
    }
  }

  // --- Event Listeners Initialization ---
  function initEvents() {
    // Navigation Tabs
    $('navDriverBtn').addEventListener('click', () => switchTab('driver'));
    $('navCameraBtn').addEventListener('click', () => switchTab('camera'));
    $('navJunctionBtn').addEventListener('click', () => switchTab('junction'));
    $('navMapBtn').addEventListener('click', () => switchTab('map'));
    $('navSettingsBtn').addEventListener('click', () => switchTab('settings'));

    // Sound Toggle Header
    $('soundToggleBtn').addEventListener('click', () => {
      initAudio();
      state.isSoundEnabled = !state.isSoundEnabled;
      $('soundToggle').checked = state.isSoundEnabled;
      $('soundIcon').style.color = state.isSoundEnabled ? 'var(--text-primary)' : 'var(--text-muted)';
      showToast(`Audio Siren: ${state.isSoundEnabled ? 'ENABLED' : 'MUTED'}`);
      if (!state.isSoundEnabled) stopSirenSound();
      else if (state.activeAlert) startSirenSound();
    });

    // Lane Selection Segment Buttons
    $('lane1Btn').addEventListener('click', () => setMyLane(1));
    $('lane2Btn').addEventListener('click', () => setMyLane(2));
    $('lane3Btn').addEventListener('click', () => setMyLane(3));

    // Clear Lane Action Buttons
    $('btnShiftLeft').addEventListener('click', () => setMyLane(state.myLane - 1));
    $('btnShiftRight').addEventListener('click', () => setMyLane(state.myLane + 1));

    // Emergency Toggle (Guarded)
    if ($('emergencyToggle')) {
      $('emergencyToggle').addEventListener('change', (e) => {
        if (state.ambulance) state.ambulance.emergency = e.target.checked;
        showToast(`Emergency Mode: ${e.target.checked ? 'ON' : 'OFF'}`);
        recalculateAlert();
      });
    }

    // Camera Access Power Buttons
    $('btnCameraTurnOn').addEventListener('click', async () => {
      showToast('Turning ON Camera Access...');
      try {
        const res = await fetch('/api/camera/access', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: true, vehicle_id: state.myVehicleId })
        });
        const data = await res.json();
        showToast(data.message || 'Camera Access: ENABLED');
      } catch (err) {
        showToast('Failed to enable camera: ' + err.message);
      }
      pollCameraTelemetry();
    });

    $('btnCameraTurnOff').addEventListener('click', async () => {
      showToast('Turning OFF Camera Access & Releasing Hardware...');
      try {
        const res = await fetch('/api/camera/access', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: false, vehicle_id: state.myVehicleId })
        });
        const data = await res.json();
        showToast(data.message || 'Camera Access: DISABLED');
      } catch (err) {
        showToast('Failed to disable camera: ' + err.message);
      }
      const feed = $('cameraLiveFeed');
      if (feed) feed.src = '/api/camera/preview';
      pollCameraTelemetry();
    });

    // Manual Still Photo Capture Button
    if ($('btnManualCapture')) {
      $('btnManualCapture').addEventListener('click', async () => {
        showToast('Triggering single still-image capture (POST /api/camera/capture)...');
        try {
          const res = await fetch('/api/camera/capture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vehicle_id: state.myVehicleId })
          });
          const data = await res.json();
          if (data.status === 'SUCCESS') {
            showToast(`📸 Photo Captured! Lane: ${data.lane} (${Math.round(data.confidence * 100)}%)`);
          } else {
            showToast(`Capture result: ${data.status} ${data.error ? '(' + data.error + ')' : ''}`);
          }
        } catch (err) {
          showToast('Manual capture request failed: ' + err.message);
        }
        pollCameraTelemetry();
      });
    }

    // Diagnostic Image Retention Toggle
    if ($('retentionToggle')) {
      $('retentionToggle').addEventListener('change', async (e) => {
        const retain = e.target.checked;
        try {
          await fetch('/api/camera/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ diagnostic_retention: retain })
          });
          showToast(`Diagnostic Retention: ${retain ? 'ENABLED (Diagnostics saved to disk)' : 'DISABLED (Discarded after inference)'}`);
        } catch (err) {
          showToast('Failed to update retention: ' + err.message);
        }
      });
    }

    // Camera Source Buttons
    $('btnSourceUsb').addEventListener('click', async () => {
      $('btnSourceUsb').classList.add('active');
      $('btnSourceSim').classList.remove('active');
      showToast('Selected Physical USB Camera (0)');
      await fetch('/api/camera/source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 0, vehicle_id: state.myVehicleId })
      });
      pollCameraTelemetry();
    });

    $('btnSourceSim').addEventListener('click', async () => {
      $('btnSourceSim').classList.add('active');
      $('btnSourceUsb').classList.remove('active');
      showToast('Switching to Prerecorded Video Test Mode...');
      await fetch('/api/camera/source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'prerecorded', vehicle_id: state.myVehicleId })
      });
      pollCameraTelemetry();
    });

    // Priority Test Buttons
    $('btnTestPriorityTrigger').addEventListener('click', async () => {
      showToast('Sending Priority Request to JUNC_01...');
      const res = await fetch('/api/junction/priority/JUNC_01', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approach_id: 'NORTH_SOUTH', eta_s: 14.5 })
      });
      const data = await res.json();
      showToast(`Priority Initiated: ${data.status}`);
      // Add entry to log
      const log = $('transitionLogList');
      if (log) {
        const item = document.createElement('div');
        item.className = 'log-entry';
        item.textContent = `[${new Date().toLocaleTimeString()}] Priority sequence requested -> Yellow Change -> All-Red -> Green A`;
        log.prepend(item);
      }
    });

    $('btnTestPriorityClear').addEventListener('click', async () => {
      showToast('Clearing Priority...');
      await fetch('/api/junction/priority/JUNC_01', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approach_id: 'CLEAR', eta_s: 0 })
      });
      showToast('Priority Cleared -> Safe cycle resuming');
    });

    // Operating Mode Switcher Controls (Phase 3)
    if ($('btnModeVehicle')) {
      $('btnModeVehicle').addEventListener('click', () => switchOperatingMode('NORMAL_VEHICLE'));
    }
    if ($('btnModeAmbulance')) {
      $('btnModeAmbulance').addEventListener('click', () => switchOperatingMode('AMBULANCE'));
    }

    // Ambulance Lane Assignment Controls (Phase 3A)
    function selectAmbulanceLane(lane) {
      state.assignedAmbulanceLane = lane;
      ['btnLaneLeft', 'btnLaneCenter', 'btnLaneRight'].forEach(id => {
        const btn = $(id);
        if (!btn) return;
        btn.classList.toggle('selected', btn.getAttribute('data-lane') === lane);
      });
      showToast(`Assigned Ambulance Lane: ${lane}`);
      fetch('/api/ambulance/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ designated_lane: lane, configured_lane: lane })
      }).catch(() => {});
    }

    if ($('btnLaneLeft')) $('btnLaneLeft').addEventListener('click', () => selectAmbulanceLane('LEFT'));
    if ($('btnLaneCenter')) $('btnLaneCenter').addEventListener('click', () => selectAmbulanceLane('CENTER'));
    if ($('btnLaneRight')) $('btnLaneRight').addEventListener('click', () => selectAmbulanceLane('RIGHT'));

    // Ambulance Start Location via Live GPS
    if ($('btnAmbUseGps')) {
      $('btnAmbUseGps').addEventListener('click', () => {
        if (state.myPosition && isValidCoordinate(state.myPosition.lat, state.myPosition.lng)) {
          if ($('ambStartInput')) {
            $('ambStartInput').value = `${state.myPosition.lat.toFixed(5)}, ${state.myPosition.lng.toFixed(5)}`;
          }
          showToast(`Using Current GPS as Start: ${state.myPosition.lat.toFixed(4)}, ${state.myPosition.lng.toFixed(4)}`);
        } else if (navigator.geolocation) {
          showToast('Acquiring current GPS position...');
          navigator.geolocation.getCurrentPosition(
            (pos) => {
              const lat = pos.coords.latitude;
              const lng = pos.coords.longitude;
              state.myPosition = { lat, lng };
              if ($('ambStartInput')) {
                $('ambStartInput').value = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
              }
              if ($('ambCurrentGpsLabel')) {
                $('ambCurrentGpsLabel').textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
              }
              showToast(`GPS Position Acquired: ${lat.toFixed(4)}, ${lng.toFixed(4)}`);
            },
            (err) => {
              showToast(`GPS unavailable: ${err.message}. Enter address manually.`);
            },
            { enableHighAccuracy: true, timeout: 8000 }
          );
        } else {
          showToast('Geolocation is not supported in this browser. Enter address manually.');
        }
      });
    }

    // Ambulance Journey Actions
    if ($('btnCalcRoute')) $('btnCalcRoute').addEventListener('click', calculateRoutePreview);
    if ($('btnStartJourney')) $('btnStartJourney').addEventListener('click', startEmergencyJourney);
    if ($('btnStopJourney')) $('btnStopJourney').addEventListener('click', stopEmergencyJourney);

    // Map Controls
    if ($('btnCenterAmbulance')) $('btnCenterAmbulance').addEventListener('click', centerOnAmbulance);
    if ($('btnCenterMe')) $('btnCenterMe').addEventListener('click', centerOnMe);
    if ($('btnFitRoute')) $('btnFitRoute').addEventListener('click', fitRouteBounds);
    if ($('btnToggleSimPlay')) $('btnToggleSimPlay').addEventListener('click', toggleSimulationPlayback);
    if ($('btnResetScenario')) $('btnResetScenario').addEventListener('click', resetSimulationScenario);

    // Map & Routing Settings Handler (OpenStreetMap + OSRM)
    if ($('btnSaveMapSettings')) {
      $('btnSaveMapSettings').addEventListener('click', () => {
        const tInput = $('settingsTileUrlInput');
        const rInput = $('settingsRoutingUrlInput');
        if (tInput && tInput.value.trim()) state.tileUrl = tInput.value.trim();
        if (rInput && rInput.value.trim()) state.routingUrl = rInput.value.trim();
        localStorage.setItem('evas_tile_url', state.tileUrl);
        localStorage.setItem('evas_routing_url', state.routingUrl);
        if (tileLayer) tileLayer.setUrl(state.tileUrl);
        if ($('settingsMapNotice')) {
          $('settingsMapNotice').style.display = 'block';
          setTimeout(() => { $('settingsMapNotice').style.display = 'none'; }, 3000);
        }
        showToast('Map & Routing settings updated!');
      });
    }

    // Location Autocomplete Setup
    setupLocationAutocomplete('ambStartInput', 'ambStartSuggestions', (loc) => {
      state.originLocation = loc;
      updateMapMarkers();
    });
    setupLocationAutocomplete('ambDestInput', 'ambDestSuggestions', (loc) => {
      state.destinationLocation = loc;
      updateMapMarkers();
    });

    // Settings Controls
    $('backendToggle').addEventListener('change', (e) => {
      if (e.target.checked) {
        connectBackend();
      } else {
        disconnectBackend(true);
      }
    });

    $('btnConnectWs').addEventListener('click', connectBackend);
    $('btnDisconnectWs').addEventListener('click', () => disconnectBackend(true));

    $('vehicleSelect').addEventListener('change', (e) => {
      state.myVehicleId = e.target.value;
      showToast(`Active Vehicle Profile: ${state.myVehicleId}`);
      if (state.useBackend) {
        connectBackend(); // reconnect with new vehicle ID
      } else {
        recalculateAlert();
      }
    });

    $('soundToggle').addEventListener('change', (e) => {
      state.isSoundEnabled = e.target.checked;
      $('soundIcon').style.color = state.isSoundEnabled ? 'var(--text-primary)' : 'var(--text-muted)';
      if (!state.isSoundEnabled) stopSirenSound();
    });

    $('vibrationToggle').addEventListener('change', (e) => {
      state.isVibrationEnabled = e.target.checked;
    });

    // REST Diagnostic Status Button
    $('btnFetchStatus').addEventListener('click', async () => {
      const out = $('diagOutput');
      out.style.display = 'block';
      out.textContent = 'Polling GET /status ...';
      try {
        const res = await fetch('/status');
        const data = await res.json();
        out.textContent = `HTTP ${res.status}\n` + JSON.stringify(data, null, 2);
      } catch (e) {
        out.textContent = `Failed: ${e.message}`;
      }
    });

    // File Upload Camera Frame Test
    $('cameraFileInput').addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      const out = $('diagOutput');
      out.style.display = 'block';
      out.textContent = `Uploading ${file.name} to /api/camera/frame/${state.myVehicleId} ...`;

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`/api/camera/frame/${state.myVehicleId}`, {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        out.textContent = `HTTP ${res.status}\n` + JSON.stringify(data, null, 2);
        if (data.accepted && data.result && data.result.lane) {
          showToast(`Camera detected lane: ${data.result.lane}`);
        }
      } catch (err) {
        out.textContent = `Upload failed: ${err.message}`;
      }
    });

    // Device Registration & Role Handlers
    if ($('regDeviceRole')) {
      $('regDeviceRole').addEventListener('change', (e) => {
        if ($('adminPinGroup')) {
          $('adminPinGroup').style.display = e.target.value === 'AMBULANCE' ? 'block' : 'none';
        }
      });
    }

    if ($('btnRegisterDevice')) {
      $('btnRegisterDevice').addEventListener('click', async () => {
        const devId = $('regDeviceId') ? $('regDeviceId').value.trim() : state.myVehicleId;
        const role = $('regDeviceRole') ? $('regDeviceRole').value : 'NORMAL_VEHICLE';
        const pin = $('regAdminPin') ? $('regAdminPin').value.trim() : undefined;

        showToast(`Registering ${devId} as ${role}...`);
        try {
          const res = await fetch('/api/device/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: devId, role: role, admin_pin: pin || null })
          });
          const data = await res.json();
          if (res.ok) {
            showToast(`Registration Successful: ${data.device_id} is ${data.role}`);
            state.myVehicleId = devId;
            syncDeviceAndAmbulanceHUD();
          } else {
            showToast(`Registration Failed: ${data.detail || 'Access denied'}`);
          }
        } catch (err) {
          showToast('Registration error: ' + err.message);
        }
      });
    }

    // Ambulance Configuration Handler
    if ($('btnSaveAmbConfig')) {
      $('btnSaveAmbConfig').addEventListener('click', async () => {
        const lane = $('ambConfigLane') ? $('ambConfigLane').value : 'CENTER';
        const approach = $('ambConfigApproach') ? $('ambConfigApproach').value : 'NORTH_SOUTH';

        showToast(`Saving Ambulance Lane: ${lane}, Approach: ${approach}...`);
        try {
          const res = await fetch('/api/ambulance/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ designated_lane: lane, designated_approach: approach })
          });
          const data = await res.json();
          if (res.ok) {
            showToast(`Ambulance Config Saved: Lane ${data.designated_lane}`);
            syncDeviceAndAmbulanceHUD();
          } else {
            showToast(`Save failed: ${data.detail || 'Error'}`);
          }
        } catch (err) {
          showToast('Config error: ' + err.message);
        }
      });
    }

    // Deterministic Demonstration Scenario Handlers
    if ($('btnRunScenario')) {
      $('btnRunScenario').addEventListener('click', async () => {
        const scenarioId = $('demoScenarioSelect') ? $('demoScenarioSelect').value : 'DIRECT_BLOCKING';
        showToast(`Loading Test Scenario: ${scenarioId}...`);
        try {
          const res = await fetch(`/api/demo/scenario?scenario_id=${scenarioId}`, {
            method: 'POST'
          });
          const data = await res.json();
          if (res.ok) {
            state.isDemoModeActive = true;
            showToast(`Scenario Loaded: [TEST DATA / SIMULATED]`);
            if ($('demoScenarioDetails')) {
              $('demoScenarioDetails').style.display = 'block';
              $('demoScenarioDetails').innerHTML = `
                <div style="color: #facc15; font-weight: 700; margin-bottom: 4px;">⚠️ TEST DATA / SIMULATED FIXTURE ACTIVE</div>
                <div><strong>Scenario:</strong> ${data.scenario_name}</div>
                <div><strong>Description:</strong> ${data.description}</div>
                <div><strong>Expected Outcome:</strong> ${data.expected_outcome}</div>
              `;
            }

            if ($('demoSimControls')) {
              $('demoSimControls').style.display = 'flex';
            }

            // Mark HUD as Test Mode
            if ($('hudModeBadge')) {
              $('hudModeBadge').textContent = 'TEST DATA / SIMULATED';
              $('hudModeBadge').style.background = 'rgba(234, 179, 8, 0.2)';
              $('hudModeBadge').style.color = '#facc15';
              $('hudModeBadge').style.borderColor = 'rgba(234, 179, 8, 0.4)';
            }

            // Inject scenario fleet fixtures
            if (data.ambulance) {
              state.ambulance = {
                id: data.ambulance.id || 'AMB01',
                lat: data.ambulance.lat,
                lng: data.ambulance.lng,
                speedKmh: data.ambulance.speed_kmh || 75,
                headingDeg: data.ambulance.heading_deg || 0,
                lane: data.ambulance.lane || 2,
                emergency: true
              };
            }
            if (data.vehicles) {
              state.vehicles = Object.assign({}, data.vehicles);
            }
            if (data.junction) {
              updateJunctionUI(data.junction);
            }

            if (data.active_alert) {
              state.activeAlert = data.active_alert;
              startSirenSound();
              triggerVibration();
            } else {
              state.activeAlert = null;
              stopSirenSound();
            }
            renderHUD();
            updateMapMarkers();
          } else {
            showToast(`Failed to load scenario: ${data.detail || 'Error'}`);
          }
        } catch (err) {
          showToast('Scenario run error: ' + err.message);
        }
      });
    }

    if ($('btnResetScenarioLive')) {
      $('btnResetScenarioLive').addEventListener('click', () => {
        showToast('Restoring LIVE Hardware Mode...');
        resetSimulationScenario();
        syncDeviceAndAmbulanceHUD();
      });
    }
  }

  // --- Sync Device & Ambulance Config onto HUD ---
  async function syncDeviceAndAmbulanceHUD() {
    try {
      const ambRes = await fetch('/api/ambulance/config');
      if (ambRes.ok) {
        const ambData = await ambRes.json();
        const laneNum = ambData.designated_lane === 'LEFT' ? 1 : (ambData.designated_lane === 'CENTER' ? 2 : 3);
        if ($('hudAmbConfigLane')) $('hudAmbConfigLane').textContent = `${ambData.designated_lane} (L${laneNum})`;
        if ($('hudAmbConfigApproach')) $('hudAmbConfigApproach').textContent = ambData.designated_approach;
        if (state.ambulance) state.ambulance.lane = laneNum;
      }

      if ($('hudDeviceId')) $('hudDeviceId').textContent = state.myVehicleId;
      const isAmb = state.myVehicleId.startsWith('AMB');
      if ($('hudDeviceRole')) $('hudDeviceRole').textContent = isAmb ? 'AMBULANCE' : 'NORMAL_VEHICLE';
      if ($('hudRoleBadge')) {
        $('hudRoleBadge').textContent = isAmb ? 'EMERGENCY' : 'VEHICLE';
        $('hudRoleBadge').style.background = isAmb ? 'rgba(239, 68, 68, 0.2)' : 'rgba(99, 102, 241, 0.2)';
        $('hudRoleBadge').style.color = isAmb ? '#f87171' : '#a5b4fc';
        $('hudRoleBadge').style.borderColor = isAmb ? 'rgba(239, 68, 68, 0.4)' : 'rgba(99, 102, 241, 0.4)';
      }
    } catch (e) {}
  }

  // --- Background REST Status Poller ---
  async function pollBackendStatus() {
    try {
      const res = await fetch('/status');
      if (!res.ok) return;
      const data = await res.json();

      // Ambulance state from backend
      if (data.ambulance_state && isValidCoordinate(data.ambulance_state.lat, data.ambulance_state.lng)) {
        state.ambulance = {
          id: data.ambulance_state.ambulance_id || 'AMB01',
          lat: data.ambulance_state.lat,
          lng: data.ambulance_state.lng,
          speedKmh: data.ambulance_state.speed_kmh || 0,
          headingDeg: data.ambulance_state.heading_deg || 0,
          emergency: data.ambulance_state.emergency ?? true,
          lane: data.ambulance_state.lane || 2,
        };
      } else if (!data.ambulance_connected && (!state.activeAlert || state.activeAlert.emergencyState === false)) {
        if (!state.isDemoModeActive) {
          state.ambulance = null;
        }
      }

      // Vehicle states from backend
      if (data.vehicle_states && !state.isDemoModeActive) {
        const updated = {};
        for (const [vid, v] of Object.entries(data.vehicle_states)) {
          if (v && isValidCoordinate(v.lat, v.lng)) {
            updated[vid] = {
              id: vid,
              lat: v.lat,
              lng: v.lng,
              speedKmh: v.speed_kmh || 0,
              headingDeg: v.heading_deg || 0,
              lane: v.lane ? parseInt(v.lane, 10) : 2,
            };
          }
        }
        if (state.myPosition && isValidCoordinate(state.myPosition.lat, state.myPosition.lng)) {
          updated[state.myVehicleId] = {
            id: state.myVehicleId,
            lat: state.myPosition.lat,
            lng: state.myPosition.lng,
            speedKmh: state.speedKmh || 0,
            headingDeg: state.headingDeg || 0,
            lane: state.myLane
          };
        }
        state.vehicles = updated;
      }

      renderHUD();
      updateMapMarkers();
    } catch (e) {
      // Offline / waiting for server
    }
  }

  // --- Background Periodic Poller ---
  function startPeriodicSync() {
    setInterval(() => {
      pollCameraTelemetry();
      pollBackendStatus();
      fetch('/api/junction/status')
        .then(r => r.json())
        .then(data => {
          if (data && data['JUNC_01']) {
            updateJunctionUI(data['JUNC_01']);
            renderHUD();
          }
        })
        .catch(() => {});
    }, 2000);
  }

  // --- Initial Boot ---
  window.addEventListener('DOMContentLoaded', () => {
    initEvents();
    initLeafletMap();
    renderHUD();
    syncDeviceAndAmbulanceHUD();
    startPeriodicSync();
    startBrowserGeolocation();

    // Auto-connect to backend WebSocket
    setTimeout(() => {
      connectBackend();
    }, 400);
  });
})();
