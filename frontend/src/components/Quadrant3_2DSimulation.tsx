import React, { useEffect, useRef, useState } from "react";
import { TrafficStreamPayload, SimulatedVehicle } from "../types/traffic";

interface Props {
  data: TrafficStreamPayload | null;
}

export const Quadrant3_2DSimulation: React.FC<Props> = ({ data }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredVehicle, setHoveredVehicle] = useState<SimulatedVehicle | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // Scale from physics meters (-120 to +120) to Canvas pixels
    const scale = W / 240.0;
    const cx = W / 2.0;
    const cy = H / 2.0;

    const toScreen = (x: number, y: number) => ({
      sx: cx + x * scale,
      sy: cy - y * scale,
    });

    // 1. Draw Asphalt Background & Cross Intersection
    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, W, H);

    // Oak Street (Vertical North-South)
    const roadW = 26 * scale;
    ctx.fillStyle = "#162032";
    ctx.fillRect(cx - roadW / 2, 0, roadW, H);

    // 5th Avenue (Horizontal East-West)
    ctx.fillRect(0, cy - roadW / 2, W, roadW);

    // 2. Dashed Center & Lane Dividers
    ctx.strokeStyle = "#475569";
    ctx.lineWidth = 1.2;
    ctx.setLineDash([6, 6]);

    // Oak St center line
    ctx.beginPath();
    ctx.moveTo(cx, 0);
    ctx.lineTo(cx, cy - roadW / 2);
    ctx.moveTo(cx, cy + roadW / 2);
    ctx.lineTo(cx, H);
    ctx.stroke();

    // 5th Ave center line
    ctx.beginPath();
    ctx.moveTo(0, cy);
    ctx.lineTo(cx - roadW / 2, cy);
    ctx.moveTo(cx + roadW / 2, cy);
    ctx.lineTo(W, cy);
    ctx.stroke();
    ctx.setLineDash([]);

    // 3. Stop Lines (Solid White Bars)
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 2.5;
    const stopDist = 16 * scale;

    // NB Stop Line
    ctx.beginPath();
    ctx.moveTo(cx - roadW / 2, cy + stopDist);
    ctx.lineTo(cx, cy + stopDist);
    ctx.stroke();

    // SB Stop Line
    ctx.beginPath();
    ctx.moveTo(cx, cy - stopDist);
    ctx.lineTo(cx + roadW / 2, cy - stopDist);
    ctx.stroke();

    // EB Stop Line
    ctx.beginPath();
    ctx.moveTo(cx - stopDist, cy);
    ctx.lineTo(cx - stopDist, cy + roadW / 2);
    ctx.stroke();

    // WB Stop Line
    ctx.beginPath();
    ctx.moveTo(cx + stopDist, cy - roadW / 2);
    ctx.lineTo(cx + stopDist, cy);
    ctx.stroke();

    // 4. In-Pavement Inductive Loop Detectors
    const drawLoop = (sx: number, sy: number, active: boolean) => {
      ctx.fillStyle = active ? "rgba(34, 197, 94, 0.4)" : "rgba(71, 85, 105, 0.25)";
      ctx.strokeStyle = active ? "#22c55e" : "#475569";
      ctx.lineWidth = 1;
      ctx.fillRect(sx - 4, sy - 6, 8, 12);
      ctx.strokeRect(sx - 4, sy - 6, 8, 12);
    };

    // Draw loop detectors at approaches
    drawLoop(cx - roadW / 4, cy + stopDist + 6, true);
    drawLoop(cx + roadW / 4, cy - stopDist - 6, true);
    drawLoop(cx - stopDist - 6, cy + roadW / 4, true);
    drawLoop(cx + stopDist + 6, cy - roadW / 4, true);

    // 5. Traffic Signal Lights
    const signals = data.adaptive_signal_control.signals;
    const drawSignal = (sx: number, sy: number, state: string, label: string) => {
      ctx.fillStyle = "#000000";
      ctx.fillRect(sx - 7, sy - 7, 14, 14);
      ctx.strokeStyle = "#334155";
      ctx.lineWidth = 1;
      ctx.strokeRect(sx - 7, sy - 7, 14, 14);

      let color = "#ef4444";
      if (state === "GREEN") color = "#22c55e";
      else if (state === "YELLOW") color = "#eab308";

      ctx.beginPath();
      ctx.arc(sx, sy, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    };

    const nbSig = signals.find((s) => s.approach === "NORTHBOUND" && s.movement === "THROUGH_RIGHT");
    const sbSig = signals.find((s) => s.approach === "SOUTHBOUND" && s.movement === "THROUGH_RIGHT");
    const ebSig = signals.find((s) => s.approach === "EASTBOUND" && s.movement === "THROUGH_RIGHT");
    const wbSig = signals.find((s) => s.approach === "WESTBOUND" && s.movement === "THROUGH_RIGHT");

    if (nbSig) drawSignal(cx - roadW / 2 - 10, cy + stopDist, nbSig.state, "NB");
    if (sbSig) drawSignal(cx + roadW / 2 + 10, cy - stopDist, sbSig.state, "SB");
    if (ebSig) drawSignal(cx - stopDist, cy + roadW / 2 + 10, ebSig.state, "EB");
    if (wbSig) drawSignal(cx + stopDist, cy - roadW / 2 - 10, wbSig.state, "WB");

    // 6. Draw Simulated Microscopic Vehicles
    data.simulation_2d_state.vehicles.forEach((v) => {
      const { sx, sy } = toScreen(v.x, v.y);
      const isTruck = v.type === "truck" || v.type === "bus";
      const w = (isTruck ? 5.2 : 4.2) * scale;
      const h = (isTruck ? 11.0 : 7.5) * scale;

      ctx.save();
      ctx.translate(sx, sy);

      // Rotation angle
      let angle = 0;
      if (v.approach === "NORTH") angle = 0;
      else if (v.approach === "SOUTH") angle = Math.PI;
      else if (v.approach === "EAST") angle = Math.PI / 2;
      else if (v.approach === "WEST") angle = -Math.PI / 2;
      ctx.rotate(angle);

      // Vehicle Bounding Box
      ctx.fillStyle = v.color || "#3b82f6";
      ctx.beginPath();
      ctx.roundRect(-w / 2, -h / 2, w, h, 2);
      ctx.fill();
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Windshield
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(-w / 2 + 1, -h / 2 + 1.2, w - 2, 2.2);

      // Headlights on Green/Moving
      if (v.speed_kmh > 5) {
        ctx.fillStyle = "#fef08a";
        ctx.fillRect(-w / 2 + 0.8, -h / 2, 1.2, 0.8);
        ctx.fillRect(w / 2 - 2.0, -h / 2, 1.2, 0.8);
      }

      // Connected OBU Indicator Halo
      if (v.has_obu) {
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(0, 0, w + 1.5, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.restore();
    });
  }, [data]);

  return (
    <div className="w-full h-full min-h-[480px] flex flex-col bg-slate-950 border border-slate-800 rounded-xl overflow-hidden p-4 space-y-3">
      {/* SECTION HEADER */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Quadrant 3: 2D Microscopic Traffic Simulation View
          </h2>
        </div>
        <div className="flex items-center space-x-3 text-[11px] font-mono">
          <span className="text-slate-400">Detector Mode:</span>
          <span className="text-cyan-400 font-bold">SUMO-Style Stop-Bar</span>
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">
            {data?.simulation_2d_state.active_vehicles_count || 28} Active
          </span>
        </div>
      </div>

      {/* CANVAS CONTAINER */}
      <div className="relative flex-1 bg-slate-950 rounded-lg overflow-hidden border border-slate-800/80 flex items-center justify-center">
        <canvas
          ref={canvasRef}
          width={540}
          height={500}
          className="w-full h-full object-contain cursor-crosshair"
        />

        {/* Dynamic Congestion Speed Banner */}
        <div className="absolute top-2 left-2 px-2.5 py-1 rounded bg-slate-900/90 border border-slate-800 text-[10px] font-mono text-slate-300">
          ML Flow:{" "}
          <strong className="text-cyan-400">
            {data?.ml_congestion_prediction.predicted_congestion_level || "LIGHT"}
          </strong>{" "}
          &bull; Avg Speed:{" "}
          <strong className="text-white">
            {data?.intersection_flow.approaches.NORTHBOUND?.avg_speed_kmh || 38.5} km/h
          </strong>
        </div>

        {/* Legend */}
        <div className="absolute bottom-2 right-2 px-2.5 py-1.5 rounded bg-slate-900/90 border border-slate-800 text-[9px] font-mono space-y-0.5 text-slate-400">
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-blue-500 inline-block"></span>
            <span>Sedan / SUV</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-500 inline-block"></span>
            <span>Commercial Truck / Bus</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full border border-sky-400 inline-block"></span>
            <span>V2I OBU Radio Link</span>
          </div>
        </div>
      </div>

      {/* STOP-BAR QUEUE LENGTHS */}
      <div className="grid grid-cols-4 gap-2 text-center text-[10px] font-mono">
        <div className="p-1.5 rounded bg-slate-900 border border-slate-800">
          <span className="text-slate-400">NB Stop Queue</span>
          <div className="text-cyan-400 font-bold text-xs mt-0.5">
            {data?.intersection_flow.approaches.NORTHBOUND?.queue_length_meters || 18}m
          </div>
        </div>
        <div className="p-1.5 rounded bg-slate-900 border border-slate-800">
          <span className="text-slate-400">SB Stop Queue</span>
          <div className="text-cyan-400 font-bold text-xs mt-0.5">
            {data?.intersection_flow.approaches.SOUTHBOUND?.queue_length_meters || 16}m
          </div>
        </div>
        <div className="p-1.5 rounded bg-slate-900 border border-slate-800">
          <span className="text-slate-400">EB Stop Queue</span>
          <div className="text-amber-400 font-bold text-xs mt-0.5">
            {data?.intersection_flow.approaches.EASTBOUND?.queue_length_meters || 22}m
          </div>
        </div>
        <div className="p-1.5 rounded bg-slate-900 border border-slate-800">
          <span className="text-slate-400">WB Stop Queue</span>
          <div className="text-amber-400 font-bold text-xs mt-0.5">
            {data?.intersection_flow.approaches.WESTBOUND?.queue_length_meters || 19}m
          </div>
        </div>
      </div>
    </div>
  );
};

