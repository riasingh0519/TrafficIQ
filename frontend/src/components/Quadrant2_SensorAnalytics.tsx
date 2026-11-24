import React from "react";
import { TrafficStreamPayload } from "../types/traffic";

interface Props {
  data: TrafficStreamPayload | null;
}

export const Quadrant2_SensorAnalytics: React.FC<Props> = ({ data }) => {
  const apprs = data?.intersection_flow.approaches;
  const city = data?.city_command_metrics;
  const iot = data?.iot_sensor_health;

  const nbVol = Math.round((apprs?.NORTHBOUND?.flow_rate_veh_min || 12) * 60);
  const sbVol = Math.round((apprs?.SOUTHBOUND?.flow_rate_veh_min || 11) * 60);
  const ebVol = Math.round((apprs?.EASTBOUND?.flow_rate_veh_min || 14) * 60);
  const wbVol = Math.round((apprs?.WESTBOUND?.flow_rate_veh_min || 10) * 60);

  const maxVol = Math.max(nbVol, sbVol, ebVol, wbVol, 1200);

  const times = city?.directional_travel_times_minutes || {
    Oak_Street_NB_to_SB: 3.1,
    Oak_Street_SB_to_NB: 2.9,
    "5th_Avenue_EB_to_WB": 2.5,
    "5th_Avenue_WB_to_EB": 2.6,
  };

  const avgTravelTime = (
    Object.values(times).reduce((a, b) => a + b, 0) / Math.max(1, Object.keys(times).length)
  ).toFixed(1);

  const ipi = city?.intersection_performance_index || 88.5;
  const los = city?.level_of_service || "A";

  const losColor =
    los === "A" || los === "B"
      ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
      : los === "C" || los === "D"
      ? "text-yellow-400 border-yellow-500/40 bg-yellow-500/10"
      : "text-rose-400 border-rose-500/40 bg-rose-500/10";

  return (
    <div className="w-full h-full min-h-[440px] flex flex-col bg-slate-950 border border-slate-800 rounded-xl overflow-hidden p-4 space-y-4">
      {/* SECTION HEADER */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
        <div className="flex items-center space-x-2.5">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Quadrant 2: IoT Sensor Network &amp; Traffic Data Analytics
          </h2>
        </div>
        <div className="flex items-center space-x-2 text-[11px] font-mono">
          <span className="text-slate-400">IoT Array Health:</span>
          <span className="text-emerald-400 font-bold">
            {iot?.overall_health_score || 99.2}%
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1">
        {/* LEFT SUB-PANEL: IoT Sensor Network Radar View */}
        <div className="p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-slate-300 uppercase tracking-wide">
              IoT Sensor Network Map Overlay
            </span>
            <span className="text-[10px] font-mono text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
              RADAR ACTIVE
            </span>
          </div>

          {/* Schematic Radar View */}
          <div className="relative flex-1 min-h-[160px] bg-slate-950 rounded-lg border border-slate-800/80 overflow-hidden flex items-center justify-center">
            {/* Concentric Radar Rings */}
            <div className="absolute w-36 h-36 rounded-full border border-slate-800"></div>
            <div className="absolute w-24 h-24 rounded-full border border-slate-800/80"></div>
            <div className="absolute w-12 h-12 rounded-full border border-slate-800/60"></div>
            <div className="absolute w-full h-[1px] bg-slate-800/60"></div>
            <div className="absolute h-full w-[1px] bg-slate-800/60"></div>

            {/* Rotating Radar Sweep Line */}
            <div className="absolute w-24 h-24 rounded-full border-r border-t border-cyan-500/40 animate-spin"></div>

            {/* Sensor Nodes & Cones */}
            {/* Traffic Cameras (Red Cones) */}
            <div className="absolute top-3 left-1/2 -translate-x-1/2 text-center">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block shadow-lg shadow-rose-500/50"></span>
              <div className="text-[8px] font-mono text-rose-400">CAM-NB (4K)</div>
            </div>
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 text-center">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block shadow-lg shadow-rose-500/50"></span>
              <div className="text-[8px] font-mono text-rose-400">CAM-SB (4K)</div>
            </div>

            {/* 3D LiDAR (Blue Cones) */}
            <div className="absolute left-4 top-1/2 -translate-y-1/2 text-center">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-400 inline-block shadow-lg shadow-blue-400/50"></span>
              <div className="text-[8px] font-mono text-blue-300">LiDAR-EB</div>
            </div>
            <div className="absolute right-4 top-1/2 -translate-y-1/2 text-center">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-400 inline-block shadow-lg shadow-blue-400/50"></span>
              <div className="text-[8px] font-mono text-blue-300">LiDAR-WB</div>
            </div>

            {/* RSU Center Gateway (Yellow) */}
            <div className="absolute z-10 text-center">
              <span className="w-3.5 h-3.5 rounded-full bg-amber-400 inline-block shadow-lg shadow-amber-400/60 animate-pulse"></span>
              <div className="text-[8px] font-mono text-amber-300 font-bold">RSU-SC74</div>
            </div>

            {/* Loop Detectors (Green) */}
            <div className="absolute top-10 left-12 w-2 h-1 bg-emerald-400 rounded-sm"></div>
            <div className="absolute bottom-10 right-12 w-2 h-1 bg-emerald-400 rounded-sm"></div>
          </div>

          {/* Sensor Array Health Badges */}
          <div className="grid grid-cols-4 gap-1.5 text-center text-[10px] font-mono">
            <div className="p-1 rounded bg-slate-950 border border-slate-800">
              <div className="text-rose-400 font-bold">Cameras</div>
              <div className="text-slate-400">30 FPS &bull; 99%</div>
            </div>
            <div className="p-1 rounded bg-slate-950 border border-slate-800">
              <div className="text-blue-400 font-bold">LiDAR</div>
              <div className="text-slate-400">20 Hz &bull; 98%</div>
            </div>
            <div className="p-1 rounded bg-slate-950 border border-slate-800">
              <div className="text-emerald-400 font-bold">Loops (8/8)</div>
              <div className="text-slate-400">100 Hz &bull; 100%</div>
            </div>
            <div className="p-1 rounded bg-slate-950 border border-slate-800">
              <div className="text-amber-400 font-bold">RSU C-V2X</div>
              <div className="text-slate-400">-68 dBm</div>
            </div>
          </div>
        </div>

        {/* RIGHT SUB-PANEL: Traffic Analytics, Travel Times, & Anomaly Alert */}
        <div className="p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-slate-300 uppercase tracking-wide">
              Traffic Data Analytics Panel
            </span>
            <span className="text-[10px] font-mono text-slate-400">
              Hourly: <strong className="text-white">{data?.intersection_flow.projected_hourly_volume || 2400} veh/hr</strong>
            </span>
          </div>

          {/* Real-time Traffic Volume (Veh/hr) Vertical Bar Chart */}
          <div className="space-y-1">
            <div className="text-[10px] uppercase font-mono text-slate-400 flex justify-between">
              <span>Traffic Volume (Veh/hr) by Approach</span>
              <span className="text-cyan-400">Demand Distribution</span>
            </div>
            <div className="grid grid-cols-4 gap-2 h-20 items-end bg-slate-950/70 p-2 rounded border border-slate-800">
              {[
                { name: "NB", vol: nbVol, col: "bg-blue-500" },
                { name: "SB", vol: sbVol, col: "bg-cyan-500" },
                { name: "EB", vol: ebVol, col: "bg-amber-500" },
                { name: "WB", vol: wbVol, col: "bg-purple-500" },
              ].map((item) => (
                <div key={item.name} className="flex flex-col items-center h-full justify-end">
                  <span className="text-[9px] font-mono text-slate-300 mb-0.5">{item.vol}</span>
                  <div
                    className={`w-full ${item.col} rounded-t transition-all duration-500`}
                    style={{ height: `${Math.max(12, (item.vol / maxVol) * 100)}%` }}
                  />
                  <span className="text-[9px] font-mono text-slate-400 mt-0.5">{item.name}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Average Travel Time Horizontal Bars */}
          <div className="space-y-1.5 text-[10px] font-mono">
            <div className="flex justify-between items-center text-slate-400">
              <span>Avg Travel Time by Direction</span>
              <span className="px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 font-bold">
                {avgTravelTime} min avg
              </span>
            </div>
            <div className="space-y-1">
              <div>
                <div className="flex justify-between text-slate-400 text-[9px]">
                  <span>Oak St NB &rarr; SB</span>
                  <span className="text-slate-200">{times.Oak_Street_NB_to_SB} min</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-blue-400 h-full rounded-full"
                    style={{ width: `${Math.min(100, (times.Oak_Street_NB_to_SB / 5) * 100)}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-slate-400 text-[9px]">
                  <span>5th Ave EB &rarr; WB</span>
                  <span className="text-slate-200">{times["5th_Avenue_EB_to_WB"]} min</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-amber-400 h-full rounded-full"
                    style={{ width: `${Math.min(100, (times["5th_Avenue_EB_to_WB"] / 5) * 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Intersection Performance Index Status Bar */}
          <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800 text-xs">
            <div className="flex items-center space-x-2">
              <span className="text-slate-400 text-[11px]">Performance Index:</span>
              <span className="font-mono font-bold text-white">{ipi} / 100</span>
            </div>
            <div className={`px-2 py-0.5 rounded font-mono font-bold text-xs border ${losColor}`}>
              LOS: {los}
            </div>
          </div>

          {/* Anomaly Detection Live Warning Banner */}
          {city?.real_time_alerts && city.real_time_alerts.length > 0 ? (
            <div className="p-2 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px] flex items-center space-x-2 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-rose-500"></span>
              <span>
                <strong>ALERT:</strong> {city.real_time_alerts[0].message}
              </span>
            </div>
          ) : (
            <div className="p-1.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-[10px] flex items-center space-x-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span>Anomaly Detection: Nominal flow. Zero corridor shockwaves detected.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

