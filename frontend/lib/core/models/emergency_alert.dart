class EmergencyAlert {
  final String toId;
  final String ambulanceId;
  final double ambulanceLat;
  final double ambulanceLon;
  final double distanceMeters;
  final int etaSeconds;
  final bool emergencyState;
  final String messageCode;
  final String humanMessage;
  final int ambulanceLane;
  final DateTime timestamp;

  const EmergencyAlert({
    required this.toId,
    this.ambulanceId = 'AMB01',
    required this.ambulanceLat,
    required this.ambulanceLon,
    required this.distanceMeters,
    required this.etaSeconds,
    required this.emergencyState,
    this.messageCode = 'EMERGENCY_ALERT_CLEAR_LANE',
    this.humanMessage = 'Emergency vehicle approaching. Please safely clear the path when safe and legal.',
    this.ambulanceLane = 2,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() {
    return {
      'to_id': toId,
      'ambulance_id': ambulanceId,
      'ambulance_lat': ambulanceLat,
      'ambulance_lon': ambulanceLon,
      'distance': distanceMeters,
      'eta': etaSeconds,
      'emergency_state': emergencyState,
      'message_code': messageCode,
      'human_message': humanMessage,
      'ambulance_lane': ambulanceLane,
      'timestamp': timestamp.toIso8601String(),
    };
  }

  factory EmergencyAlert.fromJson(Map<String, dynamic> json) {
    return EmergencyAlert(
      toId: (json['to_id'] ?? json['toId'] ?? '') as String,
      ambulanceId: (json['ambulance_id'] ?? json['ambulanceId'] ?? 'AMB01') as String,
      ambulanceLat: ((json['ambulance_lat'] ?? json['ambulanceLat'] ?? json['lat'] ?? 0.0) as num).toDouble(),
      ambulanceLon: ((json['ambulance_lon'] ?? json['ambulanceLon'] ?? json['lng'] ?? 0.0) as num).toDouble(),
      distanceMeters: ((json['distance'] ?? json['distance_m'] ?? 0.0) as num).toDouble(),
      etaSeconds: ((json['eta'] ?? json['eta_s'] ?? json['time_to_encounter_s'] ?? 0) as num).toInt(),
      emergencyState: (json['emergency_state'] ?? json['emergency'] ?? true) as bool,
      messageCode: (json['message_code'] ?? 'EMERGENCY_ALERT') as String,
      humanMessage: (json['human_message'] ??
          'Emergency vehicle approaching. Please safely clear the path when safe and legal.') as String,
      ambulanceLane: ((json['ambulance_lane'] ?? json['lane'] ?? 2) as num).toInt(),
      timestamp: json['timestamp'] != null
          ? DateTime.tryParse(json['timestamp'].toString()) ?? DateTime.now()
          : DateTime.now(),
    );
  }
}
