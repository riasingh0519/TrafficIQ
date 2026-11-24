from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime

# ==========================================
# 1. ML Inference Schemas
# ==========================================

class TrafficSensorInput(BaseModel):
    vehicle_flow_rate: float = Field(..., ge=0.0, le=200.0, description="Vehicles per minute across all approaches (5-65 typical)")
    average_speed_kmh: float = Field(..., ge=0.0, le=150.0, description="Average approach speed in km/h")
    occupancy_rate: float = Field(..., ge=0.0, le=1.0, description="Lane occupancy ratio from loop/vision detectors (0.0 to 1.0)")
    queue_length_meters: float = Field(..., ge=0.0, le=1000.0, description="Cumulative or max queue length in meters")
    weather_factor: float = Field(0.0, ge=0.0, le=1.0, description="Weather severity factor: 0.0=Clear, 0.3=Rain, 0.7=Snow/Ice")
    peak_hour: int = Field(0, ge=0, le=1, description="Binary flag indicating whether current time is peak commuting hour (0 or 1)")
    incident_flag: int = Field(0, ge=0, le=1, description="Flag for road blockages, stalls, or accidents (0 or 1)")

class ShapFeatureDriver(BaseModel):
    feature: str = Field(..., description="Feature name")
    value: float = Field(..., description="Observed input value")
    shap_value: float = Field(..., description="SHAP attribution value for the predicted class")
    impact: Literal["INCREASES_CONGESTION", "DECREASES_CONGESTION", "NEUTRAL"]
    importance_rank: int = Field(..., description="Rank of importance (1 is highest impact)")

class PredictionResponse(BaseModel):
    intersection_id: str = "SC-INT-74"
    intersection_name: str = "Oak Street & 5th Avenue"
    timestamp: datetime
    predicted_congestion_level: Literal["FREE", "LIGHT", "MODERATE", "HEAVY"]
    confidence_scores: Dict[str, float]
    shap_feature_drivers: List[ShapFeatureDriver]
    inference_latency_ms: float

# ==========================================
# 2. V2I Hardware & Telematics Metrics
# ==========================================

class PacketTelemetry(BaseModel):
    type: Literal["BSM", "MAP", "SPaT", "SRM_SSM"]
    broadcast_status: Literal["ACTIVE", "STANDBY", "DEGRADED"]
    frequency_hz: float
    packets_transmitted: int
    packet_loss_rate_pct: float
    last_payload_summary: str

class V2IHardwareMetrics(BaseModel):
    rsu_id: str = "RSU-SC74-01"
    rsu_status: Literal["ONLINE", "STANDBY", "DEGRADED", "OFFLINE"]
    rsu_temp_celsius: float
    tx_power_dbm: float
    active_obus_in_range: int
    v2i_latency_ms: float
    channel_occupancy_pct: float
    dsrc_standard: str = "IEEE 802.11p / C-V2X Rel-16"
    packets: Dict[str, PacketTelemetry]

# ==========================================
# 3. Intersection Flow & Optimization
# ==========================================

class ApproachFlow(BaseModel):
    approach: Literal["NORTHBOUND", "SOUTHBOUND", "EASTBOUND", "WESTBOUND"]
    street_name: str
    flow_rate_veh_min: float
    queue_length_meters: float
    avg_speed_kmh: float
    occupancy_pct: float
    active_vehicles_count: int

class PhaseOptimizationSavings(BaseModel):
    delay_saved_seconds_per_cycle: float
    emissions_reduction_kg: float
    baseline_vs_adaptive_gain_pct: float
    cumulative_fuel_saved_liters: float

class IntersectionFlowMetrics(BaseModel):
    total_flow_rate_veh_min: float
    projected_hourly_volume: int
    congestion_metric_distance_meters: float
    approaches: Dict[str, ApproachFlow]
    phase_optimization_savings: PhaseOptimizationSavings

# ==========================================
# 4. Adaptive Signal Controller State
# ==========================================

class SignalLightState(BaseModel):
    approach: str
    movement: Literal["THROUGH_RIGHT", "PROTECTED_LEFT"]
    state: Literal["RED", "YELLOW", "GREEN"]
    time_remaining_seconds: int

class AdaptiveSignalState(BaseModel):
    cycle_time: int = Field(..., ge=60, le=130, description="Dynamic cycle time in seconds (60-130s)")
    current_phase: int = Field(..., ge=1, le=4, description="Active phase number (1 to 4)")
    current_phase_name: str
    next_phase: int = Field(..., ge=1, le=4, description="Next scheduled phase number")
    next_phase_name: str
    phase_elapsed_seconds: int
    green_split_seconds: Dict[str, int]
    coordination_mode: Literal["ADAPTIVE_DENSITY_WEBSTER", "EMERGENCY_PREEMPTION", "MANUAL_OVERRIDE"]
    signals: List[SignalLightState]

# ==========================================
# 5. 2D Simulation State
# ==========================================

class SimulatedVehicle(BaseModel):
    vehicle_id: str
    type: Literal["sedan", "suv", "truck", "bus", "ev"]
    approach: Literal["NORTH", "SOUTH", "EAST", "WEST"]
    lane_id: str
    x: float = Field(..., description="X coordinate in meters relative to intersection center (0,0)")
    y: float = Field(..., description="Y coordinate in meters relative to intersection center (0,0)")
    speed_kmh: float
    acceleration_mps2: float
    distance_to_stopline_m: float
    target_action: Literal["THROUGH", "LEFT", "RIGHT"]
    has_obu: bool
    v2i_connected: bool
    color: str

class Simulation2DState(BaseModel):
    intersection_center: Dict[str, float] = {"x": 0.0, "y": 0.0}
    road_boundaries: Dict[str, float] = {"x_min": -120.0, "x_max": 120.0, "y_min": -120.0, "y_max": 120.0}
    active_vehicles_count: int
    vehicles: List[SimulatedVehicle]
    signal_heads: List[SignalLightState]

# ==========================================
# 6. IoT Sensor Health Metrics
# ==========================================

class SensorDeviceHealth(BaseModel):
    device_id: str
    sensor_type: Literal["TRAFFIC_CAMERA", "3D_LIDAR", "LOOP_DETECTOR", "RSU_GATEWAY"]
    status: Literal["HEALTHY", "DEGRADED", "OFFLINE"]
    coverage_pct: float
    sampling_rate_hz: float
    last_heartbeat_ms_ago: int
    operational_notes: str

class IoTSensorHealth(BaseModel):
    overall_health_score: float = Field(..., ge=0.0, le=100.0)
    devices: List[SensorDeviceHealth]

# ==========================================
# 7. City Command Metrics & Alerts
# ==========================================

class AnomalyAlert(BaseModel):
    alert_id: str
    timestamp: datetime
    type: Literal["HEAVY_CONGESTION", "SENSOR_SPIKE", "SHOCKWAVE_DETECTED", "EMERGENCY_PREEMPTION", "V2I_PACKET_LOSS"]
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    source_component: str
    active: bool

class CityCommandMetrics(BaseModel):
    city_general_index: float = Field(..., ge=0.0, le=100.0, description="0=Total Gridlock, 100=Optimal Flow")
    hourly_traffic_volume: int
    directional_travel_times_minutes: Dict[str, float]
    intersection_performance_index: float = Field(..., ge=0.0, le=100.0)
    level_of_service: Literal["A", "B", "C", "D", "E", "F"]
    real_time_alerts: List[AnomalyAlert]

# ==========================================
# 8. Full Telemetry Stream Payload (1Hz)
# ==========================================

class TrafficStreamPayload(BaseModel):
    intersection_id: str = "SC-INT-74"
    intersection_name: str = "Oak Street & 5th Avenue"
    timestamp: datetime
    frame_sequence: int
    ml_congestion_prediction: PredictionResponse
    adaptive_signal_control: AdaptiveSignalState
    v2i_hardware_metrics: V2IHardwareMetrics
    intersection_flow: IntersectionFlowMetrics
    simulation_2d_state: Simulation2DState
    iot_sensor_health: IoTSensorHealth
    city_command_metrics: CityCommandMetrics

# ==========================================
# 9. Control & Override Requests
# ==========================================

class SignalOverrideRequest(BaseModel):
    override_mode: Literal["MANUAL", "EMERGENCY", "RESUME_AUTO"]
    forced_phase: Optional[int] = Field(None, ge=1, le=4)
    duration_seconds: Optional[int] = Field(30, ge=5, le=180)
    reason: Optional[str] = "Operator Intervention"

class IncidentInjectionRequest(BaseModel):
    approach: Literal["NORTH", "SOUTH", "EAST", "WEST"]
    incident_type: Literal["STALL", "ACCIDENT", "EMERGENCY_VEHICLE", "WEATHER_STORM", "CLEAR_INCIDENTS"]
    severity: Literal["MINOR", "MODERATE", "SEVERE"] = "MODERATE"
    description: Optional[str] = None

