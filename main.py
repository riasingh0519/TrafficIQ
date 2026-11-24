import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Set, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    TrafficSensorInput, PredictionResponse,
    TrafficStreamPayload, SignalOverrideRequest, IncidentInjectionRequest,
    AdaptiveSignalState, V2IHardwareMetrics, IntersectionFlowMetrics
)
from ml_engine import ml_engine
from traffic_simulator import sim_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TrafficControlServer")

# ==========================================
# WebSocket Connection Manager
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total active clients: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active clients: {len(self.active_connections)}")

    async def broadcast_json(self, data: dict):
        if not self.active_connections:
            return

        message_text = json.dumps(data, default=str)
        dead_connections = []
        
        async with self._lock:
            connections = list(self.active_connections)
            
        for connection in connections:
            try:
                await connection.send_text(message_text)
            except Exception as e:
                logger.warning(f"Error broadcasting to client: {e}")
                dead_connections.append(connection)

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    self.active_connections.discard(dead)

manager = ConnectionManager()

# ==========================================
# Background 1Hz Simulation Loop
# ==========================================
simulation_task: Optional[asyncio.Task] = None
latest_telemetry_payload: Optional[TrafficStreamPayload] = None

async def traffic_simulation_worker():
    """
    Simulates intersection dynamics and broadcasts telemetry at 1Hz (every 1.0 second).
    """
    global latest_telemetry_payload
    logger.info("Traffic simulation background worker started at 1Hz.")
    
    try:
        while True:
            loop_start = time.perf_counter()
            
            # Step the simulation forward by 1 second
            payload: TrafficStreamPayload = sim_engine.step_simulation()
            latest_telemetry_payload = payload
            
            # Broadcast structured JSON to all connected WebSocket clients
            payload_dict = payload.model_dump(mode="json")
            await manager.broadcast_json(payload_dict)
            
            # Compute remaining time to maintain precise 1Hz cadence
            elapsed = time.perf_counter() - loop_start
            sleep_duration = max(0.05, 1.0 - elapsed)
            await asyncio.sleep(sleep_duration)
            
    except asyncio.CancelledError:
        logger.info("Traffic simulation worker cancelled gracefully.")
    except Exception as e:
        logger.error(f"Unexpected error in simulation loop: {e}", exc_info=True)

# ==========================================
# Lifespan Management
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global simulation_task
    logger.info("Initializing Smart Intersection Backend (SC-INT-74)...")
    _ = ml_engine.model  # Verify model is ready
    simulation_task = asyncio.create_task(traffic_simulation_worker())
    yield
    logger.info("Shutting down Smart Intersection Backend...")
    if simulation_task and not simulation_task.done():
        simulation_task.cancel()
        try:
            await simulation_task
        except asyncio.CancelledError:
            pass

# ==========================================
# FastAPI Application Declaration
# ==========================================
app = FastAPI(
    title="Smart City Adaptive Traffic Control & V2I Telemetry Server",
    description="Adaptive Traffic Signal Control & V2I Telemetry for Intersection SC-INT-74 (Oak St & 5th Ave)",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. ML Inference Endpoint (POST /api/predict)
# ==========================================
@app.post(
    "/api/predict",
    response_model=PredictionResponse,
    summary="Predict Congestion Level with SHAP Feature Drivers",
    description="Accepts live road sensor metrics, runs congestion_model.joblib, and computes confidence scores along with SHAP feature attributions."
)
async def predict_congestion(sensor_input: TrafficSensorInput):
    try:
        prediction = ml_engine.predict(sensor_input)
        return prediction
    except Exception as e:
        logger.error(f"Inference error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference execution failed: {str(e)}"
        )

@app.get(
    "/api/model/metrics",
    summary="Model Accuracy & Performance Metrics",
    description="Returns trained model evaluation report, test accuracy, precision/recall, and feature importances."
)
async def get_model_metrics():
    """Returns the trained model accuracy metrics and feature importances."""
    feature_importances = {}
    if hasattr(ml_engine.model, "feature_importances_"):
        for f, imp in zip(ml_engine.features, ml_engine.model.feature_importances_):
            feature_importances[f] = round(float(imp), 4)
            
    return {
        "model_file": "congestion_model.joblib",
        "model_type": type(ml_engine.model).__name__,
        "overall_accuracy_pct": 90.20,
        "classes": ml_engine.classes,
        "features": ml_engine.features,
        "class_metrics": {
            "FREE": {"precision": 0.9387, "recall": 0.9359, "f1_score": 0.9373},
            "LIGHT": {"precision": 0.8638, "recall": 0.8852, "f1_score": 0.8743},
            "MODERATE": {"precision": 0.9005, "recall": 0.8973, "f1_score": 0.8989},
            "HEAVY": {"precision": 0.8939, "recall": 0.8510, "f1_score": 0.8719}
        },
        "feature_importances": feature_importances,
        "evaluation_sample_size": 2000
    }

# ==========================================
# 2. WebSocket Telemetry Stream (/ws/traffic-stream)
# ==========================================
@app.websocket("/ws/traffic-stream")
async def websocket_traffic_stream(websocket: WebSocket):
    """
    Real-time 1Hz WebSocket telemetry stream.
    Broadcasts V2I hardware metrics, adaptive signal states, 2D simulation coordinates,
    IoT sensor health, and city command metrics.
    Also accepts bidirectional commands from clients (overrides, scenario injection).
    """
    await manager.connect(websocket)
    global latest_telemetry_payload
    try:
        # Immediately send current state so client does not wait
        if latest_telemetry_payload is None:
            latest_telemetry_payload = sim_engine.step_simulation()
        await websocket.send_text(json.dumps(latest_telemetry_payload.model_dump(mode="json"), default=str))

        while True:
            data_text = await websocket.receive_text()
            try:
                command = json.loads(data_text)
                action = command.get("action")
                
                if action == "signal_override":
                    phase = command.get("phase")
                    mode = command.get("mode", "MANUAL")
                    if mode == "EMERGENCY":
                        sim_engine.emergency_preemption_active = True
                        sim_engine.current_phase = phase or 1
                        sim_engine.phase_elapsed_seconds = 0
                    elif mode == "RESUME_AUTO":
                        sim_engine.emergency_preemption_active = False
                        sim_engine.manual_override_until = None
                    elif phase in [1, 2, 3, 4]:
                        sim_engine.current_phase = phase
                        sim_engine.phase_elapsed_seconds = 0
                        sim_engine.manual_override_until = time.time() + command.get("duration", 30)
                    await websocket.send_text(json.dumps({"status": "OK", "action": action, "active_phase": sim_engine.current_phase}))

                elif action == "inject_incident":
                    appr = command.get("approach", "NORTH")
                    inc_type = command.get("type", "STALL")
                    if inc_type == "CLEAR_INCIDENTS":
                        sim_engine.active_incident = None
                        sim_engine.weather_factor = 0.0
                    elif inc_type == "WEATHER_STORM":
                        sim_engine.weather_factor = 0.7
                    else:
                        sim_engine.active_incident = {"approach": appr, "type": inc_type}
                    await websocket.send_text(json.dumps({"status": "OK", "action": action, "incident": sim_engine.active_incident}))
                    
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
                    
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client error: {e}")
        await manager.disconnect(websocket)

# ==========================================
# 3. REST API Endpoints
# ==========================================
@app.get("/api/status", summary="Get Intersection SC-INT-74 Snapshot")
async def get_intersection_status():
    """Returns the latest telemetry, controller state, and hardware health."""
    if not latest_telemetry_payload:
        payload = sim_engine.step_simulation()
        return payload
    return latest_telemetry_payload

@app.get("/api/simulation/state", summary="Get 2D Simulation Snapshot")
async def get_simulation_state():
    """Returns the active vehicle coordinates, lane IDs, and signal states."""
    if latest_telemetry_payload:
        return latest_telemetry_payload.simulation_2d_state
    payload = sim_engine.step_simulation()
    return payload.simulation_2d_state

@app.post("/api/signal/override", summary="Manual or Emergency Signal Override")
async def override_signal(req: SignalOverrideRequest):
    """Overrides active signal phase or triggers emergency vehicle preemption."""
    if req.override_mode == "EMERGENCY":
        sim_engine.emergency_preemption_active = True
        sim_engine.coordination_mode = "EMERGENCY_PREEMPTION"
        if req.forced_phase:
            sim_engine.current_phase = req.forced_phase
            sim_engine.phase_elapsed_seconds = 0
        return {"status": "SUCCESS", "mode": "EMERGENCY_PREEMPTION", "phase": sim_engine.current_phase}
        
    elif req.override_mode == "RESUME_AUTO":
        sim_engine.emergency_preemption_active = False
        sim_engine.manual_override_until = None
        sim_engine.coordination_mode = "ADAPTIVE_DENSITY_WEBSTER"
        return {"status": "SUCCESS", "mode": "ADAPTIVE_DENSITY_WEBSTER"}
        
    elif req.override_mode == "MANUAL":
        if not req.forced_phase or req.forced_phase not in [1, 2, 3, 4]:
            raise HTTPException(status_code=400, detail="forced_phase must be an integer between 1 and 4")
        sim_engine.emergency_preemption_active = False
        sim_engine.current_phase = req.forced_phase
        sim_engine.phase_elapsed_seconds = 0
        sim_engine.manual_override_until = time.time() + (req.duration_seconds or 30)
        sim_engine.coordination_mode = "MANUAL_OVERRIDE"
        return {
            "status": "SUCCESS",
            "mode": "MANUAL_OVERRIDE",
            "forced_phase": req.forced_phase,
            "duration_seconds": req.duration_seconds
        }

@app.post("/api/simulate/inject-event", summary="Inject Incident or Weather Condition")
async def inject_event(req: IncidentInjectionRequest):
    """Simulates stalls, accidents, weather variations, or emergency preemption."""
    if req.incident_type == "CLEAR_INCIDENTS":
        sim_engine.active_incident = None
        sim_engine.weather_factor = 0.0
        return {"status": "CLEARED", "message": "All simulated incidents and weather cleared"}
    elif req.incident_type == "WEATHER_STORM":
        sim_engine.weather_factor = 0.7
        return {"status": "INJECTED", "type": "WEATHER_STORM", "weather_factor": 0.7}
    else:
        sim_engine.active_incident = {
            "approach": req.approach,
            "type": req.incident_type,
            "severity": req.severity
        }
        return {"status": "INJECTED", "incident": sim_engine.active_incident}

# ==========================================
# 4. Interactive Live 4-Quadrant Dashboard UI
# ==========================================
@app.get("/", response_class=HTMLResponse, summary="Live Intersection Operations Dashboard")
@app.get("/dashboard", response_class=HTMLResponse, summary="Live Intersection Operations Dashboard")
async def get_dashboard():
    """Serves the complete 4-Quadrant Smart City Traffic Operations Center dashboard."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Smart City Traffic Digital Twin & Command Center | SC-INT-74</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; background-color: #030712; color: #f3f4f6; overflow-x: hidden; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .card-panel { background: rgba(15, 23, 42, 0.88); backdrop-filter: blur(12px); border: 1px solid rgba(51, 65, 85, 0.7); }
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: #030712; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 2px; }
  </style>
</head>
<body class="min-h-screen flex flex-col p-2.5 space-y-2.5 selection:bg-cyan-500 selection:text-black">

  <!-- TOP COMMAND BAR: METROPOLIS ITS & SCENARIO SIMULATOR -->
  <header class="card-panel rounded-xl px-5 py-2.5 flex flex-wrap items-center justify-between gap-3 shadow-xl">
    <div class="flex items-center space-x-3.5">
      <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
        <span class="font-black text-white text-sm">DT</span>
      </div>
      <div>
        <div class="flex items-center space-x-2.5">
          <h1 class="text-sm font-extrabold tracking-wide text-white uppercase">
            METROPOLIS ITS DIGITAL TWIN &bull; DUAL-SCREEN COMMAND CENTER
          </h1>
          <span id="ws-badge" class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase bg-yellow-500/20 text-yellow-400 border border-yellow-500/40">
            CONNECTING...
          </span>
        </div>
        <p class="text-[10px] text-slate-400">
          Intersection SC-INT-74 ("Oak Street &amp; 5th Avenue") &bull; C-V2X Rel-16 &bull; Webster Dynamic Adaptive Optimization
        </p>
      </div>
    </div>

    <!-- SCENARIO SIMULATOR DROPDOWN -->
    <div class="flex items-center space-x-3">
      <div class="flex items-center space-x-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
        <label for="scenario-select" class="text-[11px] font-mono font-bold text-slate-400 uppercase">
          Scenario Simulator:
        </label>
        <select
          id="scenario-select"
          onchange="handleScenarioChange(this.value)"
          class="bg-slate-900 text-cyan-300 font-mono text-xs font-bold rounded px-2 py-1 border border-slate-700 focus:outline-none focus:border-cyan-400 cursor-pointer"
        >
          <option value="auto">Auto ML Live (Autonomous)</option>
          <option value="heavy">Simulate Rush Hour Heavy</option>
          <option value="free">Simulate Free Flow (Midnight)</option>
          <option value="incident">Simulate Incident Anomaly (Stall)</option>
        </select>
      </div>

      <button
        onclick="resetToAuto()"
        class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-mono font-semibold text-slate-300 border border-slate-700 transition"
      >
        Reset
      </button>
    </div>
  </header>

  <!-- DUAL-SCREEN 4-QUADRANT LAYOUT -->
  <main class="grid grid-cols-1 xl:grid-cols-2 gap-2.5 flex-1">
    
    <!-- LEFT SCREEN: QUADRANT 1 (TOP) & QUADRANT 2 (BOTTOM) -->
    <div class="flex flex-col space-y-2.5">
      
      <!-- ========================================== -->
      <!-- QUADRANT 1: 3D ISOMETRIC INTERSECTION DIGITAL TWIN -->
      <!-- ========================================== -->
      <section class="card-panel rounded-xl flex-1 flex flex-col relative overflow-hidden min-h-[460px] shadow-2xl">
        {/* Top Header Bar */}
        <div class="absolute top-0 left-0 right-0 z-20 px-4 py-2.5 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 flex items-center justify-between">
          <div class="flex items-center space-x-2.5">
            <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
            <h2 class="text-xs font-bold uppercase tracking-wider text-white">
              Quadrant 1: 3D Isometric Intersection Digital Twin &bull; Oak Street &amp; 5th Avenue
            </h2>
          </div>
          <div class="flex items-center space-x-2.5 text-xs">
            <div id="q1-phase-pill" class="flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-[11px]">
              <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
              <span class="font-semibold text-slate-200">Phase 1 Active</span>
            </div>
            <div id="q1-ml-badge" class="px-2.5 py-0.5 rounded-full border text-[11px] font-mono font-bold bg-blue-500/20 text-blue-400 border-blue-500/40">
              ML: LIGHT (85%)
            </div>
          </div>
        </div>

        {/* 3D Isometric Canvas Mount */}
        <div id="three-container" class="w-full flex-1 relative bg-slate-950 overflow-hidden"></div>

        {/* Overlay Card A: V2I Communication Module Hardware (Top-Left) */}
        <div class="absolute top-14 left-3 z-20 w-64 p-3 rounded-lg bg-slate-900/90 backdrop-blur-md border border-slate-700 shadow-xl space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-bold uppercase tracking-wider text-cyan-400 flex items-center space-x-1">
              <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
              <span>V2I Hardware Module</span>
            </span>
            <span class="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 px-1 py-0.2 rounded border border-emerald-500/20">
              ACTIVE
            </span>
          </div>
          <div class="py-1 px-1 bg-slate-950 rounded border border-slate-800 text-[9px] font-mono text-slate-300 flex justify-between items-center text-center">
            <span class="px-1 py-0.5 rounded bg-blue-500/20 text-blue-300" id="card-obu-cnt">OBU (24)</span>
            <span class="text-cyan-400 font-bold">&larr;BSM/MAP&rarr;</span>
            <span class="px-1 py-0.5 rounded bg-emerald-500/20 text-emerald-300">RSU-SC74</span>
            <span class="text-cyan-400 font-bold">&larr;SPaT&rarr;</span>
            <span class="px-1 py-0.5 rounded bg-purple-500/20 text-purple-300">Controller</span>
          </div>
          <div class="grid grid-cols-2 gap-1 text-[9px] font-mono text-slate-400">
            <div>Latency: <span id="card-v2i-lat" class="text-cyan-300 font-bold">11.4 ms</span></div>
            <div>Channel: <span id="card-v2i-occ" class="text-yellow-300 font-bold">24.5%</span></div>
          </div>
        </div>

        {/* Overlay Card B: Adaptive Traffic Signal Control Dashboard (Top-Right) */}
        <div class="absolute top-14 right-3 z-20 w-72 p-3 rounded-lg bg-slate-900/90 backdrop-blur-md border border-slate-700 shadow-xl space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-1">
              <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
              <span>Adaptive Signal Control</span>
            </span>
            <span class="text-[10px] font-mono text-cyan-300">
              Cycle: <strong id="card-cycle-txt" class="text-white">95s</strong> (60-130s)
            </span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-[10px]">
            <div class="p-1.5 rounded bg-slate-950/80 border border-slate-800">
              <div class="text-slate-400 text-[9px]">Current Phase</div>
              <div id="card-curr-phase" class="font-bold text-emerald-400 text-xs">Phase 1</div>
            </div>
            <div class="p-1.5 rounded bg-slate-950/80 border border-slate-800">
              <div class="text-slate-400 text-[9px]">Next Phase</div>
              <div id="card-next-phase" class="font-bold text-cyan-400 text-xs">Phase 2</div>
            </div>
          </div>
          {/* Multi-Line Queue Lengths Sparkline */}
          <div class="space-y-1">
            <div class="flex justify-between text-[9px] font-mono text-slate-400">
              <span>Queue Lengths History (m)</span>
              <span id="card-opt-savings" class="text-emerald-400 font-bold">Savings: 7.2s/cyc</span>
            </div>
            <div class="h-10 w-full bg-slate-950 rounded border border-slate-800 p-0.5">
              <svg id="queue-sparkline-svg" class="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
                <polyline id="poly-nb" fill="none" stroke="#38bdf8" stroke-width="1.8" points="0,25 100,25" />
                <polyline id="poly-eb" fill="none" stroke="#f59e0b" stroke-width="1.8" points="0,27 100,27" />
              </svg>
            </div>
          </div>
        </div>

        {/* Bottom Floating Status Bar */}
        <div class="absolute bottom-2.5 left-3 right-3 z-20 px-3.5 py-1.5 bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-lg flex items-center justify-between text-[11px] font-mono text-slate-300">
          <div class="flex items-center space-x-4">
            <div>Digital Twin ID: <span class="text-cyan-400 font-bold">SC-INT-74</span></div>
            <div>V2I Latency: <span id="bar-v2i-lat" class="text-emerald-400 font-bold">11.4 ms</span></div>
            <div>Occupancy: <span id="bar-occ" class="text-yellow-400 font-bold">32.4%</span></div>
          </div>
          <div>Active Vehicles: <strong id="bar-veh-cnt" class="text-white">28</strong> &bull; Throughput Gain: <span id="bar-gain" class="text-emerald-400 font-bold">+18.5%</span></div>
        </div>
      </section>

      <!-- ========================================== -->
      <!-- QUADRANT 2: IOT SENSOR NETWORK & TRAFFIC ANALYTICS -->
      <!-- ========================================== -->
      <section class="card-panel rounded-xl flex-1 flex flex-col p-3.5 space-y-3 min-h-[380px] shadow-2xl">
        <div class="flex items-center justify-between border-b border-slate-800 pb-2">
          <div class="flex items-center space-x-2">
            <span class="w-2 h-2 rounded-full bg-blue-500"></span>
            <h2 class="text-xs font-bold uppercase tracking-wider text-slate-200">
              Quadrant 2: IoT Sensor Network &amp; Traffic Data Analytics
            </h2>
          </div>
          <span class="text-[10px] font-mono text-emerald-400">
            Array Health: <strong id="q2-array-health">99.2%</strong>
          </span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 flex-1">
          {/* IoT Sensor Radar View */}
          <div class="p-3 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-2">
            <div class="flex justify-between items-center text-xs">
              <span class="font-bold text-slate-300 uppercase text-[10px]">Sensor Network Map Overlay</span>
              <span class="text-[9px] font-mono text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/20">RADAR ACTIVE</span>
            </div>
            <div class="relative flex-1 min-h-[140px] bg-slate-950 rounded border border-slate-800 flex items-center justify-center overflow-hidden">
              <div class="absolute w-32 h-32 rounded-full border border-slate-800"></div>
              <div class="absolute w-20 h-20 rounded-full border border-slate-800/80"></div>
              <div class="absolute w-10 h-10 rounded-full border border-slate-800/60"></div>
              <div class="absolute w-full h-[1px] bg-slate-800/60"></div>
              <div class="absolute h-full w-[1px] bg-slate-800/60"></div>
              <div class="absolute w-20 h-20 rounded-full border-r border-t border-cyan-500/40 animate-spin"></div>

              {/* Sensor Cones */}
              <div class="absolute top-2 left-1/2 -translate-x-1/2 text-[8px] font-mono text-rose-400">
                <span class="w-2 h-2 rounded-full bg-rose-500 inline-block shadow shadow-rose-500"></span> CAM-NB
              </div>
              <div class="absolute bottom-2 left-1/2 -translate-x-1/2 text-[8px] font-mono text-rose-400">
                <span class="w-2 h-2 rounded-full bg-rose-500 inline-block shadow shadow-rose-500"></span> CAM-SB
              </div>
              <div class="absolute left-3 top-1/2 -translate-y-1/2 text-[8px] font-mono text-blue-400">
                <span class="w-2 h-2 rounded-full bg-blue-500 inline-block shadow shadow-blue-500"></span> LiDAR-EB
              </div>
              <div class="absolute right-3 top-1/2 -translate-y-1/2 text-[8px] font-mono text-blue-400">
                <span class="w-2 h-2 rounded-full bg-blue-500 inline-block shadow shadow-blue-500"></span> LiDAR-WB
              </div>
              <div class="absolute text-[8px] font-mono text-amber-300 font-bold text-center">
                <span class="w-3 h-3 rounded-full bg-amber-400 inline-block shadow shadow-amber-400 animate-pulse"></span><br/>RSU
              </div>
            </div>
            {/* Badges */}
            <div class="grid grid-cols-4 gap-1 text-center text-[9px] font-mono">
              <div class="p-1 rounded bg-slate-950 border border-slate-800 text-rose-400">CAM: 30 FPS</div>
              <div class="p-1 rounded bg-slate-950 border border-slate-800 text-blue-400">LiDAR: 20 Hz</div>
              <div class="p-1 rounded bg-slate-950 border border-slate-800 text-emerald-400">Loops: 100 Hz</div>
              <div class="p-1 rounded bg-slate-950 border border-slate-800 text-amber-400">RSU: Active</div>
            </div>
          </div>

          {/* Traffic Data Analytics Panel */}
          <div class="p-3 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-2.5">
            <div class="flex justify-between items-center text-xs">
              <span class="font-bold text-slate-300 uppercase text-[10px]">Approach Volume &amp; Travel Times</span>
              <span id="q2-hourly-vol" class="text-[9px] font-mono text-cyan-300">2,400 veh/hr</span>
            </div>

            {/* Vertical Bar Chart: Traffic Volume by Approach */}
            <div class="space-y-1">
              <div class="text-[9px] uppercase font-mono text-slate-400 flex justify-between">
                <span>Approach Flow (Veh/min)</span>
                <span class="text-cyan-400">Rate</span>
              </div>
              <div class="grid grid-cols-4 gap-2 h-16 items-end bg-slate-950 p-2 rounded border border-slate-800">
                <div class="flex flex-col items-center h-full justify-end">
                  <span id="bar-val-nb" class="text-[8px] font-mono text-slate-300">12</span>
                  <div id="bar-nb" class="w-full bg-blue-500 rounded-t h-1/2 transition-all duration-300"></div>
                  <span class="text-[8px] font-mono text-slate-400">NB</span>
                </div>
                <div class="flex flex-col items-center h-full justify-end">
                  <span id="bar-val-sb" class="text-[8px] font-mono text-slate-300">11</span>
                  <div id="bar-sb" class="w-full bg-cyan-500 rounded-t h-1/2 transition-all duration-300"></div>
                  <span class="text-[8px] font-mono text-slate-400">SB</span>
                </div>
                <div class="flex flex-col items-center h-full justify-end">
                  <span id="bar-val-eb" class="text-[8px] font-mono text-slate-300">14</span>
                  <div id="bar-eb" class="w-full bg-amber-500 rounded-t h-3/5 transition-all duration-300"></div>
                  <span class="text-[8px] font-mono text-slate-400">EB</span>
                </div>
                <div class="flex flex-col items-center h-full justify-end">
                  <span id="bar-val-wb" class="text-[8px] font-mono text-slate-300">10</span>
                  <div id="bar-wb" class="w-full bg-purple-500 rounded-t h-2/5 transition-all duration-300"></div>
                  <span class="text-[8px] font-mono text-slate-400">WB</span>
                </div>
              </div>
            </div>

            {/* Avg Travel Times Horizontal Bar */}
            <div class="space-y-1 text-[9px] font-mono">
              <div class="flex justify-between text-slate-400">
                <span>Avg Travel Time</span>
                <span id="q2-avg-tt" class="text-cyan-300 font-bold">2.4 min avg</span>
              </div>
              <div class="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                <div id="tt-progress" class="bg-gradient-to-r from-blue-400 to-amber-400 h-full rounded-full w-1/2"></div>
              </div>
            </div>

            {/* Performance Index & Anomaly Banner */}
            <div class="flex items-center justify-between p-1.5 rounded bg-slate-950 border border-slate-800 text-[10px] font-mono">
              <span>Performance Index: <strong id="q2-ipi-val" class="text-white">88.5</strong></span>
              <span id="q2-los-badge" class="px-2 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">LOS: A</span>
            </div>
            <div id="q2-anomaly-banner" class="p-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-[9px] font-mono">
              Anomaly Detection: Nominal flow. Zero corridor shockwaves.
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- RIGHT SCREEN: QUADRANT 3 (TOP) & QUADRANT 4 (BOTTOM) -->
    <div class="flex flex-col space-y-2.5">
      
      <!-- ========================================== -->
      <!-- QUADRANT 3: 2D MICROSCOPIC TRAFFIC SIMULATION VIEW -->
      <!-- ========================================== -->
      <section class="card-panel rounded-xl flex-1 flex flex-col p-3.5 space-y-2 min-h-[460px] shadow-2xl">
        <div class="flex items-center justify-between border-b border-slate-800 pb-2">
          <div class="flex items-center space-x-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            <h2 class="text-xs font-bold uppercase tracking-wider text-slate-200">
              Quadrant 3: 2D Microscopic Traffic Simulation View
            </h2>
          </div>
          <div class="flex items-center space-x-2 text-[10px] font-mono">
            <span class="text-slate-400">Detector Mode:</span>
            <span class="text-cyan-400 font-bold">SUMO Stop-Bar</span>
            <span id="q3-veh-pill" class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">28 Active</span>
          </div>
        </div>

        {/* 2D Canvas Container */}
        <div class="relative flex-1 bg-slate-950 rounded-lg overflow-hidden border border-slate-800 flex items-center justify-center">
          <canvas id="simCanvas2D" width="560" height="420" class="w-full h-full object-contain"></canvas>

          {/* Flow & Speed Badge */}
          <div class="absolute top-2 left-2 px-2 py-1 rounded bg-slate-900/90 border border-slate-800 text-[9px] font-mono text-slate-300">
            ML Flow: <strong id="q3-ml-level" class="text-cyan-400">LIGHT</strong> &bull; Speed: <strong id="q3-avg-speed" class="text-white">38.5 km/h</strong>
          </div>
        </div>

        {/* Approach Stop Queues */}
        <div class="grid grid-cols-4 gap-1.5 text-center text-[9px] font-mono">
          <div class="p-1 rounded bg-slate-900 border border-slate-800">
            <div class="text-slate-400">NB Queue</div>
            <div id="q3-q-nb" class="text-cyan-400 font-bold text-xs mt-0.5">18m</div>
          </div>
          <div class="p-1 rounded bg-slate-900 border border-slate-800">
            <div class="text-slate-400">SB Queue</div>
            <div id="q3-q-sb" class="text-cyan-400 font-bold text-xs mt-0.5">16m</div>
          </div>
          <div class="p-1 rounded bg-slate-900 border border-slate-800">
            <div class="text-slate-400">EB Queue</div>
            <div id="q3-q-eb" class="text-amber-400 font-bold text-xs mt-0.5">22m</div>
          </div>
          <div class="p-1 rounded bg-slate-900 border border-slate-800">
            <div class="text-slate-400">WB Queue</div>
            <div id="q3-q-wb" class="text-amber-400 font-bold text-xs mt-0.5">19m</div>
          </div>
        </div>
      </section>

      <!-- ========================================== -->
      <!-- QUADRANT 4: SMART CITY COMMAND & OPERATION CENTER -->
      <!-- ========================================== -->
      <section class="card-panel rounded-xl flex-1 flex flex-col p-3.5 space-y-2.5 min-h-[380px] shadow-2xl">
        <div class="flex items-center justify-between border-b border-slate-800 pb-2">
          <div class="flex items-center space-x-2">
            <span class="w-2 h-2 rounded-full bg-purple-500"></span>
            <h2 class="text-xs font-bold uppercase tracking-wider text-slate-200">
              Quadrant 4: Smart City Command &amp; Operation Center &mdash; TRAFFIC MANAGEMENT
            </h2>
          </div>
          <span class="text-[10px] font-mono text-purple-300">Sector 7 Central</span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-12 gap-2.5 flex-1">
          {/* City General Index Radial Gauge (3 Cols) */}
          <div class="md:col-span-3 p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col items-center justify-between">
            <span class="text-[9px] uppercase font-bold text-slate-400 tracking-wider">City General Index</span>
            <div class="relative w-24 h-24 flex items-center justify-center">
              <svg class="w-full h-full -rotate-90" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="40" fill="none" stroke="#1e293b" stroke-width="8" />
                <circle id="cgi-circle" cx="50" cy="50" r="40" fill="none" stroke="#22c55e" stroke-width="8" stroke-dasharray="251.2" stroke-dashoffset="35" stroke-linecap="round" class="transition-all duration-700" />
              </svg>
              <div class="absolute text-center">
                <div id="cgi-val" class="text-xl font-bold font-mono text-white">89</div>
                <div class="text-[8px] font-mono text-slate-400">/ 100</div>
              </div>
            </div>
            <div class="text-[8px] font-mono text-emerald-400 font-semibold">OPTIMAL MOBILITY</div>
          </div>

          {/* Live CCTV Grid 2x2 with AI Bounding Boxes (4 Cols) */}
          <div class="md:col-span-4 p-2 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-1">
            <div class="flex justify-between items-center text-[9px] font-mono text-slate-400">
              <span class="font-bold text-slate-300 uppercase">Live CCTV Grid (2x2)</span>
              <span class="text-rose-400 flex items-center space-x-1">
                <span class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping"></span>
                <span>REC &bull; 4K</span>
              </span>
            </div>
            <div class="grid grid-cols-2 gap-1 flex-1">
              <div class="relative bg-slate-950 rounded border border-slate-800 p-1 min-h-[55px] flex flex-col justify-between">
                <div class="absolute top-2 left-3 w-7 h-5 border border-emerald-400/80 bg-emerald-500/10"></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-400"><span>CAM-01</span><span class="text-emerald-400">NB OAK</span></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-500"><span>30 FPS</span><span id="cctv-time-1">13:14:28Z</span></div>
              </div>
              <div class="relative bg-slate-950 rounded border border-slate-800 p-1 min-h-[55px] flex flex-col justify-between">
                <div class="absolute bottom-2 right-3 w-8 h-6 border border-emerald-400/80 bg-emerald-500/10"></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-400"><span>CAM-02</span><span class="text-emerald-400">SB OAK</span></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-500"><span>30 FPS</span><span id="cctv-time-2">13:14:28Z</span></div>
              </div>
              <div class="relative bg-slate-950 rounded border border-slate-800 p-1 min-h-[55px] flex flex-col justify-between">
                <div class="absolute top-3 right-4 w-9 h-5 border border-emerald-400/80 bg-emerald-500/10"></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-400"><span>CAM-03</span><span class="text-emerald-400">EB 5TH</span></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-500"><span>30 FPS</span><span id="cctv-time-3">13:14:28Z</span></div>
              </div>
              <div class="relative bg-slate-950 rounded border border-slate-800 p-1 min-h-[55px] flex flex-col justify-between">
                <div class="absolute bottom-3 left-4 w-7 h-5 border border-emerald-400/80 bg-emerald-500/10"></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-400"><span>CAM-04</span><span class="text-emerald-400">WB 5TH</span></div>
                <div class="flex justify-between text-[6px] font-mono text-slate-500"><span>30 FPS</span><span id="cctv-time-4">13:14:28Z</span></div>
              </div>
            </div>
          </div>

          {/* City Traffic GIS Map & Alerts (5 Cols) */}
          <div class="md:col-span-5 flex flex-col space-y-1.5">
            <div class="p-1.5 rounded-lg bg-slate-900/80 border border-slate-800">
              <div class="flex justify-between text-[9px] font-mono text-slate-400 mb-1">
                <span class="font-bold text-slate-300 uppercase">City Traffic GIS Map</span>
                <span class="text-cyan-400 font-bold">Oak St Corridor</span>
              </div>
              <div class="h-14 bg-slate-950 rounded border border-slate-800 relative flex items-center justify-center">
                <svg class="w-full h-full" viewBox="0 0 240 60">
                  <line x1="20" y1="15" x2="220" y2="15" stroke="#1e293b" stroke-width="1.2" />
                  <line x1="20" y1="30" x2="220" y2="30" stroke="#1e293b" stroke-width="1.2" />
                  <line x1="20" y1="45" x2="220" y2="45" stroke="#1e293b" stroke-width="1.2" />
                  <line x1="60" y1="5" x2="60" y2="55" stroke="#1e293b" stroke-width="1.2" />
                  <line x1="120" y1="5" x2="120" y2="55" stroke="#1e293b" stroke-width="1.2" />
                  <line x1="180" y1="5" x2="180" y2="55" stroke="#1e293b" stroke-width="1.2" />

                  <line id="gis-corridor-x" x1="20" y1="30" x2="220" y2="30" stroke="#38bdf8" stroke-width="3" />
                  <line id="gis-corridor-y" x1="120" y1="5" x2="120" y2="55" stroke="#38bdf8" stroke-width="3" />
                  <circle cx="120" cy="30" r="3.5" fill="#06b6d4" />
                  <circle cx="120" cy="30" r="7" fill="none" stroke="#06b6d4" stroke-width="1" class="animate-ping" />
                </svg>
              </div>
            </div>

            <div class="flex-1 p-1.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-1">
              <div class="flex justify-between text-[9px] font-mono text-slate-400">
                <span class="font-bold text-slate-300 uppercase">Real-Time Operational Alerts</span>
                <span class="text-cyan-400">Live</span>
              </div>
              <div id="q4-alerts-container" class="space-y-1 max-h-16 overflow-y-auto text-[8px] font-mono">
                <div class="p-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
                  <span class="text-cyan-400 font-bold">[ML-CONGESTION]</span> Level: LIGHT &bull; Latency: 1.48ms
                </div>
                <div class="p-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
                  <span class="text-emerald-400 font-bold">[ADAPTIVE-SIGNAL]</span> Cycle bounded at 75s &bull; Webster splits nominal
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

  </main>

  <!-- JAVASCRIPT APPLICATION LOGIC: THREE.JS, WEBSOCKET & CANVAS SIMULATION -->
  <script>
    let ws = null;
    let latestData = null;
    const queueHistory = [];

    // Initialize WebSocket connection
    function initWebSocket() {
      const loc = window.location;
      const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = loc.host || 'localhost:8000';
      const wsUrl = `${wsProto}//${host}/ws/traffic-stream`;

      const badge = document.getElementById('ws-badge');
      badge.textContent = "CONNECTING...";
      badge.className = "px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase bg-yellow-500/20 text-yellow-400 border border-yellow-500/40";

      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        badge.textContent = "LIVE 1HZ";
        badge.className = "px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/40";
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.frame_sequence) {
            latestData = payload;
            updateDashboard(payload);
          }
        } catch (e) {
          console.error("Parse error:", e);
        }
      };

      ws.onclose = () => {
        badge.textContent = "RECONNECTING...";
        badge.className = "px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse";
        setTimeout(initWebSocket, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    // Scenario Simulator handler
    function handleScenarioChange(scenario) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;

      if (scenario === 'auto') {
        ws.send(JSON.stringify({ action: "inject_incident", type: "CLEAR_INCIDENTS" }));
        ws.send(JSON.stringify({ action: "signal_override", mode: "RESUME_AUTO" }));
      } else if (scenario === 'heavy') {
        ws.send(JSON.stringify({ action: "inject_incident", approach: "NORTH", type: "ACCIDENT" }));
        ws.send(JSON.stringify({ action: "signal_override", mode: "MANUAL", phase: 1, duration: 60 }));
      } else if (scenario === 'free') {
        ws.send(JSON.stringify({ action: "inject_incident", type: "CLEAR_INCIDENTS" }));
        ws.send(JSON.stringify({ action: "signal_override", mode: "RESUME_AUTO" }));
      } else if (scenario === 'incident') {
        ws.send(JSON.stringify({ action: "inject_incident", approach: "EAST", type: "STALL" }));
      }
    }

    function resetToAuto() {
      document.getElementById('scenario-select').value = 'auto';
      handleScenarioChange('auto');
    }

    // Master Dashboard UI Update
    function updateDashboard(data) {
      const ml = data.ml_congestion_prediction;
      const ctrl = data.adaptive_signal_control;
      const v2i = data.v2i_hardware_metrics;
      const flow = data.intersection_flow;
      const city = data.city_command_metrics;
      const sim = data.simulation_2d_state;

      // Quadrant 1 updates
      const badge = document.getElementById('q1-ml-badge');
      badge.textContent = `ML: ${ml.predicted_congestion_level} (${Math.round((ml.confidence_scores[ml.predicted_congestion_level] || 0.85) * 100)}%)`;
      const levelColors = {
        'FREE': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
        'LIGHT': 'bg-blue-500/20 text-blue-400 border-blue-500/40',
        'MODERATE': 'bg-amber-500/20 text-amber-400 border-amber-500/40',
        'HEAVY': 'bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse'
      };
      badge.className = `px-2.5 py-0.5 rounded-full border text-[11px] font-mono font-bold ${levelColors[ml.predicted_congestion_level] || ''}`;

      document.getElementById('q1-phase-pill').innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400"></span><span class="font-semibold text-slate-200">Phase ${ctrl.current_phase} Active</span>`;
      document.getElementById('card-obu-cnt').textContent = `OBU (${v2i.active_obus_in_range})`;
      document.getElementById('card-v2i-lat').textContent = `${v2i.v2i_latency_ms} ms`;
      document.getElementById('card-v2i-occ').textContent = `${v2i.channel_occupancy_pct}%`;
      document.getElementById('card-cycle-txt').textContent = `${ctrl.cycle_time}s`;
      document.getElementById('card-curr-phase').textContent = `Phase ${ctrl.current_phase}`;
      document.getElementById('card-next-phase').textContent = `Phase ${ctrl.next_phase}`;
      document.getElementById('card-opt-savings').textContent = `Savings: ${flow.phase_optimization_savings.delay_saved_seconds_per_cycle}s/cyc`;

      document.getElementById('bar-v2i-lat').textContent = `${v2i.v2i_latency_ms} ms`;
      document.getElementById('bar-occ').textContent = `${v2i.channel_occupancy_pct}%`;
      document.getElementById('bar-veh-cnt').textContent = `${sim.active_vehicles_count}`;
      document.getElementById('bar-gain').textContent = `+${flow.phase_optimization_savings.baseline_vs_adaptive_gain_pct}%`;

      // Sparkline tracking
      const nbQ = flow.approaches.NORTHBOUND ? flow.approaches.NORTHBOUND.queue_length_meters : 15;
      const ebQ = flow.approaches.EASTBOUND ? flow.approaches.EASTBOUND.queue_length_meters : 18;
      queueHistory.push({ nb: nbQ, eb: ebQ });
      if (queueHistory.length > 20) queueHistory.shift();

      if (queueHistory.length > 1) {
        const ptsNb = queueHistory.map((q, i) => `${(i / (queueHistory.length - 1)) * 100},${30 - (q.nb / 80) * 26}`).join(' ');
        const ptsEb = queueHistory.map((q, i) => `${(i / (queueHistory.length - 1)) * 100},${30 - (q.eb / 80) * 26}`).join(' ');
        document.getElementById('poly-nb').setAttribute('points', ptsNb);
        document.getElementById('poly-eb').setAttribute('points', ptsEb);
      }

      // Quadrant 2 updates
      document.getElementById('q2-array-health').textContent = `${data.iot_sensor_health.overall_health_score}%`;
      document.getElementById('q2-hourly-vol').textContent = `${flow.projected_hourly_volume.toLocaleString()} veh/hr`;

      const apprs = flow.approaches;
      const nbFlow = apprs.NORTHBOUND ? apprs.NORTHBOUND.flow_rate_veh_min : 12;
      const sbFlow = apprs.SOUTHBOUND ? apprs.SOUTHBOUND.flow_rate_veh_min : 11;
      const ebFlow = apprs.EASTBOUND ? apprs.EASTBOUND.flow_rate_veh_min : 14;
      const wbFlow = apprs.WESTBOUND ? apprs.WESTBOUND.flow_rate_veh_min : 10;
      const maxF = Math.max(nbFlow, sbFlow, ebFlow, wbFlow, 25);

      document.getElementById('bar-val-nb').textContent = nbFlow;
      document.getElementById('bar-val-sb').textContent = sbFlow;
      document.getElementById('bar-val-eb').textContent = ebFlow;
      document.getElementById('bar-val-wb').textContent = wbFlow;
      document.getElementById('bar-nb').style.height = `${(nbFlow / maxF) * 100}%`;
      document.getElementById('bar-sb').style.height = `${(sbFlow / maxF) * 100}%`;
      document.getElementById('bar-eb').style.height = `${(ebFlow / maxF) * 100}%`;
      document.getElementById('bar-wb').style.height = `${(wbFlow / maxF) * 100}%`;

      document.getElementById('q2-ipi-val').textContent = city.intersection_performance_index;
      document.getElementById('q2-los-badge').textContent = `LOS: ${city.level_of_service}`;

      if (city.real_time_alerts && city.real_time_alerts.length > 0) {
        document.getElementById('q2-anomaly-banner').className = "p-1 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[9px] font-mono animate-pulse";
        document.getElementById('q2-anomaly-banner').innerHTML = `<strong>ALERT:</strong> ${city.real_time_alerts[0].message}`;
      } else {
        document.getElementById('q2-anomaly-banner').className = "p-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-[9px] font-mono";
        document.getElementById('q2-anomaly-banner').textContent = "Anomaly Detection: Nominal flow. Zero corridor shockwaves.";
      }

      // Quadrant 3 updates
      document.getElementById('q3-veh-pill').textContent = `${sim.active_vehicles_count} Active`;
      document.getElementById('q3-ml-level').textContent = ml.predicted_congestion_level;
      document.getElementById('q3-avg-speed').textContent = `${apprs.NORTHBOUND ? apprs.NORTHBOUND.avg_speed_kmh : 38.5} km/h`;
      document.getElementById('q3-q-nb').textContent = `${apprs.NORTHBOUND ? apprs.NORTHBOUND.queue_length_meters : 18}m`;
      document.getElementById('q3-q-sb').textContent = `${apprs.SOUTHBOUND ? apprs.SOUTHBOUND.queue_length_meters : 16}m`;
      document.getElementById('q3-q-eb').textContent = `${apprs.EASTBOUND ? apprs.EASTBOUND.queue_length_meters : 22}m`;
      document.getElementById('q3-q-wb').textContent = `${apprs.WESTBOUND ? apprs.WESTBOUND.queue_length_meters : 19}m`;

      render2DCanvas(sim, ctrl.signals);

      // Quadrant 4 updates
      const cgi = Math.round(city.city_general_index);
      document.getElementById('cgi-val').textContent = cgi;
      const offset = 251.2 - (251.2 * cgi) / 100;
      document.getElementById('cgi-circle').setAttribute('stroke-dashoffset', offset);
      document.getElementById('cgi-circle').setAttribute('stroke', cgi > 75 ? '#22c55e' : cgi > 50 ? '#eab308' : '#ef4444');

      const nowIso = new Date().toISOString().substring(11, 19) + 'Z';
      document.getElementById('cctv-time-1').textContent = nowIso;
      document.getElementById('cctv-time-2').textContent = nowIso;
      document.getElementById('cctv-time-3').textContent = nowIso;
      document.getElementById('cctv-time-4').textContent = nowIso;

      const corridorCol = ml.predicted_congestion_level === 'FREE' ? '#22c55e' : ml.predicted_congestion_level === 'LIGHT' ? '#38bdf8' : ml.predicted_congestion_level === 'MODERATE' ? '#eab308' : '#ef4444';
      document.getElementById('gis-corridor-x').setAttribute('stroke', corridorCol);
      document.getElementById('gis-corridor-y').setAttribute('stroke', corridorCol);

      const alertsBox = document.getElementById('q4-alerts-container');
      if (city.real_time_alerts && city.real_time_alerts.length > 0) {
        alertsBox.innerHTML = '';
        city.real_time_alerts.forEach(alt => {
          const div = document.createElement('div');
          div.className = "p-1 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300";
          div.innerHTML = `<span class="font-bold">[${alt.severity}]</span> ${alt.message}`;
          alertsBox.appendChild(div);
        });
      } else {
        alertsBox.innerHTML = `
          <div class="p-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
            <span class="text-cyan-400 font-bold">[ML-CONGESTION]</span> Level: ${ml.predicted_congestion_level} &bull; Latency: ${ml.inference_latency_ms}ms
          </div>
          <div class="p-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
            <span class="text-emerald-400 font-bold">[ADAPTIVE-SIGNAL]</span> Cycle bounded at ${ctrl.cycle_time}s &bull; Webster splits nominal
          </div>
        `;
      }

      // Update 3D scene vehicles
      update3DScene(sim, ctrl.signals);
    }

    // 2D Canvas Renderer (Quadrant 3)
    function render2DCanvas(simState, signals) {
      const canvas = document.getElementById('simCanvas2D');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const W = canvas.width;
      const H = canvas.height;
      ctx.clearRect(0, 0, W, H);

      const scale = W / 240.0;
      const cx = W / 2.0;
      const cy = H / 2.0;

      function toScreen(x, y) {
        return { sx: cx + (x * scale), sy: cy - (y * scale) };
      }

      // Road background
      ctx.fillStyle = '#090d16';
      ctx.fillRect(0, 0, W, H);

      const roadW = 26 * scale;
      ctx.fillStyle = '#162032';
      ctx.fillRect(cx - roadW / 2, 0, roadW, H);
      ctx.fillRect(0, cy - roadW / 2, W, roadW);

      // Lane dividers
      ctx.strokeStyle = '#475569';
      ctx.lineWidth = 1.2;
      ctx.setLineDash([5, 5]);

      ctx.beginPath();
      ctx.moveTo(cx, 0); ctx.lineTo(cx, cy - roadW / 2);
      ctx.moveTo(cx, cy + roadW / 2); ctx.lineTo(cx, H);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(0, cy); ctx.lineTo(cx - roadW / 2, cy);
      ctx.moveTo(cx + roadW / 2, cy); ctx.lineTo(W, cy);
      ctx.stroke();
      ctx.setLineDash([]);

      // Stop lines
      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 2.5;
      const stopDist = 16 * scale;

      ctx.beginPath(); ctx.moveTo(cx - roadW / 2, cy + stopDist); ctx.lineTo(cx, cy + stopDist); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx, cy - stopDist); ctx.lineTo(cx + roadW / 2, cy - stopDist); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx - stopDist, cy); ctx.lineTo(cx - stopDist, cy + roadW / 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx + stopDist, cy - roadW / 2); ctx.lineTo(cx + stopDist, cy); ctx.stroke();

      // Signals
      function drawSig(sx, sy, state) {
        ctx.fillStyle = '#000000';
        ctx.fillRect(sx - 6, sy - 6, 12, 12);
        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1;
        ctx.strokeRect(sx - 6, sy - 6, 12, 12);

        let color = '#ef4444';
        if (state === 'GREEN') color = '#22c55e';
        else if (state === 'YELLOW') color = '#eab308';

        ctx.beginPath();
        ctx.arc(sx, sy, 3.8, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      }

      const nbSig = signals.find(s => s.approach === 'NORTHBOUND');
      const sbSig = signals.find(s => s.approach === 'SOUTHBOUND');
      const ebSig = signals.find(s => s.approach === 'EASTBOUND');
      const wbSig = signals.find(s => s.approach === 'WESTBOUND');

      if (nbSig) drawSig(cx - roadW / 2 - 8, cy + stopDist, nbSig.state);
      if (sbSig) drawSig(cx + roadW / 2 + 8, cy - stopDist, sbSig.state);
      if (ebSig) drawSig(cx - stopDist, cy + roadW / 2 + 8, ebSig.state);
      if (wbSig) drawSig(cx + stopDist, cy - roadW / 2 - 8, wbSig.state);

      // Vehicles
      simState.vehicles.forEach(v => {
        const { sx, sy } = toScreen(v.x, v.y);
        const isTruck = v.type === 'truck' || v.type === 'bus';
        const w = (isTruck ? 5.0 : 3.8) * scale;
        const h = (isTruck ? 10.0 : 7.0) * scale;

        ctx.save();
        ctx.translate(sx, sy);

        let angle = 0;
        if (v.approach === 'NORTH') angle = 0;
        else if (v.approach === 'SOUTH') angle = Math.PI;
        else if (v.approach === 'EAST') angle = Math.PI / 2;
        else if (v.approach === 'WEST') angle = -Math.PI / 2;
        ctx.rotate(angle);

        ctx.fillStyle = v.color || '#3b82f6';
        ctx.beginPath();
        ctx.roundRect(-w / 2, -h / 2, w, h, 2);
        ctx.fill();

        ctx.fillStyle = '#0f172a';
        ctx.fillRect(-w / 2 + 0.8, -h / 2 + 1, w - 1.6, 2);

        if (v.has_obu) {
          ctx.strokeStyle = '#38bdf8';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(0, 0, w + 1, 0, Math.PI * 2);
          ctx.stroke();
        }

        ctx.restore();
      });
    }

    // 3D Isometric Viewport (Quadrant 1)
    let threeScene, threeCamera, threeRenderer, threeVehiclesGroup, threeArrowsGroup;

    function initThreeJS() {
      const container = document.getElementById('three-container');
      if (!container) return;

      const w = container.clientWidth || 560;
      const h = container.clientHeight || 460;

      threeScene = new THREE.Scene();
      threeScene.background = new THREE.Color(0x0a0e17);

      const aspect = w / h;
      const d = 55;
      threeCamera = new THREE.OrthographicCamera(-d * aspect, d * aspect, d, -d, 1, 1000);
      threeCamera.position.set(70, 70, 70);
      threeCamera.lookAt(0, 0, 0);

      threeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      threeRenderer.setSize(w, h);
      threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      threeRenderer.shadowMap.enabled = true;
      container.appendChild(threeRenderer.domElement);

      // Lighting
      threeScene.add(new THREE.AmbientLight(0xffffff, 0.75));
      const dirLight = new THREE.DirectionalLight(0x38bdf8, 1.2);
      dirLight.position.set(40, 80, 50);
      dirLight.castShadow = true;
      threeScene.add(dirLight);

      // Grid
      const grid = new THREE.GridHelper(160, 32, 0x1e293b, 0x0f172a);
      grid.position.y = -0.1;
      threeScene.add(grid);

      // Roads
      const roadMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.8 });
      const oak = new THREE.Mesh(new THREE.PlaneGeometry(22, 160), roadMat);
      oak.rotation.x = -Math.PI / 2;
      threeScene.add(oak);

      const fifth = new THREE.Mesh(new THREE.PlaneGeometry(160, 22), roadMat);
      fifth.rotation.x = -Math.PI / 2;
      fifth.position.y = 0.01;
      threeScene.add(fifth);

      // Surrounding City Skyscrapers
      const bldgMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.4 });
      const roofMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
      const offsets = [{ x: -45, z: -45, h: 28 }, { x: 45, z: -45, h: 42 }, { x: -45, z: 45, h: 32 }, { x: 45, z: 45, h: 48 }];
      offsets.forEach(b => {
        const mesh = new THREE.Mesh(new THREE.BoxGeometry(26, b.h, 26), bldgMat);
        mesh.position.set(b.x, b.h / 2, b.z);
        threeScene.add(mesh);

        const roof = new THREE.Mesh(new THREE.BoxGeometry(20, 1, 20), roofMat);
        roof.position.set(b.x, b.h + 0.5, b.z);
        threeScene.add(roof);
      });

      // RSU Center Tower
      const rsuDish = new THREE.Mesh(new THREE.SphereGeometry(1.2, 16, 16), new THREE.MeshBasicMaterial({ color: 0x22d3ee, wireframe: true }));
      rsuDish.position.set(13, 5, 13);
      threeScene.add(rsuDish);

      threeVehiclesGroup = new THREE.Group();
      threeScene.add(threeVehiclesGroup);

      threeArrowsGroup = new THREE.Group();
      threeScene.add(threeArrowsGroup);

      // Render loop
      function anim() {
        requestAnimationFrame(anim);
        rsuDish.rotation.y += 0.015;
        threeRenderer.render(threeScene, threeCamera);
      }
      anim();

      window.addEventListener('resize', () => {
        if (!container || !threeRenderer) return;
        const nw = container.clientWidth;
        const nh = container.clientHeight || 460;
        const na = nw / nh;
        threeCamera.left = -d * na;
        threeCamera.right = d * na;
        threeCamera.top = d;
        threeCamera.bottom = -d;
        threeCamera.updateProjectionMatrix();
        threeRenderer.setSize(nw, nh);
      });
    }

    function update3DScene(simState, signals) {
      if (!threeVehiclesGroup || !threeArrowsGroup) return;

      // Update vehicles
      while (threeVehiclesGroup.children.length > 0) {
        threeVehiclesGroup.remove(threeVehiclesGroup.children[0]);
      }

      const scale = 0.5;
      simState.vehicles.forEach(v => {
        const isTruck = v.type === 'truck' || v.type === 'bus';
        const geom = new THREE.BoxGeometry(isTruck ? 3.0 : 2.0, 1.2, isTruck ? 5.5 : 3.8);
        const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(v.color || 0x3b82f6), roughness: 0.3 });
        const mesh = new THREE.Mesh(geom, mat);
        mesh.position.set(v.x * scale, 0.7, -v.y * scale);

        if (v.approach === 'NORTH') mesh.rotation.y = Math.PI;
        else if (v.approach === 'SOUTH') mesh.rotation.y = 0;
        else if (v.approach === 'EAST') mesh.rotation.y = -Math.PI / 2;
        else if (v.approach === 'WEST') mesh.rotation.y = Math.PI / 2;

        if (v.has_obu) {
          const ring = new THREE.Mesh(new THREE.RingGeometry(2.0, 2.3, 16), new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide }));
          ring.rotation.x = Math.PI / 2;
          ring.position.y = 0.9;
          mesh.add(ring);
        }

        threeVehiclesGroup.add(mesh);
      });

      // Update arrows
      while (threeArrowsGroup.children.length > 0) {
        threeArrowsGroup.remove(threeArrowsGroup.children[0]);
      }

      const nbSig = signals.find(s => s.approach === 'NORTHBOUND');
      const sbSig = signals.find(s => s.approach === 'SOUTHBOUND');
      const ebSig = signals.find(s => s.approach === 'EASTBOUND');
      const wbSig = signals.find(s => s.approach === 'WESTBOUND');

      function addArr(x, z, rot, state) {
        const col = state === 'GREEN' ? 0x22c55e : state === 'YELLOW' ? 0xeab308 : 0xef4444;
        const arrow = new THREE.Mesh(new THREE.ConeGeometry(1.6, 3.2, 3), new THREE.MeshBasicMaterial({ color: col }));
        arrow.rotation.x = -Math.PI / 2;
        arrow.rotation.z = rot;
        arrow.position.set(x, 0.1, z);
        threeArrowsGroup.add(arrow);
      }

      addArr(-2, 10, 0, nbSig ? nbSig.state : 'RED');
      addArr(2, -10, Math.PI, sbSig ? sbSig.state : 'RED');
      addArr(-10, -2, -Math.PI / 2, ebSig ? ebSig.state : 'RED');
      addArr(10, 2, Math.PI / 2, wbSig ? wbSig.state : 'RED');
    }

    window.addEventListener('DOMContentLoaded', () => {
      initThreeJS();
      initWebSocket();
    });
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
