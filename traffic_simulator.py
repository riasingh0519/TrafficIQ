import time
import math
import random
import uuid
import numpy as np
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, Any

from models import (
    TrafficSensorInput, PredictionResponse,
    V2IHardwareMetrics, PacketTelemetry,
    IntersectionFlowMetrics, ApproachFlow, PhaseOptimizationSavings,
    AdaptiveSignalState, SignalLightState,
    Simulation2DState, SimulatedVehicle,
    IoTSensorHealth, SensorDeviceHealth,
    CityCommandMetrics, AnomalyAlert,
    TrafficStreamPayload
)
from ml_engine import ml_engine

# ==========================================
# Coordinate and Lane Geometry Constants
# ==========================================
# Intersection center is at (0, 0).
# Oak Street runs North-South (Y axis).
# 5th Avenue runs East-West (X axis).
# Stop line is 16.0 meters before intersection center.
STOP_LINE_DIST = 16.0
ROAD_BOUND = 120.0

LANE_CONFIG = {
    # NB travel +y: from y=-120 to +120
    "NB_THROUGH": {"approach": "NORTH", "x": -2.0, "dir": (0, 1), "action": "THROUGH"},
    "NB_LEFT":    {"approach": "NORTH", "x": -5.0, "dir": (0, 1), "action": "LEFT"},
    # SB travel -y: from y=+120 to -120
    "SB_THROUGH": {"approach": "SOUTH", "x": 2.0, "dir": (0, -1), "action": "THROUGH"},
    "SB_LEFT":    {"approach": "SOUTH", "x": 5.0, "dir": (0, -1), "action": "LEFT"},
    # EB travel +x: from x=-120 to +120
    "EB_THROUGH": {"approach": "EAST",  "y": -2.0, "dir": (1, 0), "action": "THROUGH"},
    "EB_LEFT":    {"approach": "EAST",  "y": -5.0, "dir": (1, 0), "action": "LEFT"},
    # WB travel -x: from x=+120 to -120
    "WB_THROUGH": {"approach": "WEST",  "y": 2.0, "dir": (-1, 0), "action": "THROUGH"},
    "WB_LEFT":    {"approach": "WEST",  "y": 5.0, "dir": (-1, 0), "action": "LEFT"},
}

PHASE_NAMES = {
    1: "Phase 1: Oak St (NB/SB) Through & Right",
    2: "Phase 2: Oak St (NB/SB) Protected Left",
    3: "Phase 3: 5th Ave (EB/WB) Through & Right",
    4: "Phase 4: 5th Ave (EB/WB) Protected Left",
}

class TrafficSimulationEngine:
    def __init__(self):
        self.intersection_id = "SC-INT-74"
        self.intersection_name = "Oak Street & 5th Avenue"
        self.frame_sequence = 0
        self.start_time = time.time()
        
        # Adaptive Signal Controller State
        self.cycle_time = 90
        self.current_phase = 1
        self.next_phase = 2
        self.phase_elapsed_seconds = 0
        self.coordination_mode = "ADAPTIVE_DENSITY_WEBSTER"
        self.manual_override_until: Optional[float] = None
        self.emergency_preemption_active: bool = False
        
        # Green Splits (seconds) per phase
        self.yellow_time = 3
        self.all_red_time = 1
        self.green_splits = {
            "phase_1": 28,
            "phase_2": 14,
            "phase_3": 26,
            "phase_4": 14
        }
        
        # Vehicles in simulation
        self.vehicles: Dict[str, Dict[str, Any]] = {}
        self.vehicle_id_counter = 1000
        
        # Cumulative Statistics
        self.total_vehicles_served = 240
        self.cumulative_fuel_saved_liters = 42.5
        self.cumulative_emissions_saved_kg = 98.2
        self.packet_counts = {
            "BSM": 14200,
            "MAP": 1420,
            "SPaT": 14200,
            "SRM_SSM": 320
        }
        
        # Injected conditions
        self.weather_factor = 0.0
        self.active_incident: Optional[Dict[str, Any]] = None
        
        # Cached ML Prediction & SHAP
        self.latest_prediction: Optional[PredictionResponse] = None
        
        # Pre-populate simulation with initial vehicles for smooth start
        self._seed_initial_vehicles()

    def _seed_initial_vehicles(self):
        """Seed a realistic set of initial vehicles approaching the intersection."""
        for lane_id, cfg in LANE_CONFIG.items():
            count = random.randint(2, 4)
            for i in range(count):
                dist = 20.0 + (i * 22.0) + random.uniform(0, 5)
                self._spawn_vehicle(lane_id, initial_dist=dist)

    def _spawn_vehicle(self, lane_id: str, initial_dist: Optional[float] = None) -> Optional[str]:
        cfg = LANE_CONFIG[lane_id]
        dist = initial_dist if initial_dist is not None else random.uniform(95.0, 115.0)
        
        # Check if spawn space is free
        for v in self.vehicles.values():
            if v["lane_id"] == lane_id and abs(v["distance_to_stopline"] - dist) < 14.0:
                return None  # Space occupied
                
        self.vehicle_id_counter += 1
        v_id = f"VEH-{self.vehicle_id_counter}"
        
        v_type = random.choices(
            ["sedan", "suv", "truck", "bus", "ev"],
            weights=[0.55, 0.25, 0.08, 0.04, 0.08]
        )[0]
        
        has_obu = random.random() < 0.82  # 82% OBU penetration
        
        # Coordinate calculation from distance to stop line
        if cfg["approach"] == "NORTH":
            x = cfg["x"]
            y = -(STOP_LINE_DIST + dist)
        elif cfg["approach"] == "SOUTH":
            x = cfg["x"]
            y = STOP_LINE_DIST + dist
        elif cfg["approach"] == "EAST":
            x = -(STOP_LINE_DIST + dist)
            y = cfg["y"]
        else: # WEST
            x = STOP_LINE_DIST + dist
            y = cfg["y"]
            
        color_palette = {
            "sedan": "#3B82F6",
            "suv": "#10B981",
            "truck": "#F59E0B",
            "bus": "#8B5CF6",
            "ev": "#06B6D4"
        }
        
        self.vehicles[v_id] = {
            "vehicle_id": v_id,
            "type": v_type,
            "approach": cfg["approach"],
            "lane_id": lane_id,
            "action": cfg["action"],
            "x": x,
            "y": y,
            "speed_kmh": random.uniform(32.0, 48.0),
            "acceleration": 0.0,
            "distance_to_stopline": dist,
            "has_obu": has_obu,
            "v2i_connected": has_obu,
            "color": color_palette.get(v_type, "#3B82F6"),
            "crossed_stopline": False,
            "turn_progress": 0.0
        }
        return v_id

    # ==========================================
    # Signal State & Phase Evaluation
    # ==========================================
    def get_phase_signal_state(self, phase_id: int) -> str:
        """Determines if the specified phase currently has GREEN, YELLOW, or RED."""
        if self.current_phase != phase_id:
            return "RED"
            
        active_green = self.green_splits.get(f"phase_{phase_id}", 25)
        if self.phase_elapsed_seconds < active_green:
            return "GREEN"
        elif self.phase_elapsed_seconds < (active_green + self.yellow_time):
            return "YELLOW"
        else:
            return "RED"  # All-Red clearance interval

    def get_signal_light_states(self) -> List[SignalLightState]:
        """Calculates 3-color status and time remaining for all intersection approaches."""
        p1_state = self.get_phase_signal_state(1)
        p2_state = self.get_phase_signal_state(2)
        p3_state = self.get_phase_signal_state(3)
        p4_state = self.get_phase_signal_state(4)
        
        active_split = self.green_splits.get(f"phase_{self.current_phase}", 25)
        total_phase_len = active_split + self.yellow_time + self.all_red_time
        remaining = max(0, total_phase_len - self.phase_elapsed_seconds)
        
        signals = [
            SignalLightState(approach="NORTHBOUND", movement="THROUGH_RIGHT", state=p1_state, time_remaining_seconds=remaining if p1_state != "RED" else 0),
            SignalLightState(approach="NORTHBOUND", movement="PROTECTED_LEFT", state=p2_state, time_remaining_seconds=remaining if p2_state != "RED" else 0),
            SignalLightState(approach="SOUTHBOUND", movement="THROUGH_RIGHT", state=p1_state, time_remaining_seconds=remaining if p1_state != "RED" else 0),
            SignalLightState(approach="SOUTHBOUND", movement="PROTECTED_LEFT", state=p2_state, time_remaining_seconds=remaining if p2_state != "RED" else 0),
            SignalLightState(approach="EASTBOUND",  movement="THROUGH_RIGHT", state=p3_state, time_remaining_seconds=remaining if p3_state != "RED" else 0),
            SignalLightState(approach="EASTBOUND",  movement="PROTECTED_LEFT", state=p4_state, time_remaining_seconds=remaining if p4_state != "RED" else 0),
            SignalLightState(approach="WESTBOUND",  movement="THROUGH_RIGHT", state=p3_state, time_remaining_seconds=remaining if p3_state != "RED" else 0),
            SignalLightState(approach="WESTBOUND",  movement="PROTECTED_LEFT", state=p4_state, time_remaining_seconds=remaining if p4_state != "RED" else 0),
        ]
        return signals

    # ==========================================
    # Adaptive Signal Control Optimization
    # ==========================================
    def optimize_signal_timings(self, predicted_congestion: str, queue_lengths: Dict[str, float]):
        """
        Dynamically adjusts cycle_time (60s to 130s), phase sequence,
        and green_split_seconds based on ML prediction and live approach queues.
        """
        if self.emergency_preemption_active:
            self.coordination_mode = "EMERGENCY_PREEMPTION"
            self.cycle_time = 75
            return

        if self.manual_override_until and time.time() < self.manual_override_until:
            self.coordination_mode = "MANUAL_OVERRIDE"
            return
            
        self.coordination_mode = "ADAPTIVE_DENSITY_WEBSTER"
        
        # 1. Base Cycle Time based on ML Congestion Level (bounded 60s to 130s)
        total_queue = sum(queue_lengths.values())
        if predicted_congestion == "FREE":
            base_cycle = 60
        elif predicted_congestion == "LIGHT":
            base_cycle = 75
        elif predicted_congestion == "MODERATE":
            base_cycle = 95
        else: # HEAVY
            base_cycle = 120
            
        # Additional adjustment proportional to queue backlog
        queue_addition = int(min(15, total_queue / 25.0))
        target_cycle = max(60, min(130, base_cycle + queue_addition))
        self.cycle_time = target_cycle
        
        # 2. Phase Demand Weights based on lane queues
        # Phase 1: Oak St Through (NB & SB Through)
        p1_demand = max(5.0, queue_lengths.get("NB_THROUGH", 0) + queue_lengths.get("SB_THROUGH", 0))
        # Phase 2: Oak St Left (NB & SB Left)
        p2_demand = max(3.0, queue_lengths.get("NB_LEFT", 0) + queue_lengths.get("SB_LEFT", 0))
        # Phase 3: 5th Ave Through (EB & WB Through)
        p3_demand = max(5.0, queue_lengths.get("EB_THROUGH", 0) + queue_lengths.get("WB_THROUGH", 0))
        # Phase 4: 5th Ave Left (EB & WB Left)
        p4_demand = max(3.0, queue_lengths.get("EB_LEFT", 0) + queue_lengths.get("WB_LEFT", 0))
        
        total_demand = p1_demand + p2_demand + p3_demand + p4_demand
        
        # Lost time = 4 phases * (yellow(3) + red(1)) = 16s
        effective_green = max(24, self.cycle_time - 16)
        
        # Allocate green splits dynamically
        g1 = max(10, int(round(effective_green * (p1_demand / total_demand))))
        g2 = max(6,  int(round(effective_green * (p2_demand / total_demand))))
        g3 = max(10, int(round(effective_green * (p3_demand / total_demand))))
        g4 = max(6,  int(round(effective_green * (p4_demand / total_demand))))
        
        # Balance residual seconds to the heaviest phase
        sum_green = g1 + g2 + g3 + g4
        diff = effective_green - sum_green
        if diff != 0:
            g1 += diff
            
        self.green_splits = {
            "phase_1": g1,
            "phase_2": g2,
            "phase_3": g3,
            "phase_4": g4
        }

    # ==========================================
    # Simulation Step (1Hz Tick)
    # ==========================================
    def step_simulation(self) -> TrafficStreamPayload:
        self.frame_sequence += 1
        dt = 1.0  # 1 second step
        
        # Advance phase timer
        self.phase_elapsed_seconds += 1
        current_split = self.green_splits.get(f"phase_{self.current_phase}", 25)
        total_phase_duration = current_split + self.yellow_time + self.all_red_time
        
        if self.phase_elapsed_seconds >= total_phase_duration:
            self.phase_elapsed_seconds = 0
            self.current_phase = self.next_phase
            self.next_phase = (self.current_phase % 4) + 1
            
        # Get active signal states
        signal_heads = self.get_signal_light_states()
        
        # 1. Update vehicle physics (IDM & Signal response)
        lane_queues: Dict[str, float] = {k: 0.0 for k in LANE_CONFIG.keys()}
        active_counts: Dict[str, int] = {k: 0 for k in LANE_CONFIG.keys()}
        speeds: List[float] = []
        vehicles_to_remove = []
        
        # Sort vehicles in each lane by distance to stop line ascending
        lane_vehicles: Dict[str, List[Dict[str, Any]]] = {k: [] for k in LANE_CONFIG.keys()}
        for v in self.vehicles.values():
            if not v["crossed_stopline"]:
                lane_vehicles[v["lane_id"]].append(v)
                
        for lane_id, v_list in lane_vehicles.items():
            v_list.sort(key=lambda item: item["distance_to_stopline"])
            
        # Movement & Queue evaluation
        for v_id, v in list(self.vehicles.items()):
            lane_id = v["lane_id"]
            cfg = LANE_CONFIG[lane_id]
            speed_mps = v["speed_kmh"] / 3.6
            
            # Determine movement signal
            if cfg["action"] == "LEFT":
                sig_state = self.get_phase_signal_state(2 if cfg["approach"] in ["NORTH", "SOUTH"] else 4)
            else:
                sig_state = self.get_phase_signal_state(1 if cfg["approach"] in ["NORTH", "SOUTH"] else 3)
                
            dist_to_stop = v["distance_to_stopline"]
            
            # Leading vehicle in the same lane
            lv_list = lane_vehicles[lane_id]
            idx = lv_list.index(v) if v in lv_list else -1
            lead_vehicle = lv_list[idx - 1] if idx > 0 else None
            
            # Target acceleration calculation
            desired_speed_mps = 12.5  # 45 km/h
            target_accel = 1.2  # m/s^2
            
            # Signal stopping logic
            if not v["crossed_stopline"]:
                if dist_to_stop <= 0.5:
                    v["crossed_stopline"] = True
                elif sig_state in ["RED", "YELLOW"] and dist_to_stop < 50.0:
                    # Decelerate smoothly to stop line
                    target_speed_stop = max(0.0, math.sqrt(max(0.0, 2 * 2.0 * dist_to_stop)))
                    desired_speed_mps = min(desired_speed_mps, target_speed_stop)
                    
            # Vehicle following logic
            if lead_vehicle and not v["crossed_stopline"]:
                gap = lead_vehicle["distance_to_stopline"] - dist_to_stop - 6.0  # 6m vehicle length + bumper
                if gap < 25.0:
                    lead_speed_mps = lead_vehicle["speed_kmh"] / 3.6
                    target_speed_lead = max(0.0, lead_speed_mps * 0.95 + max(0.0, gap - 3.0) * 0.4)
                    desired_speed_mps = min(desired_speed_mps, target_speed_lead)
                    
            # Check for simulated incident
            if self.active_incident and self.active_incident["approach"] == cfg["approach"]:
                if dist_to_stop > 15.0 and dist_to_stop < 60.0:
                    desired_speed_mps = min(desired_speed_mps, 2.0)
                    
            # Smooth acceleration / deceleration step
            speed_error = desired_speed_mps - speed_mps
            v["acceleration"] = max(-3.5, min(2.0, speed_error * 0.8))
            speed_mps = max(0.0, speed_mps + v["acceleration"] * dt)
            v["speed_kmh"] = round(speed_mps * 3.6, 1)
            speeds.append(v["speed_kmh"])
            
            # Distance moved
            dist_delta = speed_mps * dt
            
            if not v["crossed_stopline"]:
                v["distance_to_stopline"] -= dist_delta
                # Register queue if vehicle is nearly stopped
                if v["speed_kmh"] < 5.0 and v["distance_to_stopline"] > 0:
                    lane_queues[lane_id] = max(lane_queues[lane_id], v["distance_to_stopline"] + 6.0)
            else:
                # Crossed stopline and driving through intersection
                v["turn_progress"] += dist_delta
                if v["distance_to_stopline"] > -60.0:
                    v["distance_to_stopline"] -= dist_delta
                else:
                    self.total_vehicles_served += 1
                    
            # Update 2D coordinates
            if cfg["approach"] == "NORTH":
                v["y"] += dist_delta
            elif cfg["approach"] == "SOUTH":
                v["y"] -= dist_delta
            elif cfg["approach"] == "EAST":
                v["x"] += dist_delta
            else: # WEST
                v["x"] -= dist_delta
                
            active_counts[lane_id] += 1
            
            # Out of bounds check
            if abs(v["x"]) > ROAD_BOUND or abs(v["y"]) > ROAD_BOUND:
                vehicles_to_remove.append(v_id)
                
        for v_id in vehicles_to_remove:
            self.vehicles.pop(v_id, None)
            
        # 2. Spawning new vehicles according to arrival rate
        spawn_prob = 0.40 if self.active_incident else 0.32
        for lane_id in LANE_CONFIG.keys():
            if random.random() < spawn_prob:
                self._spawn_vehicle(lane_id)
                
        # 3. Compute Aggregate Telemetry for ML Model
        active_veh_count = len(self.vehicles)
        avg_speed = float(np.mean(speeds)) if speeds else 38.0
        max_queue = max(lane_queues.values()) if lane_queues else 12.0
        total_queue_sum = sum(lane_queues.values())
        
        # Approximate flow rate in vehicles/minute
        flow_rate = round(max(5.0, min(65.0, active_veh_count * 1.45)), 1)
        occupancy = round(min(0.98, max(0.04, (active_veh_count / 35.0) * 0.65 + (max_queue / 180.0) * 0.35)), 3)
        
        # Peak hour indicator
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        is_peak = 1 if (current_hour in [7, 8, 9, 16, 17, 18]) else 0
        incident_present = 1 if self.active_incident else 0
        
        sensor_input = TrafficSensorInput(
            vehicle_flow_rate=flow_rate,
            average_speed_kmh=round(avg_speed, 1),
            occupancy_rate=occupancy,
            queue_length_meters=round(max_queue, 1),
            weather_factor=self.weather_factor,
            peak_hour=is_peak,
            incident_flag=incident_present
        )
        
        # 4. ML Model Inference & SHAP Drivers
        ml_prediction = ml_engine.predict(sensor_input)
        self.latest_prediction = ml_prediction
        
        # 5. Adaptive Signal Optimization
        self.optimize_signal_timings(ml_prediction.predicted_congestion_level, lane_queues)
        
        # 6. Build Approach Flow Metrics
        approach_names = {
            "NORTH": ("NORTHBOUND", "Oak Street"),
            "SOUTH": ("SOUTHBOUND", "Oak Street"),
            "EAST":  ("EASTBOUND",  "5th Avenue"),
            "WEST":  ("WESTBOUND",  "5th Avenue")
        }
        approaches_dict: Dict[str, ApproachFlow] = {}
        for app_code, (app_full, st_name) in approach_names.items():
            th_lane = f"{app_code[:2]}_THROUGH" if app_code in ["EAST", "WEST"] else f"{app_code[0]}B_THROUGH"
            lt_lane = f"{app_code[:2]}_LEFT" if app_code in ["EAST", "WEST"] else f"{app_code[0]}B_LEFT"
            
            q_len = max(lane_queues.get(th_lane, 0.0), lane_queues.get(lt_lane, 0.0))
            app_cnt = active_counts.get(th_lane, 0) + active_counts.get(lt_lane, 0)
            
            approaches_dict[app_full] = ApproachFlow(
                approach=app_full,
                street_name=st_name,
                flow_rate_veh_min=round(flow_rate * 0.25 + random.uniform(-1.5, 1.5), 1),
                queue_length_meters=round(q_len, 1),
                avg_speed_kmh=round(max(10.0, avg_speed + random.uniform(-3, 3)), 1),
                occupancy_pct=round(occupancy * 100.0 + random.uniform(-2, 2), 1),
                active_vehicles_count=app_cnt
            )
            
        # Phase Optimization Savings calculation
        # Savings higher during moderate/heavy congestion due to adaptive cycle
        self.cumulative_fuel_saved_liters += round(0.012 * (1.0 + (total_queue_sum / 100.0)), 4)
        self.cumulative_emissions_saved_kg += round(0.028 * (1.0 + (total_queue_sum / 100.0)), 4)
        
        savings = PhaseOptimizationSavings(
            delay_saved_seconds_per_cycle=round(max(4.2, 5.0 + (self.cycle_time - 60) * 0.18), 1),
            emissions_reduction_kg=round(self.cumulative_emissions_saved_kg, 2),
            baseline_vs_adaptive_gain_pct=round(18.5 + (5.0 if ml_prediction.predicted_congestion_level in ["MODERATE", "HEAVY"] else 0.0), 1),
            cumulative_fuel_saved_liters=round(self.cumulative_fuel_saved_liters, 2)
        )
        
        intersection_flow = IntersectionFlowMetrics(
            total_flow_rate_veh_min=flow_rate,
            projected_hourly_volume=int(flow_rate * 60),
            congestion_metric_distance_meters=round(max_queue * 1.35, 1),
            approaches=approaches_dict,
            phase_optimization_savings=savings
        )
        
        # 7. V2I Hardware & Packet Telemetry
        obus_in_range = sum(1 for v in self.vehicles.values() if v["has_obu"])
        self.packet_counts["BSM"] += obus_in_range
        self.packet_counts["SPaT"] += 1
        self.packet_counts["MAP"] += 1
        
        v2i_metrics = V2IHardwareMetrics(
            rsu_id="RSU-SC74-01",
            rsu_status="ONLINE",
            rsu_temp_celsius=round(41.5 + random.uniform(-0.5, 0.8), 1),
            tx_power_dbm=23.0,
            active_obus_in_range=obus_in_range,
            v2i_latency_ms=round(11.4 + random.uniform(-1.8, 2.2), 1),
            channel_occupancy_pct=round(21.5 + (obus_in_range * 0.65), 1),
            dsrc_standard="IEEE 802.11p / C-V2X Rel-16",
            packets={
                "BSM": PacketTelemetry(
                    type="BSM",
                    broadcast_status="ACTIVE",
                    frequency_hz=10.0,
                    packets_transmitted=self.packet_counts["BSM"],
                    packet_loss_rate_pct=round(0.04 + random.uniform(-0.01, 0.02), 3),
                    last_payload_summary=f"{obus_in_range} OBUs broadcasting pos/speed/heading"
                ),
                "MAP": PacketTelemetry(
                    type="MAP",
                    broadcast_status="ACTIVE",
                    frequency_hz=1.0,
                    packets_transmitted=self.packet_counts["MAP"],
                    packet_loss_rate_pct=0.01,
                    last_payload_summary="Geometry Rev 4.2: 4 approaches, 8 lanes mapped"
                ),
                "SPaT": PacketTelemetry(
                    type="SPaT",
                    broadcast_status="ACTIVE",
                    frequency_hz=10.0,
                    packets_transmitted=self.packet_counts["SPaT"],
                    packet_loss_rate_pct=0.02,
                    last_payload_summary=f"Active Phase {self.current_phase} remaining: {signal_heads[0].time_remaining_seconds}s"
                ),
                "SRM_SSM": PacketTelemetry(
                    type="SRM_SSM",
                    broadcast_status="ACTIVE",
                    frequency_hz=2.0,
                    packets_transmitted=self.packet_counts["SRM_SSM"],
                    packet_loss_rate_pct=0.00,
                    last_payload_summary="Emergency/Transit preemption listening"
                )
            }
        )
        
        # 8. 2D Simulation State for clients
        sim_vehicles = [
            SimulatedVehicle(
                vehicle_id=v["vehicle_id"],
                type=v["type"],
                approach=v["approach"],
                lane_id=v["lane_id"],
                x=round(v["x"], 2),
                y=round(v["y"], 2),
                speed_kmh=v["speed_kmh"],
                acceleration_mps2=round(v["acceleration"], 2),
                distance_to_stopline_m=round(max(0.0, v["distance_to_stopline"]), 1),
                target_action=v["action"],
                has_obu=v["has_obu"],
                v2i_connected=v["v2i_connected"],
                color=v["color"]
            )
            for v in self.vehicles.values()
        ]
        
        sim_state = Simulation2DState(
            intersection_center={"x": 0.0, "y": 0.0},
            road_boundaries={"x_min": -ROAD_BOUND, "x_max": ROAD_BOUND, "y_min": -ROAD_BOUND, "y_max": ROAD_BOUND},
            active_vehicles_count=len(sim_vehicles),
            vehicles=sim_vehicles,
            signal_heads=signal_heads
        )
        
        # 9. IoT Sensor Health
        sensor_devices = [
            SensorDeviceHealth(
                device_id="CAM-NB-4K", sensor_type="TRAFFIC_CAMERA",
                status="HEALTHY", coverage_pct=99.4, sampling_rate_hz=30.0,
                last_heartbeat_ms_ago=32, operational_notes="Optical detection clear, no lens occlusion"
            ),
            SensorDeviceHealth(
                device_id="CAM-SB-4K", sensor_type="TRAFFIC_CAMERA",
                status="HEALTHY", coverage_pct=99.1, sampling_rate_hz=30.0,
                last_heartbeat_ms_ago=45, operational_notes="Optical detection clear"
            ),
            SensorDeviceHealth(
                device_id="LIDAR-CORE-01", sensor_type="3D_LIDAR",
                status="HEALTHY", coverage_pct=98.7, sampling_rate_hz=20.0,
                last_heartbeat_ms_ago=18, operational_notes="Point-cloud spatial density: 240k pts/sec"
            ),
            SensorDeviceHealth(
                device_id="LOOP-ARRAY-08", sensor_type="LOOP_DETECTOR",
                status="HEALTHY", coverage_pct=100.0, sampling_rate_hz=100.0,
                last_heartbeat_ms_ago=10, operational_notes="8/8 dual-frequency loops resonant"
            ),
            SensorDeviceHealth(
                device_id="RSU-SC74-01", sensor_type="RSU_GATEWAY",
                status="HEALTHY", coverage_pct=99.8, sampling_rate_hz=10.0,
                last_heartbeat_ms_ago=12, operational_notes="C-V2X / DSRC radio synchronized to UTC GPS"
            )
        ]
        iot_health = IoTSensorHealth(
            overall_health_score=99.2,
            devices=sensor_devices
        )
        
        # 10. City Command Metrics & Real-Time Anomaly Alerts
        # General Index: 100 is pristine free-flow, down to 20 for severe gridlock
        city_idx = round(max(15.0, 100.0 - (occupancy * 55.0) - (max_queue * 0.18)), 1)
        ipi_score = round(max(20.0, 96.0 - (occupancy * 42.0)), 1)
        
        # LOS: A to F
        if ipi_score >= 88: los = "A"
        elif ipi_score >= 76: los = "B"
        elif ipi_score >= 64: los = "C"
        elif ipi_score >= 52: los = "D"
        elif ipi_score >= 40: los = "E"
        else: los = "F"
        
        alerts: List[AnomalyAlert] = []
        if ml_prediction.predicted_congestion_level == "HEAVY":
            alerts.append(AnomalyAlert(
                alert_id=f"ALT-{self.frame_sequence}-01",
                timestamp=now_utc,
                type="HEAVY_CONGESTION",
                severity="CRITICAL",
                message=f"Heavy corridor congestion detected. Maximum queue reached {round(max_queue, 1)}m.",
                source_component="MLEngine/CongestionDetector",
                active=True
            ))
            
        if self.active_incident:
            alerts.append(AnomalyAlert(
                alert_id=f"ALT-{self.frame_sequence}-02",
                timestamp=now_utc,
                type="SHOCKWAVE_DETECTED",
                severity="WARNING",
                message=f"Incident '{self.active_incident['type']}' active on {self.active_incident['approach']} approach.",
                source_component="VisionTracker",
                active=True
            ))
            
        if self.emergency_preemption_active:
            alerts.append(AnomalyAlert(
                alert_id=f"ALT-{self.frame_sequence}-03",
                timestamp=now_utc,
                type="EMERGENCY_PREEMPTION",
                severity="CRITICAL",
                message="Emergency vehicle preemption active. Corridors cleared for priority transit.",
                source_component="V2I_RSU_Receiver",
                active=True
            ))
            
        city_command = CityCommandMetrics(
            city_general_index=city_idx,
            hourly_traffic_volume=int(flow_rate * 60),
            directional_travel_times_minutes={
                "Oak_Street_NB_to_SB": round(2.8 + (max_queue / 50.0), 2),
                "Oak_Street_SB_to_NB": round(2.7 + (max_queue / 55.0), 2),
                "5th_Avenue_EB_to_WB": round(2.4 + (max_queue / 60.0), 2),
                "5th_Avenue_WB_to_EB": round(2.5 + (max_queue / 58.0), 2)
            },
            intersection_performance_index=ipi_score,
            level_of_service=los,
            real_time_alerts=alerts
        )
        
        # 11. Compile Signal State Model
        signal_state = AdaptiveSignalState(
            cycle_time=self.cycle_time,
            current_phase=self.current_phase,
            current_phase_name=PHASE_NAMES[self.current_phase],
            next_phase=self.next_phase,
            next_phase_name=PHASE_NAMES[self.next_phase],
            phase_elapsed_seconds=self.phase_elapsed_seconds,
            green_split_seconds=self.green_splits,
            coordination_mode=self.coordination_mode,
            signals=signal_heads
        )
        
        # 12. Full Telemetry Payload
        return TrafficStreamPayload(
            intersection_id=self.intersection_id,
            intersection_name=self.intersection_name,
            timestamp=now_utc,
            frame_sequence=self.frame_sequence,
            ml_congestion_prediction=ml_prediction,
            adaptive_signal_control=signal_state,
            v2i_hardware_metrics=v2i_metrics,
            intersection_flow=intersection_flow,
            simulation_2d_state=sim_state,
            iot_sensor_health=iot_health,
            city_command_metrics=city_command
        )

# Global simulation singleton
sim_engine = TrafficSimulationEngine()
