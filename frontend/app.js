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
    myVehicleId: 'V002',
    myLane: 2,
    speedKmh: 40,
    headingDeg: 0,
    useBackend: false,
    isSoundEnabled: true,
    isVibrationEnabled: true,
    activeAlert: null,
    wsConnected: false,
    ws: null,
    wsReconnectTimer: null,
    wsMsgCount: 0,
    simTimer: null,
    isPlayingSim: false,

    // Fleet state (Bangalore reference corridor)
    ambulance: {
      id: 'AMB01',
      lat: 12.9716,
      lng: 77.5946,
      speedKmh: 75,
      headingDeg: 0,
      lane: 2,
      isEmergency: true,
    },
    vehicles: {
      'V001': { id: 'V001', label: 'V001 (Sedan)', lat: 12.9736, lng: 77.59456, speedKmh: 45, lane: 1 },
      'V002': { id: 'V002', label: 'V002 (SUV)', lat: 12.9748, lng: 77.59460, speedKmh: 40, lane: 2 },
      'V003': { id: 'V003', label: 'V003 (Hatchback)', lat: 12.9741, lng: 77.59464, speedKmh: 50, lane: 3 },
    },

    // Junction & Signal State
    junction: {
      id: 'JUNC_01',
      lat: 12.9740,
      lng: 77.5950,
      currentState: 'NORMAL_CYCLE',
      priorityActive: false,
      hardwareMode: 'PHYSICAL_ESP32',
      lights: {
        approach_a: { red: false, yellow: false, green: true },
        approach_b: { red: true, yellow: false, green: false }
      }
    },

    // Camera AI State
    camera: {
      sourceType: 'physical_usb_camera_0',
      fps: 6.0,
      lane: 'CENTER',
      confidence: 0.92,
      offsetM: 0.08,
      latencyMs: 11.4,
      modelType: 'pytorch_lane_net',
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

  // --- Standalone Simulation Engine ---
  function recalculateAlert() {
    if (state.useBackend) return; // Backend controls alerts when connected

    const myVeh = state.vehicles[state.myVehicleId];
    if (!myVeh) return;

    const amb = state.ambulance;
    const dist = haversineMeters(amb.lat, amb.lng, myVeh.lat, myVeh.lng);
    const isAhead = myVeh.lat > amb.lat;
    const isSameLane = myVeh.lane === amb.lane;

    if (amb.isEmergency && isAhead && isSameLane && dist <= 600) {
      const relSpeed = Math.max((amb.speedKmh - myVeh.speedKmh) * 1000 / 3600, 5.0);
      const eta = Math.max(1, Math.round(dist / relSpeed));

      state.activeAlert = {
        toId: state.myVehicleId,
        ambulanceId: amb.id,
        distance: Math.round(dist),
        eta: eta,
        ambulanceLane: amb.lane,
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
    if (!state.isPlayingSim || state.useBackend) return;

    // Advance ambulance Northward
    state.ambulance.lat += 0.00012; // ~13m per step
    if (state.ambulance.lat > 12.9800) {
      state.ambulance.lat = 12.9716; // loop
    }

    // Advance vehicles slowly
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
      icon.textContent = '⏸';
      txt.textContent = 'Pause';
      showToast('Simulation Playing');
      if (!state.simTimer) {
        state.simTimer = setInterval(stepSimulation, 1000);
      }
    } else {
      icon.textContent = '▶';
      txt.textContent = 'Play';
      showToast('Simulation Paused');
      if (state.simTimer) {
        clearInterval(state.simTimer);
        state.simTimer = null;
      }
    }
  }

  function resetSimulationScenario() {
    state.ambulance.lat = 12.9716;
    state.ambulance.lng = 77.5946;
    state.ambulance.lane = 2;
    state.ambulance.isEmergency = true;
    $('emergencyToggle').checked = true;

    state.vehicles['V001'].lat = 12.9736;
    state.vehicles['V001'].lane = 1;
    state.vehicles['V002'].lat = 12.9748;
    state.vehicles['V002'].lane = 2;
    state.vehicles['V003'].lat = 12.9741;
    state.vehicles['V003'].lane = 3;

    setMyLane(2);
    recalculateAlert();
    updateMapMarkers();
    showToast('Scenario Reset to Initial State');
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
    const inputVal = $('wsUrlInput').value.trim();
    if (inputVal) return inputVal;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}`;
  }

  function connectBackend() {
    const base = getWsBaseUrl();
    const url = `${base}/ws/vehicle/${state.myVehicleId}`;

    showToast(`Connecting to ${url} ...`);
    $('wsStatusBadge').textContent = 'CONNECTING...';
    $('wsStatusBadge').style.color = 'var(--warning)';

    try {
      if (state.ws) {
        state.ws.close();
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
        showToast('WebSocket Connected to FastAPI');

        // Immediately send vehicle state
        sendTelemetryToBackend();
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
    }
  }

  function disconnectBackend(userInitiated = false) {
    if (userInitiated) {
      state.useBackend = false;
      $('backendToggle').checked = false;
      $('backendModeDesc').textContent = 'Running standalone simulation';
    }
    clearTimeout(state.wsReconnectTimer);
    if (state.ws) {
      state.ws.close();
      state.ws = null;
    }
    state.wsConnected = false;
    showToast('Disconnected from Backend');
  }

  function sendTelemetryToBackend() {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    const myVeh = state.vehicles[state.myVehicleId] || { lat: 12.9748, lng: 77.5946 };

    const payload = {
      type: 'telemetry',
      vehicle_id: state.myVehicleId,
      lat: myVeh.lat,
      lng: myVeh.lng,
      speed_kmh: state.speedKmh,
      heading_deg: state.headingDeg,
      lane: String(state.myLane),
      lane_confidence: 0.95,
      ts: Date.now() / 1000.0
    };

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
      startSirenSound();
      triggerVibration();
      renderHUD();
      return;
    }

    // 2. Emergency Clearance
    if (data.type === 'emergency_clear' || (data.to_id === state.myVehicleId && data.emergency_state === false)) {
      state.activeAlert = null;
      stopSirenSound();
      renderHUD();
      return;
    }

    // 3. Fleet & Junction Update
    if (data.type === 'fleet_update') {
      if (data.ambulance) {
        state.ambulance.lat = data.ambulance.lat;
        state.ambulance.lng = data.ambulance.lng;
        state.ambulance.speedKmh = data.ambulance.speed_kmh || state.ambulance.speedKmh;
        state.ambulance.lane = data.ambulance.lane || 2;
        state.ambulance.isEmergency = data.ambulance.emergency ?? true;
      }
      if (data.vehicles) {
        Object.entries(data.vehicles).forEach(([id, v]) => {
          if (state.vehicles[id]) {
            state.vehicles[id].lat = v.lat;
            state.vehicles[id].lng = v.lng;
            state.vehicles[id].speedKmh = v.speed_kmh || state.vehicles[id].speedKmh;
            if (v.lane !== undefined) state.vehicles[id].lane = Number(v.lane);
          }
        });
      }
      if (data.junctions && data.junctions['JUNC_01']) {
        updateJunctionUI(data.junctions['JUNC_01']);
      }
      renderHUD();
      updateMapMarkers();
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
      $('alertTitle').textContent = 'Path is Clear';
      $('alertSubtitle').textContent = state.ambulance.isEmergency
        ? 'Ambulance is active in an adjacent corridor.'
        : 'No active emergency vehicles detected in your path.';
      $('alertIcon').setAttribute('fill', '#22C55E');

      metrics.style.display = 'none';
      clearActions.style.display = 'none';
      badge.classList.remove('visible');
      laneBadge.className = 'lane-status-badge safe';
      laneBadge.textContent = 'CLEAR';

      // Distance to ambulance
      const myVeh = state.vehicles[state.myVehicleId] || { lat: 12.9748, lng: 77.5946 };
      const d = Math.round(haversineMeters(state.ambulance.lat, state.ambulance.lng, myVeh.lat, myVeh.lng));
      $('ambDistVal').textContent = d;
      $('ambDistUnit').textContent = 'm';
      $('distIconBox').style.color = 'var(--accent-cyan)';
    }

    // 2. Ambulance Lane Beacon on Road lanes
    const ambLane = state.ambulance.lane || 2;
    [1, 2, 3].forEach(n => {
      const beacon = $(`beaconLane${n}`);
      if (beacon) {
        beacon.style.display = (state.ambulance.isEmergency && n === ambLane) ? 'block' : 'none';
      }
    });

    // 3. Upcoming Junction HUD card
    const distToJunc = Math.round(haversineMeters(state.ambulance.lat, state.ambulance.lng, state.junction.lat, state.junction.lng));
    const speedMs = Math.max(5.0, (state.ambulance.speedKmh * 1000) / 3600);
    const etaToJunc = Math.max(0, Math.round(distToJunc / speedMs));

    $('hudJuncEta').textContent = `${etaToJunc} s`;
    $('hudJuncStatusBadge').textContent = state.junction.currentState;
    $('hudJuncPriority').textContent = state.junction.priorityActive ? 'PRIORITY HOLD' : (etaToJunc <= 30 && state.ambulance.isEmergency ? 'REQUESTED' : 'IDLE');

    // Update mini lamps
    const aLights = state.junction.lights.approach_a || {};
    $('hudLampRed').className = `mini-lamp red ${aLights.red ? 'on' : ''}`;
    $('hudLampYellow').className = `mini-lamp yellow ${aLights.yellow ? 'on' : ''}`;
    $('hudLampGreen').className = `mini-lamp green ${aLights.green ? 'on' : ''}`;
  }

  // --- Junction Signal Controller UI ---
  function updateJunctionUI(jData) {
    if (!jData) return;
    state.junction.currentState = jData.current_state || state.junction.currentState;
    state.junction.priorityActive = jData.priority_active ?? state.junction.priorityActive;
    state.junction.hardwareMode = jData.hardware_mode || state.junction.hardwareMode;
    state.junction.lights = jData.lights || state.junction.lights;

    // Hardware badge
    const hwBadge = $('esp32HwBadge');
    if (hwBadge) {
      if (state.junction.hardwareMode === 'PHYSICAL_ESP32') {
        hwBadge.className = 'badge-pill active';
        hwBadge.textContent = 'ESP32: CONNECTED (COM5)';
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
    const lA = state.junction.lights.approach_a || {};
    if ($('sigARed')) $('sigARed').className = `signal-lamp red ${lA.red ? 'on' : ''}`;
    if ($('sigAYellow')) $('sigAYellow').className = `signal-lamp yellow ${lA.yellow ? 'on' : ''}`;
    if ($('sigAGreen')) $('sigAGreen').className = `signal-lamp green ${lA.green ? 'on' : ''}`;
    if ($('labelAppA')) {
      $('labelAppA').textContent = lA.green ? 'GREEN (CLEARANCE)' : (lA.yellow ? 'AMBER / CAUTION' : 'RED / STOP');
      $('labelAppA').style.color = lA.green ? 'var(--safe)' : (lA.yellow ? 'var(--warning)' : 'var(--emergency)');
    }

    // Physical LED Signal Lamps (Approach B)
    const lB = state.junction.lights.approach_b || {};
    if ($('sigBRed')) $('sigBRed').className = `signal-lamp red ${lB.red ? 'on' : ''}`;
    if ($('sigBYellow')) $('sigBYellow').className = `signal-lamp yellow ${lB.yellow ? 'on' : ''}`;
    if ($('sigBGreen')) $('sigBGreen').className = `signal-lamp green ${lB.green ? 'on' : ''}`;
    if ($('labelAppB')) {
      $('labelAppB').textContent = lB.green ? 'GREEN (CROSS-TRAFFIC)' : (lB.yellow ? 'AMBER / CAUTION' : 'RED / STOP');
      $('labelAppB').style.color = lB.green ? 'var(--safe)' : (lB.yellow ? 'var(--warning)' : 'var(--emergency)');
    }

    // Distance and ETA
    const distToJunc = Math.round(haversineMeters(state.ambulance.lat, state.ambulance.lng, state.junction.lat, state.junction.lng));
    const speedMs = Math.max(5.0, (state.ambulance.speedKmh * 1000) / 3600);
    const etaToJunc = Math.max(0, Math.round(distToJunc / speedMs));

    if ($('juncDistVal')) $('juncDistVal').textContent = `${distToJunc} m`;
    if ($('juncEtaVal')) $('juncEtaVal').textContent = `${etaToJunc} s`;

    const pBadge = $('priorityStatusBadge');
    if (pBadge) {
      if (state.junction.priorityActive) {
        pBadge.className = 'badge-pill active';
        pBadge.textContent = 'PRIORITY_HOLD ACTIVE';
      } else if (etaToJunc <= 30 && state.ambulance.isEmergency) {
        pBadge.className = 'badge-pill active';
        pBadge.textContent = 'REQUESTED (ETA <= 30s)';
      } else {
        pBadge.className = 'badge-pill';
        pBadge.textContent = 'IDLE';
      }
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
        $('camLaneVal').textContent = isEnabled ? (data.lane || 'UNKNOWN') : 'STANDBY';
        $('camLaneVal').style.color = data.lane === 'CENTER' ? 'var(--safe)' : (data.lane === 'UNKNOWN' ? 'var(--text-muted)' : 'var(--warning)');
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

  // --- Leaflet Live Map ---
  let mapInstance = null;
  let mapMarkers = {};
  let corridorPolyline = null;
  let junctionMarker = null;

  function initMap() {
    if (mapInstance) return;

    const initialCenter = [state.ambulance.lat, state.ambulance.lng];
    mapInstance = L.map('map', {
      center: initialCenter,
      zoom: 16,
      zoomControl: false,
    });

    L.control.zoom({ position: 'bottomright' }).addTo(mapInstance);

    // CartoDB Dark Matter tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; CartoDB & OpenStreetMap',
      subdomains: 'abcd',
      maxZoom: 19
    }).addTo(mapInstance);

    // Initial corridor & markers
    updateMapCorridor();
    updateMapMarkers();
  }

  function createCustomIcon(label, isAmbulance, isTarget) {
    const color = isAmbulance ? '#EF4444' : isTarget ? '#6366F1' : '#38BDF8';
    const emoji = isAmbulance ? '🚑' : '🚗';
    return L.divIcon({
      className: 'custom-map-marker',
      html: `
        <div style="
          background: ${color};
          color: white;
          border: 2px solid white;
          border-radius: 20px;
          padding: 3px 8px;
          font-weight: 800;
          font-size: 11px;
          display: flex;
          align-items: center;
          gap: 4px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.5);
          white-space: nowrap;
          transform: translate(-50%, -50%);
        ">
          <span>${emoji}</span> ${label}
        </div>
      `,
      iconSize: [60, 24],
      iconAnchor: [30, 12]
    });
  }

  function createJunctionIcon(label, isGreen) {
    const color = isGreen ? '#22C55E' : '#EF4444';
    return L.divIcon({
      className: 'custom-junc-marker',
      html: `
        <div style="
          background: #111827;
          border: 2px solid ${color};
          border-radius: 8px;
          padding: 3px 8px;
          font-weight: 800;
          font-size: 11px;
          color: white;
          box-shadow: 0 0 14px ${color};
          transform: translate(-50%, -50%);
        ">
          🚦 ${label}
        </div>
      `,
      iconSize: [80, 24],
      iconAnchor: [40, 12]
    });
  }

  function updateMapMarkers() {
    if (!mapInstance) return;

    // Ambulance Marker
    const ambPos = [state.ambulance.lat, state.ambulance.lng];
    if (!mapMarkers['amb']) {
      mapMarkers['amb'] = L.marker(ambPos, {
        icon: createCustomIcon('AMB01', true, false)
      }).addTo(mapInstance);
    } else {
      mapMarkers['amb'].setLatLng(ambPos);
    }

    // Vehicle Markers
    Object.values(state.vehicles).forEach(v => {
      const pos = [v.lat, v.lng];
      const isMe = v.id === state.myVehicleId;
      if (!mapMarkers[v.id]) {
        mapMarkers[v.id] = L.marker(pos, {
          icon: createCustomIcon(v.id + (isMe ? ' (YOU)' : ''), false, isMe)
        }).addTo(mapInstance);
      } else {
        mapMarkers[v.id].setLatLng(pos);
      }
    });

    // Junction Traffic Light Marker
    const juncPos = [state.junction.lat, state.junction.lng];
    const isGrn = state.junction.lights.approach_a ? state.junction.lights.approach_a.green : true;
    if (!junctionMarker) {
      junctionMarker = L.marker(juncPos, {
        icon: createJunctionIcon('JUNC_01', isGrn)
      }).addTo(mapInstance);
    } else {
      junctionMarker.setIcon(createJunctionIcon('JUNC_01', isGrn));
    }

    updateMapCorridor();
  }

  function updateMapCorridor() {
    if (!mapInstance) return;
    const ambLat = state.ambulance.lat;
    const ambLng = state.ambulance.lng;
    const points = [
      [ambLat - 0.002, ambLng],
      [ambLat, ambLng],
      [ambLat + 0.006, ambLng],
    ];

    const corridorColor = state.ambulance.isEmergency ? '#EF4444' : '#38BDF8';

    if (!corridorPolyline) {
      corridorPolyline = L.polyline(points, {
        color: corridorColor,
        weight: 4,
        opacity: 0.7,
        dashArray: '8, 8'
      }).addTo(mapInstance);
    } else {
      corridorPolyline.setLatLngs(points);
      corridorPolyline.setStyle({ color: corridorColor });
    }
  }

  function centerOnAmbulance() {
    if (!mapInstance) return;
    mapInstance.panTo([state.ambulance.lat, state.ambulance.lng], { animate: true });
    showToast('Centered on Ambulance');
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

    if (tabName === 'map') {
      setTimeout(() => {
        initMap();
        if (mapInstance) mapInstance.invalidateSize();
      }, 100);
    }

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

    // Emergency Toggle
    $('emergencyToggle').addEventListener('click', (e) => {
      state.ambulance.isEmergency = e.target.checked;
      showToast(`Emergency Mode: ${state.ambulance.isEmergency ? 'ON' : 'OFF'}`);
      recalculateAlert();
    });

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

    // Map Controls
    $('btnCenterAmbulance').addEventListener('click', centerOnAmbulance);
    $('btnToggleSimPlay').addEventListener('click', toggleSimulationPlayback);
    $('btnResetScenario').addEventListener('click', resetSimulationScenario);

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

            // Mark HUD as Test Mode
            if ($('hudModeBadge')) {
              $('hudModeBadge').textContent = 'TEST DATA / SIMULATED';
              $('hudModeBadge').style.background = 'rgba(234, 179, 8, 0.2)';
              $('hudModeBadge').style.color = '#facc15';
              $('hudModeBadge').style.borderColor = 'rgba(234, 179, 8, 0.4)';
            }

            // If scenario returned fleet telemetry, inject
            if (data.ambulance) {
              state.ambulance.lat = data.ambulance.lat;
              state.ambulance.lng = data.ambulance.lng;
              state.ambulance.lane = data.ambulance.lane;
            }
            if (data.vehicles) {
              Object.assign(state.vehicles, data.vehicles);
            }
            if (data.junction) {
              updateJunctionUI(data.junction);
            }

            // Trigger alert if targeted
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
        if ($('hudModeBadge')) {
          $('hudModeBadge').textContent = 'LIVE HARDWARE';
          $('hudModeBadge').style.background = 'rgba(34, 197, 94, 0.15)';
          $('hudModeBadge').style.color = '#4ade80';
          $('hudModeBadge').style.borderColor = 'rgba(34, 197, 94, 0.3)';
        }
        if ($('demoScenarioDetails')) {
          $('demoScenarioDetails').style.display = 'none';
        }
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
        state.ambulance.lane = laneNum;
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

  // --- Background Periodic Poller ---
  function startPeriodicSync() {
    setInterval(() => {
      pollCameraTelemetry();
      fetch('/api/junction/status')
        .then(r => r.json())
        .then(data => {
          if (data && data['JUNC_01']) {
            updateJunctionUI(data['JUNC_01']);
            renderHUD();
          }
        })
        .catch(() => {});
    }, 1500);
  }

  // --- Initial Boot ---
  window.addEventListener('DOMContentLoaded', () => {
    initEvents();
    renderHUD();
    syncDeviceAndAmbulanceHUD();
    startPeriodicSync();

    // Auto-connect to backend if on standard port
    setTimeout(() => {
      connectBackend();
    }, 400);
  });
})();
