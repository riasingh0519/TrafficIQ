import React, { useEffect, useState, useRef } from "react";
import { TrafficStreamPayload } from "./types/traffic";
import { Quadrant1_3DDigitalTwin } from "./components/Quadrant1_3DDigitalTwin";
import { Quadrant2_SensorAnalytics } from "./components/Quadrant2_SensorAnalytics";
import { Quadrant3_2DSimulation } from "./components/Quadrant3_2DSimulation";
import { Quadrant4_CityCommand } from "./components/Quadrant4_CityCommand";

export const App: React.FC = () => {
  const [data, setData] = useState<TrafficStreamPayload | null>(null);
  const [wsStatus, setWsStatus] = useState<"CONNECTING" | "LIVE" | "DISCONNECTED">("CONNECTING");
  const [activeScenario, setActiveScenario] = useState<string>("auto");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const loc = window.location;
    const wsProto = loc.protocol === "https:" ? "wss:" : "ws:";
    const host = loc.host || "localhost:8000";
    const wsUrl = `${wsProto}//${host}/ws/traffic-stream`;

    let socket: WebSocket;
    const connect = () => {
      setWsStatus("CONNECTING");
      socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        setWsStatus("LIVE");
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.frame_sequence) {
            setData(payload);
          }
        } catch (e) {
          console.error("WebSocket message parsing error:", e);
        }
      };

      socket.onclose = () => {
        setWsStatus("DISCONNECTED");
        setTimeout(connect, 2000);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Handle Scenario Simulator dropdown changes
  const handleScenarioChange = (scenario: string) => {
    setActiveScenario(scenario);
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    if (scenario === "auto") {
      wsRef.current.send(JSON.stringify({ action: "inject_incident", type: "CLEAR_INCIDENTS" }));
      wsRef.current.send(JSON.stringify({ action: "signal_override", mode: "RESUME_AUTO" }));
    } else if (scenario === "heavy") {
      wsRef.current.send(JSON.stringify({ action: "inject_incident", approach: "NORTH", type: "ACCIDENT" }));
      wsRef.current.send(JSON.stringify({ action: "signal_override", mode: "MANUAL", phase: 1, duration: 60 }));
    } else if (scenario === "free") {
      wsRef.current.send(JSON.stringify({ action: "inject_incident", type: "CLEAR_INCIDENTS" }));
      wsRef.current.send(JSON.stringify({ action: "signal_override", mode: "RESUME_AUTO" }));
    } else if (scenario === "incident") {
      wsRef.current.send(JSON.stringify({ action: "inject_incident", approach: "EAST", type: "STALL" }));
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col p-3 space-y-3 font-sans selection:bg-cyan-500 selection:text-black">
      {/* GLOBAL TOP COMMAND BAR */}
      <header className="px-5 py-3 rounded-xl bg-slate-900/90 border border-slate-800 backdrop-blur-md flex flex-wrap items-center justify-between gap-4 shadow-2xl">
        <div className="flex items-center space-x-3.5">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <span className="font-bold text-white text-base">DT</span>
          </div>
          <div>
            <h1 className="text-base font-extrabold tracking-wide text-white flex items-center space-x-2">
              <span>METROPOLIS ITS DIGITAL TWIN &bull; DUAL-SCREEN COMMAND CENTER</span>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase ${
                  wsStatus === "LIVE"
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                    : "bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse"
                }`}
              >
                {wsStatus} 1HZ
              </span>
            </h1>
            <p className="text-[11px] text-slate-400">
              V2I IEEE 802.11p / C-V2X &bull; SHAP TreeExplainer &bull; Webster Dynamic Adaptive Optimization
            </p>
          </div>
        </div>

        {/* SCENARIO SIMULATOR DROPDOWN & DEMO CONTROLS */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
            <label htmlFor="scenario-select" className="text-xs font-mono font-bold text-slate-400 uppercase">
              Scenario Simulator:
            </label>
            <select
              id="scenario-select"
              value={activeScenario}
              onChange={(e) => handleScenarioChange(e.target.value)}
              className="bg-slate-900 text-cyan-300 font-mono text-xs font-bold rounded px-2 py-1 border border-slate-700 focus:outline-none focus:border-cyan-400 cursor-pointer"
            >
              <option value="auto">Auto ML Live (Autonomous)</option>
              <option value="heavy">Simulate Rush Hour Heavy</option>
              <option value="free">Simulate Free Flow (Midnight)</option>
              <option value="incident">Simulate Incident Anomaly (Stall)</option>
            </select>
          </div>

          <button
            onClick={() => handleScenarioChange("auto")}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-mono font-semibold text-slate-300 border border-slate-700 transition"
          >
            Reset
          </button>
        </div>
      </header>

      {/* DUAL-SCREEN 4-QUADRANT GRID */}
      <main className="grid grid-cols-1 xl:grid-cols-2 gap-3 flex-1">
        {/* OPERATIONAL SCREEN 1: LEFT DUAL-QUADRANT */}
        <div className="flex flex-col space-y-3">
          {/* Quadrant 1: 3D Isometric Intersection Digital Twin & V2I */}
          <div className="flex-1">
            <Quadrant1_3DDigitalTwin data={data} />
          </div>

          {/* Quadrant 2: IoT Sensor Network & Traffic Data Analytics */}
          <div className="flex-1">
            <Quadrant2_SensorAnalytics data={data} />
          </div>
        </div>

        {/* OPERATIONAL SCREEN 2: RIGHT DUAL-QUADRANT */}
        <div className="flex flex-col space-y-3">
          {/* Quadrant 3: 2D Microscopic Traffic Simulation View */}
          <div className="flex-1">
            <Quadrant3_2DSimulation data={data} />
          </div>

          {/* Quadrant 4: Smart City Command & Operation Center */}
          <div className="flex-1">
            <Quadrant4_CityCommand data={data} />
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;

