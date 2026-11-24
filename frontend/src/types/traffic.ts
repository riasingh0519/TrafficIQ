export type CongestionLevel = "FREE" | "LIGHT" | "MODERATE" | "HEAVY";

export type SignalColor = "RED" | "YELLOW" | "GREEN";

export interface ShapDriver {
  feature: string;
  value: number;
  shap_value: number;
  impact: "INCREASES_CONGESTION" | "DECREASES_CONGESTION" | "NEUTRAL";
  importance_rank: number;
}

export interface MLPrediction {
  intersection_id: string;
  intersection_name: string;
  timestamp: string;
  predicted_congestion_level: CongestionLevel;
  confidence_scores: Record<CongestionLevel, number>;
  shap_feature_drivers: ShapDriver[];
  inference_latency_ms: number;
}

export interface SignalHead {
  approach: string;
  movement: "THROUGH_RIGHT" | "PROTECTED_LEFT";
  state: SignalColor;
  time_remaining_seconds: number;
}

export interface AdaptiveSignalControl {
  cycle_time: number;
  current_phase: number;
  current_phase_name: string;
  next_phase: number;
  next_phase_name: string;
  phase_elapsed_seconds: number;
  green_split_seconds: {
    phase_1: number;
    phase_2: number;
    phase_3: number;
    phase_4: number;
  };
  coordination_mode: string;
  signals: SignalHead[];
}

export interface PacketTelemetry {
  type: "BSM" | "MAP" | "SPaT" | "SRM_SSM";
  broadcast_status: "ACTIVE" | "STANDBY" | "DEGRADED";
  frequency_hz: number;
  packets_transmitted: number;
  packet_loss_rate_pct: number;
  last_payload_summary: string;
}

export interface V2IHardwareMetrics {
  rsu_id: string;
  rsu_status: string;
  rsu_temp_celsius: number;
  tx_power_dbm: number;
  active_obus_in_range: number;
  v2i_latency_ms: number;
  channel_occupancy_pct: number;
  dsrc_standard: string;
  packets: Record<string, PacketTelemetry>;
}

export interface ApproachFlow {
  approach: string;
  street_name: string;
  flow_rate_veh_min: number;
  queue_length_meters: number;
  avg_speed_kmh: number;
  occupancy_pct: number;
  active_vehicles_count: number;
}

export interface PhaseOptimizationSavings {
  delay_saved_seconds_per_cycle: number;
  emissions_reduction_kg: number;
  baseline_vs_adaptive_gain_pct: number;
  cumulative_fuel_saved_liters: number;
}

export interface IntersectionFlow {
  total_flow_rate_veh_min: number;
  projected_hourly_volume: number;
  congestion_metric_distance_meters: number;
  approaches: Record<string, ApproachFlow>;
  phase_optimization_savings: PhaseOptimizationSavings;
}

export interface SimulatedVehicle {
  vehicle_id: string;
  type: "sedan" | "suv" | "truck" | "bus" | "ev";
  approach: "NORTH" | "SOUTH" | "EAST" | "WEST";
  lane_id: string;
  x: number;
  y: number;
  speed_kmh: number;
  acceleration_mps2: number;
  distance_to_stopline_m: number;
  target_action: "THROUGH" | "LEFT" | "RIGHT";
  has_obu: boolean;
  v2i_connected: boolean;
  color: string;
}

export interface Simulation2DState {
  intersection_center: { x: number; y: number };
  road_boundaries: { x_min: number; x_max: number; y_min: number; y_max: number };
  active_vehicles_count: number;
  vehicles: SimulatedVehicle[];
  signal_heads: SignalHead[];
}

export interface SensorDeviceHealth {
  device_id: string;
  sensor_type: "TRAFFIC_CAMERA" | "3D_LIDAR" | "LOOP_DETECTOR" | "RSU_GATEWAY";
  status: "HEALTHY" | "DEGRADED" | "OFFLINE";
  coverage_pct: number;
  sampling_rate_hz: number;
  last_heartbeat_ms_ago: number;
  operational_notes: string;
}

export interface IoTSensorHealth {
  overall_health_score: number;
  devices: SensorDeviceHealth[];
}

export interface AnomalyAlert {
  alert_id: string;
  timestamp: string;
  type: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  message: string;
  source_component: string;
  active: boolean;
}

export interface CityCommandMetrics {
  city_general_index: number;
  hourly_traffic_volume: number;
  directional_travel_times_minutes: Record<string, number>;
  intersection_performance_index: number;
  level_of_service: "A" | "B" | "C" | "D" | "E" | "F";
  real_time_alerts: AnomalyAlert[];
}

export interface TrafficStreamPayload {
  intersection_id: string;
  intersection_name: string;
  timestamp: string;
  frame_sequence: number;
  ml_congestion_prediction: MLPrediction;
  adaptive_signal_control: AdaptiveSignalControl;
  v2i_hardware_metrics: V2IHardwareMetrics;
  intersection_flow: IntersectionFlow;
  simulation_2d_state: Simulation2DState;
  iot_sensor_health: IoTSensorHealth;
  city_command_metrics: CityCommandMetrics;
}

