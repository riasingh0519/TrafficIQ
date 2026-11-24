import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { TrafficStreamPayload, SignalColor } from "../types/traffic";

interface Props {
  data: TrafficStreamPayload | null;
}

export const Quadrant1_3DDigitalTwin: React.FC<Props> = ({ data }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const vehiclesGroupRef = useRef<THREE.Group | null>(null);
  const arrowsGroupRef = useRef<THREE.Group | null>(null);

  // Store queue length history for the multi-line chart
  const [queueHistory, setQueueHistory] = useState<Array<{ nb: number; sb: number; eb: number; wb: number }>>([]);

  useEffect(() => {
    if (!data) return;
    const apprs = data.intersection_flow.approaches;
    const nbQ = apprs.NORTHBOUND?.queue_length_meters || 0;
    const sbQ = apprs.SOUTHBOUND?.queue_length_meters || 0;
    const ebQ = apprs.EASTBOUND?.queue_length_meters || 0;
    const wbQ = apprs.WESTBOUND?.queue_length_meters || 0;

    setQueueHistory((prev) => {
      const next = [...prev, { nb: nbQ, sb: sbQ, eb: ebQ, wb: wbQ }];
      return next.slice(-20); // Keep last 20 frames
    });
  }, [data?.frame_sequence]);

  // Initialize Three.js Isometric Scene
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight || 480;

    // 1. Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0e17);
    sceneRef.current = scene;

    // 2. Isometric Orthographic Camera
    const aspect = width / height;
    const d = 55;
    const camera = new THREE.OrthographicCamera(
      -d * aspect,
      d * aspect,
      d,
      -d,
      1,
      1000
    );
    // Standard 45-degree isometric projection angle
    camera.position.set(70, 70, 70);
    camera.lookAt(0, 0, 0);

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0x38bdf8, 1.2);
    dirLight.position.set(40, 80, 50);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    scene.add(dirLight);

    const cyanPoint = new THREE.PointLight(0x06b6d4, 2, 80);
    cyanPoint.position.set(0, 8, 0);
    scene.add(cyanPoint);

    // 5. Ground Grid & Roads
    const gridHelper = new THREE.GridHelper(160, 32, 0x1e293b, 0x0f172a);
    gridHelper.position.y = -0.1;
    scene.add(gridHelper);

    // Asphalt Roads (North-South: Oak St, East-West: 5th Ave)
    const roadMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.8 });
    const roadW = 22;
    const roadL = 160;

    // Oak Street (Z-axis in Three.js)
    const oakGeom = new THREE.PlaneGeometry(roadW, roadL);
    const oakMesh = new THREE.Mesh(oakGeom, roadMat);
    oakMesh.rotation.x = -Math.PI / 2;
    oakMesh.receiveShadow = true;
    scene.add(oakMesh);

    // 5th Avenue (X-axis in Three.js)
    const fifthGeom = new THREE.PlaneGeometry(roadL, roadW);
    const fifthMesh = new THREE.Mesh(fifthGeom, roadMat);
    fifthMesh.rotation.x = -Math.PI / 2;
    fifthMesh.position.y = 0.01;
    fifthMesh.receiveShadow = true;
    scene.add(fifthMesh);

    // Sidewalks & City Blocks (Surrounding 4 Corners)
    const blockMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.6 });
    const bldgMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.4, metalness: 0.2 });
    const windowMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });

    const cornerOffsets = [
      { x: -45, z: -45 },
      { x: 45, z: -45 },
      { x: -45, z: 45 },
      { x: 45, z: 45 },
    ];

    cornerOffsets.forEach((pos, idx) => {
      // Sidewalk platform
      const sideGeom = new THREE.BoxGeometry(60, 0.4, 60);
      const sideMesh = new THREE.Mesh(sideGeom, blockMat);
      sideMesh.position.set(pos.x, 0.2, pos.z);
      scene.add(sideMesh);

      // Skyscraper buildings
      const bHeights = [24, 38, 30, 45];
      const h = bHeights[idx];
      const bldgGeom = new THREE.BoxGeometry(26, h, 26);
      const bldgMesh = new THREE.Mesh(bldgGeom, bldgMat);
      bldgMesh.position.set(pos.x, h / 2 + 0.4, pos.z);
      bldgMesh.castShadow = true;
      scene.add(bldgMesh);

      // Glowing roof accent
      const roofGeom = new THREE.BoxGeometry(20, 1, 20);
      const roofMesh = new THREE.Mesh(roofGeom, windowMat);
      roofMesh.position.set(pos.x, h + 0.9, pos.z);
      scene.add(roofMesh);
    });

    // Crosswalk Stripes (White lines near stop bars)
    const cwMat = new THREE.MeshBasicMaterial({ color: 0xe2e8f0 });
    const cwPositions = [
      { x: 0, z: -14, rot: 0 },
      { x: 0, z: 14, rot: 0 },
      { x: -14, z: 0, rot: Math.PI / 2 },
      { x: 14, z: 0, rot: Math.PI / 2 },
    ];
    cwPositions.forEach((cw) => {
      for (let i = -7; i <= 7; i += 2.2) {
        const stripe = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 3), cwMat);
        stripe.rotation.x = -Math.PI / 2;
        if (cw.rot === 0) {
          stripe.position.set(cw.x + i, 0.05, cw.z);
        } else {
          stripe.rotation.z = Math.PI / 2;
          stripe.position.set(cw.x, 0.05, cw.z + i);
        }
        scene.add(stripe);
      }
    });

    // Center RSU Antenna Tower
    const rsuBase = new THREE.Mesh(
      new THREE.CylinderGeometry(0.8, 1.2, 5, 8),
      new THREE.MeshStandardMaterial({ color: 0x06b6d4, metalness: 0.8 })
    );
    rsuBase.position.set(13, 2.5, 13);
    scene.add(rsuBase);

    const rsuDish = new THREE.Mesh(
      new THREE.SphereGeometry(1.2, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0x22d3ee, wireframe: true })
    );
    rsuDish.position.set(13, 5.5, 13);
    scene.add(rsuDish);

    // Dynamic Groups
    const vehiclesGroup = new THREE.Group();
    scene.add(vehiclesGroup);
    vehiclesGroupRef.current = vehiclesGroup;

    const arrowsGroup = new THREE.Group();
    scene.add(arrowsGroup);
    arrowsGroupRef.current = arrowsGroup;

    // Animation Loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      rsuDish.rotation.y += 0.015;
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!container || !rendererRef.current) return;
      const w = container.clientWidth;
      const h = container.clientHeight || 480;
      const a = w / h;
      camera.left = -d * a;
      camera.right = d * a;
      camera.top = d;
      camera.bottom = -d;
      camera.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", handleResize);
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Update 3D Vehicles & Glowing Lane Arrows on Telemetry Ticks
  useEffect(() => {
    if (!vehiclesGroupRef.current || !arrowsGroupRef.current || !data) return;

    // 1. Rebuild 3D Vehicles
    const vGroup = vehiclesGroupRef.current;
    while (vGroup.children.length > 0) {
      vGroup.remove(vGroup.children[0]);
    }

    const scale = 0.5; // Scale simulator meters to Three.js units
    data.simulation_2d_state.vehicles.forEach((v) => {
      const vGeom = new THREE.BoxGeometry(
        v.type === "truck" || v.type === "bus" ? 3.0 : 2.0,
        1.2,
        v.type === "truck" || v.type === "bus" ? 5.5 : 3.8
      );
      const vColor = new THREE.Color(v.color || 0x3b82f6);
      const vMat = new THREE.MeshStandardMaterial({ color: vColor, roughness: 0.3 });
      const mesh = new THREE.Mesh(vGeom, vMat);
      mesh.castShadow = true;

      // Position: simulator (x, y) maps to Three.js (x, z)
      mesh.position.set(v.x * scale, 0.7, -v.y * scale);

      // Orientation
      if (v.approach === "NORTH") mesh.rotation.y = Math.PI;
      else if (v.approach === "SOUTH") mesh.rotation.y = 0;
      else if (v.approach === "EAST") mesh.rotation.y = -Math.PI / 2;
      else if (v.approach === "WEST") mesh.rotation.y = Math.PI / 2;

      // OBU Connected Radio Halo
      if (v.has_obu) {
        const ringGeom = new THREE.RingGeometry(2.2, 2.5, 16);
        const ringMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide });
        const ring = new THREE.Mesh(ringGeom, ringMat);
        ring.rotation.x = Math.PI / 2;
        ring.position.y = 0.9;
        mesh.add(ring);
      }

      vGroup.add(mesh);
    });

    // 2. Rebuild Glowing Directional Lane Arrows
    const aGroup = arrowsGroupRef.current;
    while (aGroup.children.length > 0) {
      aGroup.remove(aGroup.children[0]);
    }

    const signals = data.adaptive_signal_control.signals;
    const nbSig = signals.find((s) => s.approach === "NORTHBOUND")?.state || "RED";
    const sbSig = signals.find((s) => s.approach === "SOUTHBOUND")?.state || "RED";
    const ebSig = signals.find((s) => s.approach === "EASTBOUND")?.state || "RED";
    const wbSig = signals.find((s) => s.approach === "WESTBOUND")?.state || "RED";

    const createArrow = (x: number, z: number, rotY: number, state: SignalColor) => {
      const color = state === "GREEN" ? 0x22c55e : state === "YELLOW" ? 0xeab308 : 0xef4444;
      const cone = new THREE.Mesh(
        new THREE.ConeGeometry(1.6, 3.2, 3),
        new THREE.MeshBasicMaterial({ color })
      );
      cone.rotation.x = -Math.PI / 2;
      cone.rotation.z = rotY;
      cone.position.set(x, 0.1, z);
      aGroup.add(cone);
    };

    createArrow(-2, 10, 0, nbSig);
    createArrow(2, -10, Math.PI, sbSig);
    createArrow(-10, -2, -Math.PI / 2, ebSig);
    createArrow(10, 2, Math.PI / 2, wbSig);
  }, [data]);

  const ctrl = data?.adaptive_signal_control;
  const ml = data?.ml_congestion_prediction;
  const v2i = data?.v2i_hardware_metrics;

  const congestionColorMap: Record<string, string> = {
    FREE: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
    LIGHT: "bg-blue-500/20 text-blue-400 border-blue-500/40",
    MODERATE: "bg-amber-500/20 text-amber-400 border-amber-500/40",
    HEAVY: "bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse",
  };

  const currentLevel = ml?.predicted_congestion_level || "LIGHT";

  return (
    <div className="relative w-full h-full min-h-[500px] flex flex-col bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
      {/* TOP HEADER BAR */}
      <div className="absolute top-0 left-0 right-0 z-20 px-5 py-3 bg-slate-900/90 backdrop-blur-md border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
          <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
            Oak Street &amp; 5th Avenue &bull; SC-INT-74
          </h2>
          <span className="text-xs text-slate-400 font-mono">Twin Sync: 1Hz</span>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          {/* Signal Phase Pill */}
          <div className="flex items-center space-x-1.5 px-3 py-1 rounded-full bg-slate-800 border border-slate-700">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span className="font-semibold text-slate-200">
              Phase {ctrl?.current_phase || 1} Active
            </span>
          </div>

          {/* ML Congestion Badge */}
          <div
            className={`px-3 py-1 rounded-full border text-xs font-mono font-bold ${
              congestionColorMap[currentLevel]
            }`}
          >
            ML: {currentLevel} ({Math.round((ml?.confidence_scores[currentLevel] || 0.85) * 100)}%)
          </div>
        </div>
      </div>

      {/* THREE.JS ISOMETRIC VIEWPORT */}
      <div ref={mountRef} className="w-full flex-1 relative overflow-hidden" />

      {/* FLOATING FLOW BADGES OVER ROAD CORRIDORS */}
      <div className="absolute top-20 left-1/2 -translate-x-1/2 z-10 pointer-events-none flex space-x-8">
        <div className="px-2 py-0.5 rounded bg-slate-900/90 border border-emerald-500/50 text-[11px] font-mono font-bold text-emerald-400 shadow-lg">
          Oak St NB: {data?.intersection_flow.approaches.NORTHBOUND?.flow_rate_veh_min || 52} veh/min
        </div>
        <div className="px-2 py-0.5 rounded bg-slate-900/90 border border-emerald-500/50 text-[11px] font-mono font-bold text-emerald-400 shadow-lg">
          5th Ave EB: {data?.intersection_flow.approaches.EASTBOUND?.flow_rate_veh_min || 68} veh/min
        </div>
      </div>

      {/* OVERLAY CARD A: V2I Communication Module Hardware (Top-Left) */}
      <div className="absolute top-16 left-4 z-20 w-72 p-3.5 rounded-lg bg-slate-900/90 backdrop-blur-md border border-slate-700/80 shadow-xl space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-[11px] font-bold uppercase tracking-wider text-cyan-400 flex items-center space-x-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
            <span>V2I Hardware Schematic</span>
          </div>
          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
            ACTIVE
          </span>
        </div>

        {/* Node-Link Schematic */}
        <div className="py-1 px-1 bg-slate-950/80 rounded border border-slate-800 text-[10px] font-mono text-slate-300 space-y-1">
          <div className="flex justify-between items-center text-center">
            <span className="px-1.5 py-0.5 rounded bg-blue-500/20 border border-blue-500/40 text-blue-300">
              OBU ({v2i?.active_obus_in_range || 22})
            </span>
            <span className="text-cyan-400 font-bold">&larr;BSM/MAP&rarr;</span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-300">
              RSU-SC74
            </span>
            <span className="text-cyan-400 font-bold">&larr;SPaT&rarr;</span>
            <span className="px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-500/40 text-purple-300">
              Controller
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-slate-400">
          <div>
            Latency:{" "}
            <span className="text-cyan-300 font-bold">
              {v2i?.v2i_latency_ms || 11.4} ms
            </span>
          </div>
          <div>
            Loss:{" "}
            <span className="text-emerald-300 font-bold">
              {v2i?.packets.BSM.packet_loss_rate_pct || 0.03}%
            </span>
          </div>
        </div>
      </div>

      {/* OVERLAY CARD B: Adaptive Traffic Signal Control Dashboard (Top-Right) */}
      <div className="absolute top-16 right-4 z-20 w-80 p-3.5 rounded-lg bg-slate-900/90 backdrop-blur-md border border-slate-700/80 shadow-xl space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="text-[11px] font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            <span>Adaptive Signal Control</span>
          </div>
          <span className="text-[10px] font-mono text-cyan-300">
            Cycle: <strong className="text-white">{ctrl?.cycle_time || 95}s</strong> (60-130s)
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="p-2 rounded bg-slate-950/70 border border-slate-800">
            <span className="text-slate-400 text-[10px]">Current Phase</span>
            <div className="font-bold text-emerald-400 text-sm">
              Phase {ctrl?.current_phase || 1}
            </div>
            <span className="text-[10px] text-slate-500">
              Split: {ctrl?.green_split_seconds.phase_1 || 28}s
            </span>
          </div>
          <div className="p-2 rounded bg-slate-950/70 border border-slate-800">
            <span className="text-slate-400 text-[10px]">Next Phase</span>
            <div className="font-bold text-cyan-400 text-sm">
              Phase {ctrl?.next_phase || 2}
            </div>
            <span className="text-[10px] text-slate-500">
              Split: {ctrl?.green_split_seconds.phase_2 || 14}s
            </span>
          </div>
        </div>

        {/* Multi-Line Queue Lengths Sparkline */}
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] font-mono text-slate-400">
            <span>Queue Lengths (m) History</span>
            <span className="text-rose-400">Max: {Math.round(data?.intersection_flow.congestion_metric_distance_meters || 35)}m</span>
          </div>
          <div className="h-12 w-full bg-slate-950/80 rounded border border-slate-800 p-1 flex items-end">
            <svg className="w-full h-full" viewBox="0 0 100 40" preserveAspectRatio="none">
              {/* NB queue polyline */}
              <polyline
                fill="none"
                stroke="#38bdf8"
                strokeWidth="1.8"
                points={
                  queueHistory.length > 1
                    ? queueHistory
                        .map((q, i) => `${(i / (queueHistory.length - 1)) * 100},${40 - (q.nb / 80) * 36}`)
                        .join(" ")
                    : "0,35 100,35"
                }
              />
              {/* EB queue polyline */}
              <polyline
                fill="none"
                stroke="#f59e0b"
                strokeWidth="1.8"
                points={
                  queueHistory.length > 1
                    ? queueHistory
                        .map((q, i) => `${(i / (queueHistory.length - 1)) * 100},${40 - (q.eb / 80) * 36}`)
                        .join(" ")
                    : "0,38 100,38"
                }
              />
            </svg>
          </div>
          <div className="flex justify-between text-[9px] font-mono text-slate-500">
            <span className="text-sky-400">&bull; Oak St NB</span>
            <span className="text-amber-400">&bull; 5th Ave EB</span>
            <span>Savings: {data?.intersection_flow.phase_optimization_savings.delay_saved_seconds_per_cycle || 6.2}s/cycle</span>
          </div>
        </div>
      </div>

      {/* BOTTOM FLOATING STATUS BAR */}
      <div className="absolute bottom-3 left-4 right-4 z-20 px-4 py-2 bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-lg flex items-center justify-between text-xs font-mono text-slate-300">
        <div className="flex items-center space-x-4">
          <div>
            Digital Twin ID: <span className="text-cyan-400 font-bold">SC-INT-74</span>
          </div>
          <div>
            V2I Latency:{" "}
            <span className="text-emerald-400 font-bold">
              {v2i?.v2i_latency_ms || 11.4} ms
            </span>
          </div>
          <div>
            Channel Occupancy:{" "}
            <span className="text-yellow-400 font-bold">
              {v2i?.channel_occupancy_pct || 24.5}%
            </span>
          </div>
        </div>

        <div className="text-slate-400 text-[11px]">
          Active Vehicles:{" "}
          <strong className="text-white">
            {data?.simulation_2d_state.active_vehicles_count || 28}
          </strong>{" "}
          &bull; Throughput Gain:{" "}
          <span className="text-emerald-400 font-bold">
            +{data?.intersection_flow.phase_optimization_savings.baseline_vs_adaptive_gain_pct || 18.5}%
          </span>
        </div>
      </div>
    </div>
  );
};

