import React from "react";
import { TrafficStreamPayload } from "../types/traffic";

interface Props {
  data: TrafficStreamPayload | null;
}

export const Quadrant4_CityCommand: React.FC<Props> = ({ data }) => {
  const city = data?.city_command_metrics;
  const cgi = city?.city_general_index || 88.5;
  const alerts = city?.real_time_alerts || [];
  const level = data?.ml_congestion_prediction.predicted_congestion_level || "LIGHT";

  // Corridor congestion colors based on ML level
  const corridorColor =
    level === "FREE"
      ? "#22c55e"
      : level === "LIGHT"
      ? "#38bdf8"
      : level === "MODERATE"
      ? "#eab308"
      : "#ef4444";

  return (
    <div className="w-full h-full min-h-[440px] flex flex-col bg-slate-950 border border-slate-800 rounded-xl overflow-hidden p-4 space-y-3">
      {/* SECTION HEADER */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2.5">
          <span className="w-2.5 h-2.5 rounded-full bg-purple-500"></span>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Quadrant 4: Smart City Command &amp; Operation Center &mdash; TRAFFIC MANAGEMENT
          </h2>
        </div>
        <div className="flex items-center space-x-2 text-[11px] font-mono">
          <span className="text-slate-400">Jurisdiction:</span>
          <span className="text-purple-300 font-bold">Metropolis Core Sector 7</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 flex-1">
        {/* SUB-SECTION 1: City General Index Radial Gauge & Sparkline (3 Cols) */}
        <div className="md:col-span-3 p-3 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col items-center justify-between space-y-2">
          <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
            City General Index
          </div>

          {/* Radial Circular Gauge */}
          <div className="relative w-28 h-28 flex items-center justify-center">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="none"
                stroke="#1e293b"
                strokeWidth="8"
              />
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="none"
                stroke={cgi > 75 ? "#22c55e" : cgi > 50 ? "#eab308" : "#ef4444"}
                strokeWidth="8"
                strokeDasharray="251.2"
                strokeDashoffset={251.2 - (251.2 * cgi) / 100}
                strokeLinecap="round"
                className="transition-all duration-700 ease-out"
              />
            </svg>
            <div className="absolute text-center">
              <div className="text-2xl font-bold font-mono text-white tracking-tight">
                {Math.round(cgi)}
              </div>
              <div className="text-[9px] font-mono text-slate-400">/ 100</div>
            </div>
          </div>

          <div className="w-full text-center">
            <div className="text-[9px] font-mono text-emerald-400 font-semibold">
              OPTIMAL MOBILITY &bull; LOS {city?.level_of_service || "A"}
            </div>
            {/* Sparkline */}
            <div className="h-6 w-full mt-1.5 flex items-end justify-between px-2 bg-slate-950/60 rounded border border-slate-800">
              {[82, 85, 87, 86, 89, 90, cgi].map((val, idx) => (
                <div
                  key={idx}
                  className="w-2 bg-purple-500/80 rounded-t"
                  style={{ height: `${Math.max(4, ((val - 60) / 40) * 100)}%` }}
                />
              ))}
            </div>
          </div>
        </div>

        {/* SUB-SECTION 2: Live CCTV Grid 2x2 with AI Bounding Box Overlays (4 Cols) */}
        <div className="md:col-span-4 p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-1.5">
          <div className="flex justify-between items-center text-[10px] font-mono text-slate-400">
            <span className="font-bold text-slate-300 uppercase">Live CCTV Grid (2x2)</span>
            <span className="text-rose-400 flex items-center space-x-1">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping"></span>
              <span>REC &bull; 4K</span>
            </span>
          </div>

          <div className="grid grid-cols-2 gap-1.5 flex-1">
            {[
              { id: "CAM-01", label: "NB OAK ST", conf: "98.4%", bbox: "top-4 left-6 w-8 h-6" },
              { id: "CAM-02", label: "SB OAK ST", conf: "97.2%", bbox: "top-6 right-4 w-9 h-7" },
              { id: "CAM-03", label: "EB 5TH AVE", conf: "99.1%", bbox: "bottom-3 left-4 w-10 h-6" },
              { id: "CAM-04", label: "WB 5TH AVE", conf: "96.5%", bbox: "bottom-4 right-5 w-8 h-5" },
            ].map((cam) => (
              <div
                key={cam.id}
                className="relative bg-slate-950 rounded border border-slate-800 overflow-hidden flex flex-col justify-between p-1 min-h-[68px]"
              >
                {/* Simulated scanlines */}
                <div className="absolute inset-0 bg-gradient-to-b from-transparent via-cyan-500/5 to-transparent pointer-events-none opacity-40"></div>

                {/* AI Detection Bounding Box */}
                <div
                  className={`absolute ${cam.bbox} border border-emerald-400/80 bg-emerald-500/10 rounded-sm`}
                >
                  <span className="absolute -top-3 left-0 text-[6px] font-mono text-emerald-300 bg-slate-900/90 px-0.5">
                    VEH {cam.conf}
                  </span>
                </div>

                <div className="flex justify-between text-[7px] font-mono text-slate-400 z-10">
                  <span>{cam.id}</span>
                  <span className="text-emerald-400">{cam.label}</span>
                </div>

                <div className="flex justify-between text-[7px] font-mono text-slate-500 z-10">
                  <span>29.97 FPS</span>
                  <span>{new Date().toISOString().substring(11, 19)}Z</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* SUB-SECTION 3: City Traffic GIS Map & Live Alert Log (5 Cols) */}
        <div className="md:col-span-5 flex flex-col space-y-2">
          {/* City Traffic GIS Map */}
          <div className="p-2 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-1">
            <div className="flex justify-between text-[10px] font-mono text-slate-400">
              <span className="font-bold text-slate-300 uppercase">City Traffic GIS Corridor Map</span>
              <span className="text-cyan-400 font-bold">Sector 7 Central</span>
            </div>

            <div className="h-20 bg-slate-950 rounded border border-slate-800/80 relative overflow-hidden flex items-center justify-center">
              <svg className="w-full h-full" viewBox="0 0 300 80">
                {/* Adjacent City Grid Lines */}
                <line x1="20" y1="20" x2="280" y2="20" stroke="#1e293b" strokeWidth="1.5" />
                <line x1="20" y1="40" x2="280" y2="40" stroke="#1e293b" strokeWidth="1.5" />
                <line x1="20" y1="60" x2="280" y2="60" stroke="#1e293b" strokeWidth="1.5" />
                <line x1="80" y1="5" x2="80" y2="75" stroke="#1e293b" strokeWidth="1.5" />
                <line x1="150" y1="5" x2="150" y2="75" stroke="#1e293b" strokeWidth="1.5" />
                <line x1="220" y1="5" x2="220" y2="75" stroke="#1e293b" strokeWidth="1.5" />

                {/* Primary Arterials */}
                {/* 5th Avenue (Horizontal Corridor) */}
                <line x1="20" y1="40" x2="280" y2="40" stroke={corridorColor} strokeWidth="3.5" />

                {/* Oak Street (Vertical Corridor) */}
                <line x1="150" y1="5" x2="150" y2="75" stroke={corridorColor} strokeWidth="3.5" />

                {/* Intersection Node SC-INT-74 */}
                <circle cx="150" cy="40" r="4.5" fill="#06b6d4" stroke="#ffffff" strokeWidth="1.2" />
                <circle cx="150" cy="40" r="9" fill="none" stroke="#06b6d4" strokeWidth="1" className="animate-ping" />
              </svg>

              <div className="absolute top-1 left-2 text-[8px] font-mono text-slate-400">
                Oak St &amp; 5th Ave Arterial Grid
              </div>
            </div>
          </div>

          {/* Real-Time Live Scrolling Alerts Log */}
          <div className="flex-1 p-2 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-1">
            <div className="flex justify-between text-[10px] font-mono text-slate-400">
              <span className="font-bold text-slate-300 uppercase">Real-Time Operational Alerts</span>
              <span className="text-cyan-400">Auto Scroll</span>
            </div>

            <div className="space-y-1 max-h-24 overflow-y-auto pr-1 text-[9px] font-mono">
              {alerts.length > 0 ? (
                alerts.map((alt) => (
                  <div
                    key={alt.alert_id}
                    className="p-1 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300"
                  >
                    <span className="font-bold">[{alt.severity}]</span> {alt.message}
                  </div>
                ))
              ) : (
                <>
                  <div className="p-1 rounded bg-slate-950 border border-slate-800/80 text-slate-300">
                    <span className="text-cyan-400 font-bold">[ML-CONGESTION]</span> Prediction: {level} &bull; Latency: {data?.ml_congestion_prediction.inference_latency_ms}ms
                  </div>
                  <div className="p-1 rounded bg-slate-950 border border-slate-800/80 text-slate-300">
                    <span className="text-emerald-400 font-bold">[ADAPTIVE-SIGNAL]</span> Cycle dynamically bounded at {data?.adaptive_signal_control.cycle_time}s &bull; Webster splits active
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

