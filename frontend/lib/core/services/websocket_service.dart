import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/emergency_alert.dart';

class WebSocketService {
  WebSocketChannel? _channel;
  bool _isConnected = false;
  String _currentBaseUrl = 'ws://localhost:8000';
  String _activeVehicleId = 'V002';
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  bool _shouldReconnect = true;

  final _alertController = StreamController<EmergencyAlert>.broadcast();
  final _clearController = StreamController<void>.broadcast();
  final _fleetController = StreamController<Map<String, dynamic>>.broadcast();
  final _statusController = StreamController<bool>.broadcast();

  Stream<EmergencyAlert> get onEmergencyAlert => _alertController.stream;
  Stream<void> get onEmergencyClear => _clearController.stream;
  Stream<Map<String, dynamic>> get onFleetUpdate => _fleetController.stream;
  Stream<bool> get onConnectionStatus => _statusController.stream;

  bool get isConnected => _isConnected;
  String get currentUrl => _currentBaseUrl;

  String _formatEndpoint(String base, String vehicleId) {
    var url = base.trim();
    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    if (url.startsWith('http://')) {
      url = 'ws://${url.substring(7)}';
    } else if (url.startsWith('https://')) {
      url = 'wss://${url.substring(8)}';
    } else if (!url.startsWith('ws://') && !url.startsWith('wss://')) {
      url = 'ws://$url';
    }
    if (!url.contains('/ws/vehicle/')) {
      if (url.endsWith('/ws')) {
        url = '${url.substring(0, url.length - 3)}/ws/vehicle/$vehicleId';
      } else {
        url = '$url/ws/vehicle/$vehicleId';
      }
    }
    return url;
  }

  Future<void> connect(String url, {String vehicleId = 'V002'}) async {
    _currentBaseUrl = url;
    _activeVehicleId = vehicleId;
    _shouldReconnect = true;
    _reconnectTimer?.cancel();
    disconnect(preserveAutoReconnect: true);

    try {
      final endpoint = _formatEndpoint(url, vehicleId);
      final uri = Uri.parse(endpoint);
      _channel = WebSocketChannel.connect(uri);

      _channel!.stream.listen(
        (message) {
          if (!_isConnected) {
            _isConnected = true;
            _reconnectAttempts = 0;
            _statusController.add(true);
          }
          _handleMessage(message);
        },
        onError: (err) {
          _handleDisconnect();
        },
        onDone: () {
          _handleDisconnect();
        },
      );

      _isConnected = true;
      _reconnectAttempts = 0;
      _statusController.add(true);
    } catch (e) {
      _handleDisconnect();
    }
  }

  void _handleDisconnect() {
    _isConnected = false;
    _statusController.add(false);
    _channel = null;

    if (_shouldReconnect) {
      _reconnectAttempts++;
      final backoffSec = min(pow(2, _reconnectAttempts).toInt(), 10);
      _reconnectTimer?.cancel();
      _reconnectTimer = Timer(Duration(seconds: backoffSec), () {
        if (_shouldReconnect) {
          connect(_currentBaseUrl, vehicleId: _activeVehicleId);
        }
      });
    }
  }

  void disconnect({bool preserveAutoReconnect = false}) {
    if (!preserveAutoReconnect) {
      _shouldReconnect = false;
      _reconnectTimer?.cancel();
    }
    try {
      _channel?.sink.close();
    } catch (_) {}
    _channel = null;
    _isConnected = false;
    _statusController.add(false);
  }

  void _handleMessage(dynamic rawMessage) {
    try {
      final Map<String, dynamic> data = jsonDecode(rawMessage as String);
      final type = data['type'] as String?;

      if (type == 'emergency_alert' || (data.containsKey('to_id') && data['emergency_state'] == true)) {
        final alert = EmergencyAlert.fromJson(data);
        _alertController.add(alert);
      } else if (type == 'emergency_clear' || (data.containsKey('to_id') && data['emergency_state'] == false)) {
        _clearController.add(null);
      } else if (type == 'fleet_update' || data.containsKey('vehicles')) {
        _fleetController.add(data);
      }
    } catch (_) {}
  }

  void sendLocationUpdate({
    required String vehicleId,
    required double lat,
    required double lng,
    required double speedKmh,
    required double heading,
    required int lane,
  }) {
    if (!_isConnected || _channel == null) return;

    try {
      final payload = jsonEncode({
        'vehicle_id': vehicleId,
        'lat': lat,
        'lng': lng,
        'speed_kmh': speedKmh,
        'heading_deg': heading,
        'lane': lane.toString(),
        'lane_confidence': 0.95,
        'ts': DateTime.now().millisecondsSinceEpoch / 1000.0,
      });
      _channel!.sink.add(payload);
    } catch (_) {}
  }

  void dispose() {
    _shouldReconnect = false;
    _reconnectTimer?.cancel();
    disconnect();
    _alertController.close();
    _clearController.close();
    _fleetController.close();
    _statusController.close();
  }
}
