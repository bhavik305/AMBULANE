# Graph Report - MINOR  (2026-10-28)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1255 nodes · 2462 edges · 80 communities (59 shown, 21 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 147 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ca378515`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 60
- Community 61
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 73

## God Nodes (most connected - your core abstractions)
1. `AmbulanceState` - 49 edges
2. `VehicleState` - 40 edges
3. `get_ws_manager()` - 30 edges
4. `initEvents()` - 28 edges
5. `DefaultMatchingEngine` - 26 edges
6. `WebSocketManager` - 25 edges
7. `JunctionService` - 23 edges
8. `RouteEngine` - 23 edges
9. `Win32Window` - 21 edges
10. `detect_lane()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `DeviceService` --uses--> `AmbulanceConfigRequest`  [INFERRED]
  backend/device_service.py → backend/models.py
- `JourneyService` --uses--> `AmbulanceConfigRequest`  [INFERRED]
  backend/journey_service.py → backend/models.py
- `DeviceService` --uses--> `DeviceRole`  [INFERRED]
  backend/device_service.py → backend/models.py
- `test_criterion_5_device_registration_and_role_authorization()` --uses--> `DeviceRole`  [INFERRED]
  backend/test_final_audit_suite.py → backend/models.py
- `test_device_registration_role_protection()` --uses--> `DeviceRole`  [INFERRED]
  backend/test_lane_matching_cases.py → backend/models.py

## Import Cycles
- None detected.

## Communities (80 total, 21 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (39): _activeAlert, ambulance, AppRole, backendUrl, connectBackend, _currentRole, currentTargetVehicle, disconnectBackend (+31 more)

### Community 1 - "Community 1"
Cohesion: 0.14
Nodes (46): attachMapToCurrentView(), calculateRoutePreview(), centerOnAmbulance(), centerOnMe(), connectBackend(), disconnectBackend(), fitRouteBounds(), getLeafletAmbulanceIcon() (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (17): audioplayers_darwin, Cocoa, device_info_plus, Flutter, FlutterMacOS, Foundation, AppDelegate, SceneDelegate (+9 more)

### Community 3 - "Community 3"
Cohesion: 0.10
Nodes (18): ambulance_websocket(), _handle_telemetry(), _serialize_state(), _handle_telemetry(), _serialize_state(), vehicle_websocket(), _fetch_status(), main() (+10 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (16): detect_lane(), _filter_lane_colors(), _fit_lane_lines(), generate_lane_overlay(), get_vehicle_tracker(), decode_frame(), extract_road_roi(), preprocess_frame() (+8 more)

### Community 5 - "Community 5"
Cohesion: 0.17
Nodes (18): DefaultMatchingEngine, filter_by_distance(), MatchingConfig, AmbulanceState, VehicleState, test_esp32_telemetry_flow(), test_criterion_7_normal_vehicle_matching(), test_criterion_8_stale_telemetry_protection() (+10 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (11): get_lane_model(), DeepLearningLaneModel, LaneDetectionModel, load_model(), list_demo_scenarios(), test_criterion_10_unauthorized_priority_request(), test_criterion_11_websocket_telemetry_exchange(), test_criterion_12_esp32_command_validation_and_ack() (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (15): start_journey(), stop_journey(), load_deterministic_scenario(), get_device_service(), dispatch_alerts_and_fleet(), get_matching_engine(), _parse_lane(), get_journey_service() (+7 more)

### Community 9 - "Community 9"
Cohesion: 0.10
Nodes (6): JourneyService, Corridor, Route, RouteEngine, RoutePoint, test_corridor_geometry_and_membership()

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (14): fl_register_plugins(), main(), first_frame_cb(), my_application_activate(), my_application_class_init(), my_application_dispose(), my_application_init(), my_application_local_command_line() (+6 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (24): _activeVehicleId, _alertController, _channel, _clearController, connect, _currentBaseUrl, currentUrl, disconnect (+16 more)

### Community 12 - "Community 12"
Cohesion: 0.06
Nodes (25): alertZoneMeters, _ambulance, baseLat, baseLng, calculateDistanceMeters, _degToRad, dispose, evaluateTargeting (+17 more)

### Community 13 - "Community 13"
Cohesion: 0.07
Nodes (27): ambulanceId, ambulanceLane, ambulanceLat, ambulanceLon, distanceMeters, emergencyState, etaSeconds, fromJson (+19 more)

### Community 14 - "Community 14"
Cohesion: 0.10
Nodes (4): VehicleCameraManager, test_camera_manager_lifecycle(), test_criterion_1_camera_still_image_interval(), test_criterion_2_camera_unavailable_handling()

### Community 15 - "Community 15"
Cohesion: 0.17
Nodes (3): update_ambulance_config(), AmbulanceConfigRequest, DeviceRole

### Community 16 - "Community 16"
Cohesion: 0.08
Nodes (25): dependencies, audioplayers, cupertino_icons, flutter, flutter_map, geolocator, google_fonts, http (+17 more)

### Community 17 - "Community 17"
Cohesion: 0.09
Nodes (4): a(), Ci(), l(), x()

### Community 18 - "Community 18"
Cohesion: 0.13
Nodes (7): register_device(), DeviceService, DeviceRegisterRequest, DeviceRegistration, test_criterion_5_device_registration_and_role_authorization(), test_criterion_6_ambulance_fixed_configured_lane_and_approach(), test_device_registration_role_protection()

### Community 19 - "Community 19"
Cohesion: 0.13
Nodes (5): JunctionService, JunctionState, LightAspects, test_criterion_13_conflicting_green_prevention(), test_criterion_14_physical_led_honest_hardware_status()

### Community 20 - "Community 20"
Cohesion: 0.08
Nodes (11): client(), test_app_config_returns_openstreetmap_and_osrm(), test_camera_status_and_lane_reporting(), test_device_role_registration(), test_frontend_dom_ids_and_no_google_maps(), test_frontend_static_assets_served(), test_journey_lifecycle_start_and_stop(), test_journey_route_calculation_endpoint() (+3 more)

### Community 21 - "Community 21"
Cohesion: 0.14
Nodes (4): wWinMain(), CreateAndAttachConsole(), GetCommandLineArguments(), Utf8FromUtf16()

### Community 22 - "Community 22"
Cohesion: 0.13
Nodes (8): calculate_route(), get_active_journey(), get_app_config(), _get_local_ip(), OSRMRouteEngine, RoutingError, test_osrm_mocked_failure_raises_error(), test_osrm_mocked_success()

### Community 23 - "Community 23"
Cohesion: 0.10
Nodes (19): accent, accentMuted, AppColors, background, border, borderSubtle, emergency, emergencyBg (+11 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (7): detect_image_format(), FrameResponse, LaneDetectionResult, process_frame(), upload_frame(), _create_sample_image(), test_camera_reception()

### Community 25 - "Community 25"
Cohesion: 0.14
Nodes (10): CameraAccessRequest, CameraConfigRequest, CameraSourceRequest, get_camera_preview(), get_camera_telemetry(), set_camera_source(), toggle_camera_access(), trigger_manual_capture() (+2 more)

### Community 26 - "Community 26"
Cohesion: 0.16
Nodes (6): EnableNonClientDpiScaling, Scale(), Win32Window::Win32Window(), WindowClassRegistrar, class_registered_, instance_

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (6): ambulance_ui_redirect(), app_ui_redirect(), health(), lifespan(), root(), status()

### Community 28 - "Community 28"
Cohesion: 0.12
Nodes (4): FlutterWindow, flutter_controller_, FlutterWindow::FlutterWindow(), project_

### Community 29 - "Community 29"
Cohesion: 0.16
Nodes (3): LaneFeatureNet, generate_synthetic_dataset(), train_and_export()

### Community 30 - "Community 30"
Cohesion: 0.15
Nodes (6): JunctionConfig, JunctionLights, SignalPriorityRequest, test_eta_triggered_priority_logic(), test_junction_websocket_and_telemetry_flow(), test_neural_lane_inference()

### Community 31 - "Community 31"
Cohesion: 0.12
Nodes (10): dispose, getCurrentLocation, _instance, _locationController, LocationService, onLocationChanged, _positionStream, requestPermission (+2 more)

### Community 32 - "Community 32"
Cohesion: 0.12
Nodes (12): AlertFeedbackService, dispose, _hasVibrator, init, _instance, _isActive, startAlert, stopAlert (+4 more)

### Community 33 - "Community 33"
Cohesion: 0.20
Nodes (4): bearing_deg(), create_default_route_engine(), haversine_distance_m(), normalize_heading()

### Community 34 - "Community 34"
Cohesion: 0.15
Nodes (9): build, _buildCard, _buildSwitchRow, createState, dispose, initState, SettingsScreen, _SettingsScreenState (+1 more)

### Community 35 - "Community 35"
Cohesion: 0.17
Nodes (7): build, createState, _currentIndex, main, MainNavigationShell, _MainNavigationShellState, _screens

### Community 36 - "Community 36"
Cohesion: 0.18
Nodes (7): build, _buildAmbulanceMarker, _buildVehicleMarker, createState, _mapController, OperatorMapScreen, _OperatorMapScreenState

### Community 37 - "Community 37"
Cohesion: 0.20
Nodes (5): JunctionConfigUpdate, ManualPriorityTrigger, report_junction_hardware_state(), trigger_manual_priority(), update_junction_config()

### Community 38 - "Community 38"
Cohesion: 0.20
Nodes (5): clean_singletons(), clean_manager(), test_vehicle_ws_and_alert_dispatch(), test_vehicle_ws_malformed_resilience(), reset_ws_manager()

### Community 39 - "Community 39"
Cohesion: 0.38
Nodes (10): connectWs(), fmt(), sendTelemetry(), setConn(), setGps(), show(), startGps(), stopGps() (+2 more)

### Community 40 - "Community 40"
Cohesion: 0.24
Nodes (11): at(), d(), ht(), Li(), m(), v(), ve(), W() (+3 more)

### Community 41 - "Community 41"
Cohesion: 0.24
Nodes (11): F(), G(), h(), j(), k(), ke(), me(), Oe() (+3 more)

### Community 42 - "Community 42"
Cohesion: 0.18
Nodes (10): background_color, description, display, icons, name, orientation, prefer_related_applications, short_name (+2 more)

### Community 43 - "Community 43"
Cohesion: 0.24
Nodes (4): Win32Window, child_content_, quit_on_close_, window_handle_

### Community 45 - "Community 45"
Cohesion: 0.27
Nodes (5): build, _buildAmbulanceApproachCard, _buildSafeCard, DriverHudScreen, AppState

### Community 46 - "Community 46"
Cohesion: 0.20
Nodes (6): accentColor, build, icon, title, unit, value

### Community 47 - "Community 47"
Cohesion: 0.20
Nodes (6): EmergencyAlert, alert, build, _buildMetric, onClearLaneLeft, onClearLaneRight

### Community 48 - "Community 48"
Cohesion: 0.20
Nodes (9): background_color, description, display, icons, name, orientation, short_name, start_url (+1 more)

### Community 50 - "Community 50"
Cohesion: 0.42
Nodes (6): AmbulanceTelemetry, VehicleTelemetry, test_ambulance_telemetry_coordinate_out_of_range(), test_ambulance_telemetry_invalid_speed_and_heading(), test_ambulance_telemetry_valid(), test_vehicle_telemetry_validation()

### Community 51 - "Community 51"
Cohesion: 0.22
Nodes (6): ambulanceLane, build, _buildSegment, currentLane, isAmbulanceApproaching, onLaneSelected

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (9): Ae(), be(), De(), ei(), Ie(), ii(), p(), pe() (+1 more)

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (9): bi(), c(), e(), hi(), Pi(), q(), Qe(), Ti() (+1 more)

### Community 54 - "Community 54"
Cohesion: 0.25
Nodes (3): get_ambulance_config(), get_device(), list_devices()

### Community 56 - "Community 56"
Cohesion: 0.25
Nodes (7): analyzer, errors, exclude, deprecated_member_use, include, linter, rules

### Community 58 - "Community 58"
Cohesion: 0.29
Nodes (7): Jt(), Le(), O(), Qt(), Re(), $t(), te()

### Community 63 - "Community 63"
Cohesion: 0.40
Nodes (4): LaneAwareEVASApp, AlertBannerWidget, LaneIndicatorWidget, TelemetryCard

### Community 65 - "Community 65"
Cohesion: 0.50
Nodes (5): i(), Mi(), ne(), e(), zi()

### Community 66 - "Community 66"
Cohesion: 0.67
Nodes (4): Je(), ni(), oi(), si()

### Community 67 - "Community 67"
Cohesion: 0.50
Nodes (3): Point, x, y

### Community 68 - "Community 68"
Cohesion: 0.50
Nodes (3): Size, height, width

## Knowledge Gaps
- **201 isolated node(s):** `_activeAlert`, `ambulance`, `AppRole`, `backendUrl`, `connectBackend` (+196 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 609 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_ws_manager()` connect `Community 8` to `Community 3`, `Community 4`, `Community 38`, `Community 7`, `Community 72`, `Community 9`, `Community 6`, `Community 14`, `Community 15`, `Community 20`, `Community 24`, `Community 27`, `Community 30`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `AmbulanceState` (e.g. with `_serialize_state()` and `trigger_manual_priority()`) actually correct?**
  _`AmbulanceState` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_activeAlert`, `ambulance`, `AppRole` to the rest of the system?**
  _201 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.04081632653061224 - nodes in this community are weakly interconnected._
- **Why does `AmbulanceState` connect `Community 5` to `Community 33`, `Community 3`, `Community 37`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 72`, `Community 15`, `Community 50`, `Community 19`, `Community 55`, `Community 60`, `Community 30`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `VehicleState` (e.g. with `_serialize_state()` and `DefaultMatchingEngine`) actually correct?**
  _`VehicleState` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.1445578231292517 - nodes in this community are weakly interconnected._