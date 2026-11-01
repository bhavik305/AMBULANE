# Graph Report - MINOR  (2026-11-01)

## Corpus Check
- 130 files · ~76,947 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 64 file(s) not represented in the graph (top: .xml 19, .xcconfig 8, (none) 7)

## Summary
- 1742 nodes · 3036 edges · 101 communities (81 shown, 20 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 151 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `406f8617`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- app_state.dart
- app.js
- GeneratedPluginRegistrant.swift
- json
- test_step8_lane_detection.py
- time
- WebSocketManager
- lane_detection.py
- demo_fixtures.py
- RouteEngine
- my_application.cc
- websocket_service.dart
- simulation_engine.dart
- emergency_alert.dart
- VehicleCameraManager
- models.py
- dependencies
- leaflet.js
- test_final_audit_suite.py
- JunctionService
- get_ws_manager
- utils.cpp
- test_step5_route_engine.py
- colors.dart
- main.py
- camera.py
- win32_window.cpp
- get
- FlutterWindow
- train_lane_model.py
- Tool Orchestration
- location_service.dart
- alert_sound_service.dart
- route_engine.py
- settings_screen.dart
- main.dart
- operator_map_screen.dart
- Verification Chains (by Language)
- Context Management
- ambulance.js
- m
- F
- web/manifest.json
- Win32Window
- TemporalLaneTracker
- test_phone_camera_road_service.py
- telemetry_card.dart
- alert_banner_widget.dart
- ambulance/manifest.json
- .MessageHandler
- The 20 Anti-Patterns
- lane_indicator_widget.dart
- p
- e
- Persona Protocol
- GRAVITAS Prompt Template
- analysis_options.yaml
- windows/flutter/generated_plugin_registrant.cc
- Jt
- Agent: General
- trigger_demo_scenario
- StatelessWidget
- widget_test.dart
- i
- oi
- Point
- Size
- list_demo_scenarios
- Agent: Verify
- The 7 Attack Vectors
- Model-Native Optimization Notes (Gemini tuned)
- FlutterActivity
- Memory Protocol
- Agent: Plan
- Subagent Patterns
- GRAVITAS -- Engineering Reliability Runtime
- Gravitas -- Verification Reference
- verify.sh
- Gravitas -- Delegation Reference
- Gravitas -- Interruption Recovery Reference
- Gravitas -- Task Contract Reference
- 1. Physical Hardware Setup (Production Firmware)
- Agent: Explore
- ESP32 Junction Traffic Signal Hardware Controller
- AMBULANE: Lane-Aware Intelligent Emergency Vehicle Alert & Clearance System
- Gravitas -- Model Routing Reference
- Gravitas -- Adaptive Reasoning Reference
- Gravitas -- Reconnaissance Reference
- evas_app
- coordinator.md
- run-checks.sh
- SESSION_FAILURES.md
- LaunchImage.imageset/README.md

## God Nodes (most connected - your core abstractions)
1. `AmbulanceState` - 49 edges
2. `VehicleState` - 42 edges
3. `get_ws_manager()` - 31 edges
4. `initEvents()` - 31 edges
5. `DefaultMatchingEngine` - 26 edges
6. `WebSocketManager` - 25 edges
7. `JunctionService` - 23 edges
8. `RouteEngine` - 23 edges
9. `get_device_service()` - 22 edges
10. `detect_lane()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `Simulation Firmware Design (`esp32_benchtwin_sim.ino`)` --references--> `AmbulanceTelemetry`  [INFERRED]
  firmware/README.md → backend/models.py
- `DeepLearningLaneModel` --uses--> `LaneFeatureNet`  [INFERRED]
  backend/ai/lane_model.py → backend/ai/model_def.py
- `_serialize_state()` --uses--> `AmbulanceState`  [INFERRED]
  backend/api/ambulance.py → backend/models.py
- `_handle_telemetry()` --uses--> `AmbulanceTelemetry`  [INFERRED]
  backend/api/ambulance.py → backend/models.py
- `upload_frame()` --uses--> `DeviceRegisterRequest`  [INFERRED]
  backend/api/camera.py → backend/models.py

## Import Cycles
- None detected.

## Communities (101 total, 20 thin omitted)

### Community 0 - "app_state.dart"
Cohesion: 0.04
Nodes (39): _activeAlert, ambulance, AppRole, backendUrl, connectBackend, _currentRole, currentTargetVehicle, disconnectBackend (+31 more)

### Community 1 - "app.js"
Cohesion: 0.14
Nodes (50): attachMapToCurrentView(), calculateRoutePreview(), captureAndAnalyzeStillPhoto(), centerOnAmbulance(), centerOnMe(), connectBackend(), disconnectBackend(), fitRouteBounds() (+42 more)

### Community 2 - "GeneratedPluginRegistrant.swift"
Cohesion: 0.06
Nodes (17): audioplayers_darwin, Cocoa, device_info_plus, Flutter, FlutterMacOS, Foundation, AppDelegate, SceneDelegate (+9 more)

### Community 3 - "json"
Cohesion: 0.07
Nodes (25): count_source_files(), detect_language(), main(), suggest_budget(), imported_plugin_names(), main(), sha256(), main() (+17 more)

### Community 4 - "test_step8_lane_detection.py"
Cohesion: 0.13
Nodes (14): detect_lane(), decode_frame(), extract_road_roi(), preprocess_frame(), _create_sample_road_frame(), test_criterion_3_ml_inference_on_real_image(), test_criterion_4_lane_unknown_on_occluded_image(), test_direct_process_frame_with_map_fusion() (+6 more)

### Community 5 - "time"
Cohesion: 0.09
Nodes (18): DefaultMatchingEngine, MatchingConfig, MatchResult, AmbulanceState, VehicleState, test_criterion_7_normal_vehicle_matching(), test_criterion_8_stale_telemetry_protection(), test_ambulance_invalid_coordinates_handled_safely() (+10 more)

### Community 7 - "lane_detection.py"
Cohesion: 0.11
Nodes (9): _filter_lane_colors(), _fit_lane_lines(), generate_lane_overlay(), get_lane_model(), DeepLearningLaneModel, LaneDetectionModel, load_model(), test_neural_lane_inference() (+1 more)

### Community 8 - "demo_fixtures.py"
Cohesion: 0.06
Nodes (17): get_all_junctions(), junction_websocket(), JunctionConfigUpdate, ManualPriorityTrigger, report_junction_hardware_state(), trigger_manual_priority(), update_junction_config(), list_demo_scenarios() (+9 more)

### Community 9 - "RouteEngine"
Cohesion: 0.10
Nodes (7): JourneyService, ActiveJourney, StartJourneyRequest, Corridor, Route, RouteEngine, test_corridor_geometry_and_membership()

### Community 10 - "my_application.cc"
Cohesion: 0.08
Nodes (14): fl_register_plugins(), main(), first_frame_cb(), my_application_activate(), my_application_class_init(), my_application_dispose(), my_application_init(), my_application_local_command_line() (+6 more)

### Community 11 - "websocket_service.dart"
Cohesion: 0.06
Nodes (24): _activeVehicleId, _alertController, _channel, _clearController, connect, _currentBaseUrl, currentUrl, disconnect (+16 more)

### Community 12 - "simulation_engine.dart"
Cohesion: 0.06
Nodes (25): alertZoneMeters, _ambulance, baseLat, baseLng, calculateDistanceMeters, _degToRad, dispose, evaluateTargeting (+17 more)

### Community 13 - "emergency_alert.dart"
Cohesion: 0.07
Nodes (27): ambulanceId, ambulanceLane, ambulanceLat, ambulanceLon, distanceMeters, emergencyState, etaSeconds, fromJson (+19 more)

### Community 14 - "VehicleCameraManager"
Cohesion: 0.09
Nodes (4): VehicleCameraManager, test_camera_manager_lifecycle(), test_criterion_1_camera_still_image_interval(), test_criterion_2_camera_unavailable_handling()

### Community 15 - "models.py"
Cohesion: 0.13
Nodes (9): _handle_telemetry(), _serialize_state(), vehicle_websocket(), AmbulanceTelemetry, VehicleTelemetry, test_ambulance_telemetry_coordinate_out_of_range(), test_ambulance_telemetry_invalid_speed_and_heading(), test_ambulance_telemetry_valid() (+1 more)

### Community 16 - "dependencies"
Cohesion: 0.08
Nodes (25): dependencies, audioplayers, cupertino_icons, flutter, flutter_map, geolocator, google_fonts, http (+17 more)

### Community 17 - "leaflet.js"
Cohesion: 0.09
Nodes (4): a(), Ci(), l(), x()

### Community 18 - "test_final_audit_suite.py"
Cohesion: 0.07
Nodes (18): get_ambulance_config(), get_device(), list_devices(), register_device(), update_ambulance_config(), DeviceService, get_device_service(), AmbulanceConfigRequest (+10 more)

### Community 19 - "JunctionService"
Cohesion: 0.10
Nodes (9): JunctionService, JunctionConfig, JunctionLights, JunctionState, LightAspects, SignalPriorityRequest, test_criterion_13_conflicting_green_prevention(), test_criterion_14_physical_led_honest_hardware_status() (+1 more)

### Community 20 - "get_ws_manager"
Cohesion: 0.05
Nodes (20): clean_singletons(), test_junction_websocket_and_telemetry_flow(), client(), test_app_config_returns_openstreetmap_and_osrm(), test_camera_status_and_lane_reporting(), test_device_role_registration(), test_frontend_dom_ids_and_no_google_maps(), test_frontend_static_assets_served() (+12 more)

### Community 21 - "utils.cpp"
Cohesion: 0.14
Nodes (4): wWinMain(), CreateAndAttachConsole(), GetCommandLineArguments(), Utf8FromUtf16()

### Community 22 - "test_step5_route_engine.py"
Cohesion: 0.11
Nodes (8): calculate_route(), get_active_journey(), get_app_config(), _get_local_ip(), OSRMRouteEngine, RoutingError, test_osrm_mocked_failure_raises_error(), test_osrm_mocked_success()

### Community 23 - "colors.dart"
Cohesion: 0.10
Nodes (19): accent, accentMuted, AppColors, background, border, borderSubtle, emergency, emergencyBg (+11 more)

### Community 24 - "main.py"
Cohesion: 0.15
Nodes (3): lifespan(), create_default_route_engine(), test_esp32_telemetry_flow()

### Community 25 - "camera.py"
Cohesion: 0.10
Nodes (15): CameraAccessRequest, CameraConfigRequest, CameraSourceRequest, detect_image_format(), FrameResponse, get_camera_preview(), get_camera_telemetry(), LaneDetectionResult (+7 more)

### Community 26 - "win32_window.cpp"
Cohesion: 0.16
Nodes (6): EnableNonClientDpiScaling, Scale(), Win32Window::Win32Window(), WindowClassRegistrar, class_registered_, instance_

### Community 27 - "get"
Cohesion: 0.22
Nodes (5): ambulance_ui_redirect(), app_ui_redirect(), health(), root(), status()

### Community 28 - "FlutterWindow"
Cohesion: 0.12
Nodes (4): FlutterWindow, flutter_controller_, FlutterWindow::FlutterWindow(), project_

### Community 29 - "train_lane_model.py"
Cohesion: 0.16
Nodes (3): LaneFeatureNet, generate_synthetic_dataset(), train_and_export()

### Community 30 - "Tool Orchestration"
Cohesion: 0.06
Nodes (33): 1. Parallel by Default, 2. Tool Selection Hierarchy, 3. Never Retry Verbatim, 4. Confirm Before Destructive Actions, After implementation, After write, Always capture output, Always read before write (+25 more)

### Community 31 - "location_service.dart"
Cohesion: 0.12
Nodes (10): dispose, getCurrentLocation, _instance, _locationController, LocationService, onLocationChanged, _positionStream, requestPermission (+2 more)

### Community 32 - "alert_sound_service.dart"
Cohesion: 0.12
Nodes (12): AlertFeedbackService, dispose, _hasVibrator, init, _instance, _isActive, startAlert, stopAlert (+4 more)

### Community 33 - "route_engine.py"
Cohesion: 0.11
Nodes (10): start_journey(), stop_journey(), get_journey_service(), filter_by_distance(), StopJourneyRequest, bearing_deg(), haversine_distance_m(), normalize_heading() (+2 more)

### Community 34 - "settings_screen.dart"
Cohesion: 0.12
Nodes (14): build, build, _buildAmbulanceApproachCard, _buildSafeCard, build, _buildCard, _buildSwitchRow, createState (+6 more)

### Community 35 - "main.dart"
Cohesion: 0.18
Nodes (6): createState, _currentIndex, main, MainNavigationShell, _MainNavigationShellState, _screens

### Community 36 - "operator_map_screen.dart"
Cohesion: 0.17
Nodes (7): build, _buildAmbulanceMarker, _buildVehicleMarker, createState, _mapController, OperatorMapScreen, _OperatorMapScreenState

### Community 37 - "Verification Chains (by Language)"
Cohesion: 0.07
Nodes (27): Baseline (before implementation), C#, Edge Case Matrix, Evidence Format (cite verbatim), Evidence Requirements, Go, Issuing VERDICT: FAIL, Issuing VERDICT: PASS (+19 more)

### Community 38 - "Context Management"
Cohesion: 0.08
Nodes (25): Context Budgeting, Context Hygiene Rules, Context Management, Context Structure (by Task Size), Cross-session continuity, Don't pass:, Large task (full codebase, 200K–1M tokens), Long Session Management (+17 more)

### Community 39 - "ambulance.js"
Cohesion: 0.38
Nodes (10): connectWs(), fmt(), sendTelemetry(), setConn(), setGps(), show(), startGps(), stopGps() (+2 more)

### Community 40 - "m"
Cohesion: 0.24
Nodes (11): at(), d(), ht(), Li(), m(), v(), ve(), W() (+3 more)

### Community 41 - "F"
Cohesion: 0.24
Nodes (11): F(), G(), h(), j(), k(), ke(), me(), Oe() (+3 more)

### Community 42 - "web/manifest.json"
Cohesion: 0.18
Nodes (10): background_color, description, display, icons, name, orientation, prefer_related_applications, short_name (+2 more)

### Community 43 - "Win32Window"
Cohesion: 0.24
Nodes (4): Win32Window, child_content_, quit_on_close_, window_handle_

### Community 44 - "TemporalLaneTracker"
Cohesion: 0.17
Nodes (3): get_vehicle_tracker(), TemporalLaneTracker, test_temporal_lane_tracker()

### Community 45 - "test_phone_camera_road_service.py"
Cohesion: 0.11
Nodes (6): get_road_service(), RoadAttributes, RoadService, test_road_service_fusion_camera_only_when_map_missing(), test_road_service_fusion_map_and_camera(), test_road_service_fusion_unknown_when_visibility_insufficient()

### Community 46 - "telemetry_card.dart"
Cohesion: 0.20
Nodes (6): accentColor, build, icon, title, unit, value

### Community 47 - "alert_banner_widget.dart"
Cohesion: 0.20
Nodes (6): EmergencyAlert, alert, build, _buildMetric, onClearLaneLeft, onClearLaneRight

### Community 48 - "ambulance/manifest.json"
Cohesion: 0.20
Nodes (9): background_color, description, display, icons, name, orientation, short_name, start_url (+1 more)

### Community 50 - "The 20 Anti-Patterns"
Cohesion: 0.08
Nodes (23): 10. Preamble Padding, 11. Over-scoping, 12. Quiet Workarounds, 13. Scope Narrowing Without Disclosure, 14. Post-hoc Rationalization, 15. False Precision, 16. Context Window Gaslighting, 17. Tool Trust Abuse (+15 more)

### Community 51 - "lane_indicator_widget.dart"
Cohesion: 0.22
Nodes (6): ambulanceLane, build, _buildSegment, currentLane, isAmbulanceApproaching, onLaneSelected

### Community 52 - "p"
Cohesion: 0.22
Nodes (9): Ae(), be(), De(), ei(), Ie(), ii(), p(), pe() (+1 more)

### Community 53 - "e"
Cohesion: 0.22
Nodes (9): bi(), c(), e(), hi(), Pi(), q(), Qe(), Ti() (+1 more)

### Community 54 - "Persona Protocol"
Cohesion: 0.08
Nodes (23): After Tool Calls, Always open with:, Autonomous Operation Voice, Core Voice, Disagreement Protocol, Do, Don't, Examples (+15 more)

### Community 55 - "GRAVITAS Prompt Template"
Cohesion: 0.09
Nodes (21): Assembling the Full Prompt, Bug Fix, Example: Bug Fix Task, Explore Dispatch, Feature Addition, For a conditional subagent, For Long Sessions (after context compression), GRAVITAS Prompt Template (+13 more)

### Community 56 - "analysis_options.yaml"
Cohesion: 0.25
Nodes (7): analyzer, errors, exclude, deprecated_member_use, include, linter, rules

### Community 58 - "Jt"
Cohesion: 0.29
Nodes (7): Jt(), Le(), O(), Qt(), Re(), $t(), te()

### Community 60 - "Agent: General"
Cohesion: 0.10
Nodes (20): Agent: General, Always run the full chain for the language, Before Writing Any Code, Cite verbatim, Code Standards, Compare to baseline, Don't over-engineer, Execution Protocol (+12 more)

### Community 63 - "StatelessWidget"
Cohesion: 0.33
Nodes (5): LaneAwareEVASApp, DriverHudScreen, AlertBannerWidget, LaneIndicatorWidget, TelemetryCard

### Community 65 - "i"
Cohesion: 0.50
Nodes (5): i(), Mi(), ne(), e(), zi()

### Community 66 - "oi"
Cohesion: 0.67
Nodes (4): Je(), ni(), oi(), si()

### Community 67 - "Point"
Cohesion: 0.50
Nodes (3): Point, x, y

### Community 68 - "Size"
Cohesion: 0.50
Nodes (3): Size, height, width

### Community 70 - "Agent: Verify"
Cohesion: 0.10
Nodes (20): 1. Coverage check, 2. Test quality check, 3. Security spot-check (if auth/input/db code changed), Adversarial Test Review, Agent: Verify, Edge Case Matrix, Escalation, Full Verification Chain (+12 more)

### Community 71 - "The 7 Attack Vectors"
Cohesion: 0.10
Nodes (19): Adversarial Critique Protocol, Auth Middleware Order, Common Failure Patterns (Historical), Critique Output Format, Critique Thresholds, DB Migration Without Transaction, Import Style Breaks Tree Shaking, Test Assertion Mismatch (+11 more)

### Community 72 - "Model-Native Optimization Notes (Gemini tuned)"
Cohesion: 0.12
Nodes (16): 10. Integration with GRAVITAS Tiers, 11. Portability Notes (tuned on Gemini, re-validate elsewhere), 12. Anti-patterns for Gemini, 1. Adaptive Reasoning, 2. Outcome-First Prompting, 3. Few-Shot Examples — Gemini's Strongest Lever, 4. Markdown Structure Over XML, 5. Context Window — Large, But Use Wisely (+8 more)

### Community 80 - "Memory Protocol"
Cohesion: 0.12
Nodes (16): Before saving, Cross-Session Continuity Pattern, Don't save, `feedback` — What the user has corrected, Layer 1 — Session Memory (in-session, ephemeral), Layer 2 — Project Memory (cross-session, persistent), Memory Index — GRAVITAS_MEMORY.md, Memory Lifecycle (+8 more)

### Community 81 - "Agent: Plan"
Cohesion: 0.12
Nodes (15): Agent: Plan, Calibrated Reasoning Phase, Complexity Heuristics, Plan Agent Rules, Plan Templates, Planning Process, Step 1 — Absorb Everything Explore Found, Step 2 — Extended Research (for Tier 1+) (+7 more)

### Community 82 - "Subagent Patterns"
Cohesion: 0.12
Nodes (15): Agent Communication Rules, Anti-Patterns, Core Decision: Spawn or Act Directly?, Dispatching an Agent, Example Dispatch: Explore, Example Dispatch: General, Example Dispatch: Verify, Pattern 1: Sequential Pipeline (+7 more)

### Community 83 - "GRAVITAS -- Engineering Reliability Runtime"
Cohesion: 0.14
Nodes (13): DECISION RECORDS, DEEP REFERENCES, DELEGATION, EFFORT PROFILES, Evidence, GRAVITAS -- Engineering Reliability Runtime, MODES, OUTPUT FORMAT (+5 more)

### Community 84 - "Gravitas -- Verification Reference"
Cohesion: 0.17
Nodes (11): Adversarial Edge Cases (strict/security work), Completion Gating, Evidence Requirements by Claim, Gravitas -- Verification Reference, Regression Baseline, Reproduction-First Debugging, Requirement-Evidence States, Scope-Appropriate Verification (+3 more)

### Community 85 - "verify.sh"
Cohesion: 0.58
Nodes (10): log_fail(), log_info(), log_pass(), log_warn(), verify.sh script, detect_language(), verify_go(), verify_python() (+2 more)

### Community 86 - "Gravitas -- Delegation Reference"
Cohesion: 0.20
Nodes (9): Budget Profiles and Delegation, Gravitas -- Delegation Reference, Impact Auditor, Investigator, Simple Task Rule, Spawn Decision Record, The Principle, Three Conditional Roles (+1 more)

### Community 87 - "Gravitas -- Interruption Recovery Reference"
Cohesion: 0.20
Nodes (9): Circuit Breaker, Evidence Ledger: .gravitas/sessions/<task-id>/evidence.jsonl, Failure Log: .gravitas/sessions/<task-id>/failures.jsonl, Gravitas -- Interruption Recovery Reference, Recovery Protocol, State File: .gravitas/sessions/<task-id>/state.json, The Problem, The Solution (+1 more)

### Community 88 - "Gravitas -- Task Contract Reference"
Cohesion: 0.20
Nodes (9): Acceptance Criteria, Action Lock, Allowed Write Scope, Gravitas -- Task Contract Reference, Interruption Recovery, Modes, Policy Dimensions, Schema (+1 more)

### Community 89 - "1. Physical Hardware Setup (Production Firmware)"
Cohesion: 0.20
Nodes (9): 1. Physical Hardware Setup (Production Firmware), 2. BenchTwin Simulation Setup, Board Selection & Flashing, Cause of BenchTwin Error, ESP32 Ambulance Telemetry Firmware & BenchTwin Simulation, Hardware Wiring, Required Arduino Libraries (Physical ESP32), Running in BenchTwin (+1 more)

### Community 90 - "Agent: Explore"
Cohesion: 0.22
Nodes (8): Agent: Explore, Exploration Depth by Tier, Explore Rules, MANDATORY: Full Codebase Map Phase, Phase 2 — Target Deep Dive (parallel batch), Phase 3 — Dependency and Impact Analysis (parallel batch), Phase 4 — Critical Analysis, What to Report

### Community 91 - "ESP32 Junction Traffic Signal Hardware Controller"
Cohesion: 0.22
Nodes (8): 1. Tabletop Hardware Pinout & Wiring, 2. Safety State Machine & Interlocks, 3. Communication Protocol, 4. Compilation & Flashing Instructions, ESP32 Junction Traffic Signal Hardware Controller, Hardware Safety Interlocks:, Priority Request (`Backend -> ESP32` over `/ws/junction/{junction_id}`):, Telemetry Packet (`ESP32 -> Backend`):

### Community 92 - "AMBULANE: Lane-Aware Intelligent Emergency Vehicle Alert & Clearance System"
Cohesion: 0.22
Nodes (8): 1. Install Dependencies, 2. Run Test Suites, 3. Launch Backend, AMBULANE: Lane-Aware Intelligent Emergency Vehicle Alert & Clearance System, Directory Structure, Hardware Configuration (Ambulance Unit), Quickstart, System Architecture

### Community 93 - "Gravitas -- Model Routing Reference"
Cohesion: 0.25
Nodes (7): Available Models in Antigravity (example snapshot, September 2026 -- verify), Conceptual Routing Policy, Gravitas -- Model Routing Reference, GravitasBench Will Measure This, Quota-Aware Routing, The Principle, When Native Antigravity Features Are Better

### Community 94 - "Gravitas -- Adaptive Reasoning Reference"
Cohesion: 0.25
Nodes (7): Gravitas -- Adaptive Reasoning Reference, Reasoning by Scenario, Reasoning Depth Formula, Red Flags for Over-Reasoning, Red Flags for Under-Reasoning, Selective CoT, The Core Principle

### Community 95 - "Gravitas -- Reconnaissance Reference"
Cohesion: 0.25
Nodes (7): Dependency-Directed Recon, Extended Recon (unfamiliar codebase or high fan-out), Gravitas -- Reconnaissance Reference, Recon Completeness Check, Recon Principle, Standard Recon (Tier 1 tasks), What Not to Do

## Knowledge Gaps
- **201 isolated node(s):** `AppColors`, `background`, `surface`, `surfaceElevated`, `accent` (+196 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 964 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AmbulanceState` connect `time` to `route_engine.py`, `json`, `WebSocketManager`, `demo_fixtures.py`, `RouteEngine`, `models.py`, `test_final_audit_suite.py`, `JunctionService`, `get_ws_manager`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `AmbulanceState` (e.g. with `_serialize_state()` and `trigger_manual_priority()`) actually correct?**
  _`AmbulanceState` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `AppColors`, `background`, `surface` to the rest of the system?**
  _201 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `app_state.dart` be split into smaller, more focused modules?**
  _Cohesion score 0.04081632653061224 - nodes in this community are weakly interconnected._
- **Why does `get_ws_manager()` connect `get_ws_manager` to `route_engine.py`, `json`, `test_step8_lane_detection.py`, `WebSocketManager`, `demo_fixtures.py`, `RouteEngine`, `test_phone_camera_road_service.py`, `VehicleCameraManager`, `models.py`, `main.py`, `camera.py`, `get`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `VehicleState` (e.g. with `upload_frame()` and `_serialize_state()`) actually correct?**
  _`VehicleState` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Should `app.js` be split into smaller, more focused modules?**
  _Cohesion score 0.13570391872278664 - nodes in this community are weakly interconnected._