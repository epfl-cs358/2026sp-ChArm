"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Chess } from "chess.js";
import {
  ArrowRight,
  Bot,
  Camera,
  CheckCircle2,
  Cpu,
  Crosshair,
  Eye,
  Gauge,
  Grid3X3,
  Loader2,
  Play,
  Settings,
  ShieldCheck,
  Square,
  Swords,
  Terminal,
  UserRound,
  XCircle,
  Zap,
} from "lucide-react";
import { api, CnnActiveModel, CnnModelMeta, ControllerPhase, CvRouterConfig } from "@/lib/api";
import { useCalibration } from "@/lib/calibration-context";
import { imageSrc } from "@/lib/image";
import {
  CalibrationData,
  DEFAULT_PARAMS,
  GameStepResult,
  RobotPoint3D,
  PipelineResult,
  RobotStatus,
} from "@/lib/types";
import ChessBoard from "@/components/ChessBoard";
import DebugImages from "@/components/DebugImages";
import ManualCalibration from "@/components/ManualCalibration";
import { BASE as ARM_BASE, type ArmAngles, type ArmDebugTarget, type ArmMove } from "@/components/RobotArmOverlay";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";

const DIFFICULTY_LABELS = ["Easy", "Medium", "Hard"] as const;

const SKILL_LEVEL_STORAGE_KEY = "charm-stockfish-skill-level";
const DEFAULT_SKILL_LEVEL = 12;
const MIN_SKILL_LEVEL = 1;
const MAX_SKILL_LEVEL = 20;

function controllerPhaseLabel(phase: ControllerPhase): string {
  switch (phase) {
    case "idle": return "idle";
    case "starting": return "starting…";
    case "waiting": return "waiting for start";
    case "arm_calibrating": return "calibrating arm";
    case "checking_board": return "checking board";
    case "player_turn": return "your turn";
    case "bot_thinking": return "thinking";
    case "bot_moving": return "moving";
    case "game_over": return "game over";
    case "error": return "error — see LCD";
    default: return phase;
  }
}

function estimateEloForSkill(skill: number): number {
  const anchors: Array<[number, number]> = [
    [0, 1100], [5, 1500], [10, 1800], [15, 2300], [20, 2850],
  ];
  const s = Math.max(0, Math.min(20, skill));
  for (let i = 0; i < anchors.length - 1; i++) {
    const [s0, e0] = anchors[i];
    const [s1, e1] = anchors[i + 1];
    if (s >= s0 && s <= s1) {
      const t = (s - s0) / (s1 - s0);
      return Math.round(e0 + t * (e1 - e0));
    }
  }
  return anchors[anchors.length - 1][1];
}

function skillTier(skill: number): string {
  if (skill <= 3) return "Beginner";
  if (skill <= 7) return "Casual";
  if (skill <= 12) return "Club";
  if (skill <= 16) return "Strong";
  return "Master";
}

const RobotArmOverlay = dynamic(() => import("@/components/RobotArmOverlay"), { ssr: false });

const DEBUG_PANELS_CNN = [
  { key: "refined_warp", label: "Refined Warp" },
  { key: "cnn_overlay", label: "CNN Detection" },
] as const;

const DEBUG_PANELS_VISION = [
  { key: "refined_warp", label: "Refined Warp" },
  { key: "occupancy_debug", label: "Occupancy" },
  { key: "piece_color_debug", label: "Piece Colors" },
] as const;

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];
const RANKS = ["8", "7", "6", "5", "4", "3", "2", "1"];
const COORDINATE_RANKS = [
  { label: "8", x: 0.75, y: 3.5, tone: "light" },
  { label: "7", x: 0.75, y: 15.75, tone: "dark" },
  { label: "6", x: 0.75, y: 28.25, tone: "light" },
  { label: "5", x: 0.75, y: 40.75, tone: "dark" },
  { label: "4", x: 0.75, y: 53.25, tone: "light" },
  { label: "3", x: 0.75, y: 65.75, tone: "dark" },
  { label: "2", x: 0.75, y: 78.25, tone: "light" },
  { label: "1", x: 0.75, y: 90.75, tone: "dark" },
] as const;
const COORDINATE_FILES = [
  { label: "a", x: 10, y: 99, tone: "dark" },
  { label: "b", x: 22.5, y: 99, tone: "light" },
  { label: "c", x: 35, y: 99, tone: "dark" },
  { label: "d", x: 47.5, y: 99, tone: "light" },
  { label: "e", x: 60, y: 99, tone: "dark" },
  { label: "f", x: 72.5, y: 99, tone: "light" },
  { label: "g", x: 85, y: 99, tone: "dark" },
  { label: "h", x: 97.5, y: 99, tone: "light" },
] as const;
const COORDINATE_COLORS = {
  light: "var(--charm-board-light)",
  dark: "var(--charm-board-dark)",
} as const;
const PIECE_IMAGE_PATHS: Record<string, string> = {
  wp: "/chesscom-pieces/wp.png", wn: "/chesscom-pieces/wn.png",
  wb: "/chesscom-pieces/wb.png", wr: "/chesscom-pieces/wr.png",
  wq: "/chesscom-pieces/wq.png", wk: "/chesscom-pieces/wk.png",
  bp: "/chesscom-pieces/bp.png", bn: "/chesscom-pieces/bn.png",
  bb: "/chesscom-pieces/bb.png", br: "/chesscom-pieces/br.png",
  bq: "/chesscom-pieces/bq.png", bk: "/chesscom-pieces/bk.png",
};
const DEFAULT_SERIAL_PORT = "/dev/ttyUSB0";
const DEFAULT_ESP32_HOST = "172.21.70.102";
const DEFAULT_ESP32_PORT = 8765;
const DEFAULT_ENGINE_PATH = "/usr/games/stockfish";
const ROBOT_PORT_STORAGE_KEY = "charm.robot.port";

type TurnState =
  | "arm_calibrate" | "arm_calibrating" | "human_turn" | "capturing"
  | "processing" | "human_move_found" | "robot_thinking" | "robot_moving" | "error";

const FLOW = [
  { key: "arm_calibrate", label: "Arm calibrate", icon: ShieldCheck },
  { key: "human_turn", label: "Your turn", icon: UserRound },
  { key: "capturing", label: "Capture", icon: Camera },
  { key: "processing", label: "Vision", icon: Eye },
  { key: "human_move_found", label: "Move found", icon: CheckCircle2 },
  { key: "robot_thinking", label: "Engine", icon: Cpu },
  { key: "robot_moving", label: "Robot turn", icon: Bot },
] as const;

function uciToArmMove(uci: string, san: string, id: number): ArmMove {
  return { id, from: uci.slice(0, 2), to: uci.slice(2, 4), label: `robot ${san}`, piece: "♟" };
}

function robotPositionToBoardTarget(
  position: Pick<RobotPoint3D, "x" | "y">,
  status: RobotStatus | null
): ArmDebugTarget | null {
  const robotCalibration = status?.robot_calibration;
  if (!robotCalibration?.exists) return null;
  const { a1, file_vector, rank_vector } = robotCalibration.calibration;
  const dx = position.x - a1.x;
  const dy = position.y - a1.y;
  const det = file_vector.x * rank_vector.y - file_vector.y * rank_vector.x;
  if (Math.abs(det) < 0.001) return null;
  return {
    x: (dx * rank_vector.y - dy * rank_vector.x) / det + 0.5,
    y: 7.5 - (file_vector.x * dy - file_vector.y * dx) / det,
  };
}

function ChessComCoordinates({ svgBoardUnits = false }: { svgBoardUnits?: boolean }) {
  const labels = [...COORDINATE_RANKS, ...COORDINATE_FILES];
  const content = labels.map((coord) => (
    <text key={coord.label} x={coord.x} y={coord.y} fontSize="2.8" fontWeight="700"
      fontFamily="Arial, Helvetica, sans-serif" fill={COORDINATE_COLORS[coord.tone]}>
      {coord.label}
    </text>
  ));
  if (svgBoardUnits) {
    return <g transform="scale(0.08)" pointerEvents="none" aria-hidden="true">{content}</g>;
  }
  return (
    <svg viewBox="0 0 100 100" className="pointer-events-none absolute inset-0" aria-hidden="true">
      {content}
    </svg>
  );
}

function BoardPiecesSvg({ game, visible, opacity }: { game: Chess; visible: boolean; opacity: number }) {
  const board = useMemo(() => game.board(), [game]);
  if (!visible) return null;
  return (
    <g opacity={opacity}>
      {board.map((row, rowIndex) =>
        row.map((piece, colIndex) => {
          if (!piece) return null;
          const pieceImage = PIECE_IMAGE_PATHS[`${piece.color}${piece.type}`];
          return (
            <image
              key={`${FILES[colIndex]}${RANKS[rowIndex]}-${piece.color}${piece.type}`}
              href={pieceImage} x={colIndex + 0.03} y={rowIndex - 0.02}
              width={0.94} height={0.94} preserveAspectRatio="xMidYMid meet"
            />
          );
        }),
      )}
    </g>
  );
}

function LogicalBoard({ game, lastMove }: { game: Chess; lastMove: string | null }) {
  const board = useMemo(() => game.board(), [game]);
  return (
    <div className="mx-auto w-full max-w-[300px]">
      <div className="relative grid aspect-square grid-cols-8 grid-rows-8 overflow-hidden rounded-md border border-border">
        {board.map((row, rowIndex) =>
          row.map((piece, colIndex) => {
            const square = `${FILES[colIndex]}${RANKS[rowIndex]}`;
            const light = (rowIndex + colIndex) % 2 === 0;
            const highlighted = lastMove?.slice(0, 2) === square || lastMove?.slice(2, 4) === square;
            const pieceImage = piece ? PIECE_IMAGE_PATHS[`${piece.color}${piece.type}`] : null;
            return (
              <div key={square} className="relative flex min-h-0 min-w-0 items-center justify-center"
                style={{
                  background: highlighted ? "oklch(0.78 0.14 210 / 0.55)"
                    : light ? "var(--charm-board-light)" : "var(--charm-board-dark)",
                }}>
                {pieceImage && (
                  <span aria-hidden="true" className="block h-[92%] w-[92%] bg-contain bg-center bg-no-repeat"
                    style={{ backgroundImage: `url(${pieceImage})` }} />
                )}
              </div>
            );
          }),
        )}
        <ChessComCoordinates />
      </div>
    </div>
  );
}

function FlowRail({ state, armCalibrated }: { state: TurnState; armCalibrated: boolean }) {
  const activeKey = state === "arm_calibrating" ? "arm_calibrate" : state;
  const activeIndex = Math.max(0, FLOW.findIndex((step) => step.key === activeKey));
  return (
    <div className="grid gap-2 md:grid-cols-7">
      {FLOW.map((step, index) => {
        const Icon = step.icon;
        const active = index === activeIndex;
        const done = state !== "error" && (index < activeIndex || (step.key === "arm_calibrate" && armCalibrated));
        return (
          <div key={step.key} className="rounded-md border px-3 py-2"
            style={{
              borderColor: active ? "oklch(from var(--charm-cyan) l c h / 0.45)" : "var(--charm-border)",
              background: active ? "oklch(from var(--charm-cyan) l c h / 0.1)" : "var(--charm-card)",
            }}>
            <div className="flex items-center gap-2">
              {done
                ? <CheckCircle2 className="size-4" style={{ color: "var(--charm-cyan)" }} />
                : <Icon className="size-4" style={{ color: active ? "var(--charm-cyan)" : "var(--charm-muted)" }} />}
              <span className="font-jetbrains text-xs" style={{ color: active ? "var(--charm-text)" : "var(--charm-muted)" }}>
                {step.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ImagePanel({ title, image, active }: { title: string; image?: string; active?: boolean }) {
  return (
    <div className="overflow-hidden rounded-md border"
      style={{
        borderColor: active ? "oklch(from var(--charm-cyan) l c h / 0.45)" : "var(--charm-border)",
        background: "var(--background)",
      }}>
      <div className="flex items-center justify-between border-b border-border px-2 py-1.5">
        <span className="font-jetbrains text-xs" style={{ color: active ? "var(--charm-cyan)" : "var(--charm-muted)" }}>{title}</span>
        {active && <span className="h-1.5 w-1.5 rounded-full status-loading" />}
      </div>
      {image
        ? <img src={imageSrc(image)} alt={title} className="h-32 w-full object-contain" />
        : <div className="flex h-32 items-center justify-center font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>waiting</div>}
    </div>
  );
}

function HeaderSystemStatus({ robotStatus, calibration, activeModel }: {
  robotStatus: RobotStatus | null;
  calibration: CalibrationData | null;
  activeModel: CnnActiveModel | null;
}) {
  const visionReady = Boolean(calibration?.board && calibration?.inner);
  const robotReady = Boolean(robotStatus?.robot_calibration.exists);
  const modelReady = Boolean(activeModel?.run_id);

  return (
    <div className="flex flex-wrap items-stretch gap-2">
      <Link href="/lab" className="min-w-[170px] rounded-md border px-3 py-2"
        style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="flex items-center gap-2">
          <Grid3X3 className="size-4" style={{ color: visionReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }} />
          <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>Vision calibration</p>
        </div>
        <p className="mt-1 truncate font-jetbrains text-xs" style={{ color: visionReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }}>
          {visionReady ? "ready" : "needs corners"}
        </p>
      </Link>

      <Link href="/robot" className="min-w-[170px] rounded-md border px-3 py-2"
        style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="flex items-center gap-2">
          <Settings className="size-4" style={{ color: robotReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }} />
          <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>Robot calibration</p>
        </div>
        <p className="mt-1 truncate font-jetbrains text-xs" style={{ color: robotReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }}>
          {robotReady ? "complete" : "a1 / h1 / h8"}
        </p>
      </Link>

      <Link href="/lab/cnn" className="min-w-[200px] rounded-md border px-3 py-2"
        style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="flex items-center gap-2">
          <Zap className="size-4" style={{ color: modelReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }} />
          <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>CNN model</p>
        </div>
        <p className="mt-1 truncate font-jetbrains text-xs" style={{ color: modelReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }}>
          {modelReady
            ? `${activeModel!.run_id}${activeModel!.val_acc != null ? ` · ${(activeModel!.val_acc * 100).toFixed(1)}%` : ""}`
            : "no model active"}
        </p>
      </Link>

      <div className="min-w-[190px] rounded-md border px-3 py-2" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="flex items-center gap-2">
          <Gauge className="size-4" style={{ color: robotStatus?.serial_connected ? "var(--charm-cyan)" : "var(--charm-muted)" }} />
          <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>Serial</p>
        </div>
        <p className="mt-1 max-w-[180px] truncate font-jetbrains text-xs"
          style={{ color: robotStatus?.serial_connected ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
          {robotStatus?.serial_connected ? robotStatus.active_port : robotStatus?.detected_port ?? "idle"}
        </p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [game, setGame] = useState(() => new Chess());
  const [turnState, setTurnState] = useState<TurnState>("arm_calibrate");
  const [armCalibrated, setArmCalibrated] = useState(false);
  const [gameSessionStarted, setGameSessionStarted] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [stepResult, setStepResult] = useState<GameStepResult | null>(null);
  const [robotMove, setRobotMove] = useState<ArmMove | null>(null);
  const [armView, setArmView] = useState<"Board" | "Arm">("Board");
  const [armDebug, setArmDebug] = useState(false);
  const [armDebugTarget, setArmDebugTarget] = useState<ArmDebugTarget>({ x: 4, y: 6 });
  const [armIdleTarget, setArmIdleTarget] = useState<ArmDebugTarget | null>(null);
  const [armOpacity, setArmOpacity] = useState(0.78);
  const [expectedOpacity, setExpectedOpacity] = useState(0.26);
  const [scaraPiecesVisible, setScaraPiecesVisible] = useState(true);
  const [scaraPiecesOpacity, setScaraPiecesOpacity] = useState(0.9);
  const [armAngles, setArmAngles] = useState<ArmAngles>({ a1: 0, a2: 0 });
  const [lastMove, setLastMove] = useState<string | null>(null);
  const [moveLog, setMoveLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [testBusy, setTestBusy] = useState<"capture" | null>(null);
  const [lastCapturePath, setLastCapturePath] = useState<string | null>(null);
  const [showManualCalibrationModal, setShowManualCalibrationModal] = useState(false);
  const [overlayOpen, setOverlayOpen] = useState(false);
  const [robotStatus, setRobotStatus] = useState<RobotStatus | null>(null);
  // Render with deterministic defaults on the server; hydrate from
  // localStorage in an effect after mount so SSR and the first client
  // render agree (avoids React hydration mismatches).
  const [robotPort, setRobotPort] = useState<string>(DEFAULT_SERIAL_PORT);
  const { calibration, refresh: refreshCalibration, setCalibration } = useCalibration();
  const [difficulty, setDifficulty] = useState<0 | 1 | 2>(1);
  const [skillLevel, setSkillLevel] = useState<number>(DEFAULT_SKILL_LEVEL);
  const [showSkillModal, setShowSkillModal] = useState(false);
  const [draftSkillLevel, setDraftSkillLevel] = useState<number>(DEFAULT_SKILL_LEVEL);

  useEffect(() => {
    const storedPort = window.localStorage.getItem(ROBOT_PORT_STORAGE_KEY);
    if (storedPort) setRobotPort(storedPort);

    const storedSkill = window.localStorage.getItem(SKILL_LEVEL_STORAGE_KEY);
    const parsed = storedSkill ? parseInt(storedSkill, 10) : NaN;
    if (Number.isFinite(parsed)) {
      const clamped = Math.max(MIN_SKILL_LEVEL, Math.min(MAX_SKILL_LEVEL, parsed));
      setSkillLevel(clamped);
      setDraftSkillLevel(clamped);
    }
  }, []);
  const [skillApplyToast, setSkillApplyToast] = useState<{ level: number; at: number } | null>(null);

  // ── play_game.py controller (LCD) ──────────────────────────────────────
  const [controllerRunning, setControllerRunning] = useState(false);
  const [controllerLog, setControllerLog] = useState<string[]>([]);
  const [controllerBusy, setControllerBusy] = useState(false);
  const [showControllerLog, setShowControllerLog] = useState(false);
  const [controllerPhase, setControllerPhase] = useState<ControllerPhase>("idle");
  const [controllerMoves, setControllerMoves] = useState<string[]>([]);
  const [controllerPlayerColor, setControllerPlayerColor] = useState<"white" | "black" | null>(null);

  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const s = await api.controllerStatus();
        if (stopped) return;
        const running = !!s.running;
        setControllerRunning(running);
        if (s.log_tail) setControllerLog(s.log_tail);

        if (!running) {
          setControllerPhase("idle");
          setControllerMoves([]);
          setControllerPlayerColor(null);
          return;
        }

        const gs = await api.controllerGameState();
        if (stopped) return;
        setControllerPhase(gs.phase);
        setControllerMoves(gs.moves ?? []);
        setControllerPlayerColor(gs.player_color);
        if (gs.fen) {
          try {
            setGame(new Chess(gs.fen));
          } catch {
            // Ignore — the controller may briefly publish a transient or
            // pre-start FEN; the next poll will correct it.
          }
        }
      } catch {
        // network blip — ignore
      }
    };
    poll();
    const id = window.setInterval(poll, 2000);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, []);

  // CNN model state
  const [cnnModels, setCnnModels] = useState<CnnModelMeta[]>([]);
  const [activeCnnModel, setActiveCnnModel] = useState<CnnActiveModel | null>(null);
  const [showCnnModelModal, setShowCnnModelModal] = useState(false);
  const [cnnModelBusy, setCnnModelBusy] = useState(false);

  // CV router state (primary/fallback + validated-capture toggle)
  const [cvConfig, setCvConfig] = useState<CvRouterConfig | null>(null);
  const [cvConfigBusy, setCvConfigBusy] = useState(false);

  const refreshCvConfig = useCallback(async () => {
    try {
      const cfg = await api.getCvConfig();
      setCvConfig(cfg);
    } catch {
      // non-fatal
    }
  }, []);

  const patchCvConfig = useCallback(async (patch: Partial<CvRouterConfig>) => {
    setCvConfigBusy(true);
    try {
      const updated = await api.setCvConfig(patch);
      setCvConfig(updated);
    } catch {
      // ignore — UI keeps last known value
    } finally {
      setCvConfigBusy(false);
    }
  }, []);

  const armMoveId = useRef(0);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SKILL_LEVEL_STORAGE_KEY, String(skillLevel));
    }
  }, [skillLevel]);

  useEffect(() => {
    if (!skillApplyToast) return;
    const t = setTimeout(() => setSkillApplyToast(null), 3500);
    return () => clearTimeout(t);
  }, [skillApplyToast]);

  const refreshCnnState = useCallback(async () => {
    try {
      const [modelsResp, active] = await Promise.all([api.cnnListModels(), api.cnnActiveModel()]);
      setCnnModels(modelsResp.models);
      setActiveCnnModel(active);
    } catch {
      // non-fatal
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Calibration is already fetched by CalibrationProvider at the layout
    // level; here we only need robot status.
    api.getRobotStatus()
      .then((robot) => {
        if (cancelled) return;
        setRobotStatus(robot);
        setRobotPort((current) => {
          const stored = typeof window !== "undefined" ? window.localStorage.getItem(ROBOT_PORT_STORAGE_KEY) : null;
          const detected = robot.active_port || robot.detected_port || null;
          const knownPorts = new Set(robot.ports.map((p) => p.device));
          const preferred = stored || current;
          if (!preferred || preferred === DEFAULT_SERIAL_PORT) return detected || preferred || current;
          return knownPorts.has(preferred) ? preferred : (detected || preferred || current);
        });
        setArmIdleTarget(robotPositionToBoardTarget(robot.robot_calibration.calibration.home, robot));
      })
      .catch(() => undefined);
    refreshCnnState();
    refreshCvConfig();
    return () => { cancelled = true; };
  }, [refreshCnnState, refreshCvConfig]);

  const resolveSerialPort = useCallback((currentPort?: string | null) => {
    const current = currentPort || robotPort;
    const detected = robotStatus?.active_port || robotStatus?.detected_port || null;
    if (!current) return detected || undefined;
    if (current === DEFAULT_SERIAL_PORT) return detected || undefined;
    if (robotStatus?.ports.some((p) => p.device === current)) return current;
    return detected || current;
  }, [robotPort, robotStatus]);

  const toggleController = useCallback(async () => {
    if (controllerBusy) return;
    setControllerBusy(true);
    try {
      if (controllerRunning) {
        const s = await api.controllerStop();
        setControllerRunning(!!s.running);
      } else {
        const s = await api.controllerStart({
          esp32_host: DEFAULT_ESP32_HOST,
          esp32_port: DEFAULT_ESP32_PORT,
          arm_port: resolveSerialPort(robotPort) || DEFAULT_SERIAL_PORT,
          player_color: "white",
          difficulty,
          engine_path: DEFAULT_ENGINE_PATH,
        });
        setControllerRunning(!!s.running);
        setShowControllerLog(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Controller toggle failed");
    } finally {
      setControllerBusy(false);
    }
  }, [controllerBusy, controllerRunning, difficulty, resolveSerialPort, robotPort]);

  const activateCnnModel = useCallback(async (run_id: string) => {
    setCnnModelBusy(true);
    try {
      await api.cnnActivateModel(run_id);
      await refreshCnnState();
      setShowCnnModelModal(false);
    } catch {
      // show stays open
    } finally {
      setCnnModelBusy(false);
    }
  }, [refreshCnnState]);

  const busy = turnState === "arm_calibrating" || turnState === "capturing" || turnState === "processing" || turnState === "robot_thinking" || turnState === "robot_moving";

  const runStartupCalibrate = useCallback(async () => {
    if (turnState === "arm_calibrating") return;
    setMoveLog((current) => [...current, "Calibrate: click"]);
    setError(null);
    setTurnState("arm_calibrating");
    try {
      const response = await api.sendRobotCommand({
        command: "arm-calibrate",
        port: resolveSerialPort(robotPort),
        baud: 115200,
      });
      setMoveLog((current) => [
        ...current,
        response.responses.length > 0 ? `Calibrate: ${response.responses.at(-1)}` : "Calibrate: command sent",
      ]);
      setArmIdleTarget(robotPositionToBoardTarget(
        response.position ?? robotStatus?.robot_calibration.calibration.home ?? { x: 0, y: 0 },
        robotStatus
      ));
      setArmCalibrated(true);
      setGameSessionStarted(false);
      setTurnState("human_turn");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Arm calibration failed");
      setTurnState("error");
    }
  }, [robotPort, robotStatus, turnState]);

  const runRecalibrate = useCallback(async () => {
    if (turnState === "arm_calibrating" || busy) return;
    const resumeState = turnState;
    setError(null);
    setTurnState("arm_calibrating");
    try {
      const response = await api.sendRobotCommand({
        command: "arm-calibrate",
        port: resolveSerialPort(robotPort),
        baud: 115200,
      });
      setMoveLog((current) => [
        ...current,
        response.responses.length > 0 ? `Recalibrate: ${response.responses.at(-1)}` : "Recalibrate: command sent",
      ]);
      setArmIdleTarget(robotPositionToBoardTarget(
        response.position ?? robotStatus?.robot_calibration.calibration.home ?? { x: 0, y: 0 },
        robotStatus
      ));
      setArmCalibrated(true);
      setTurnState(resumeState === "arm_calibrate" ? "human_turn" : resumeState);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Arm recalibration failed");
      setTurnState("error");
    }
  }, [robotPort, robotStatus, turnState, busy]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const finishRobotMove = useCallback((_finishedMove: ArmMove) => {}, []);

  const processHumanTurn = useCallback(async () => {
    if (!armCalibrated) {
      setError("Run startup arm calibration before the first turn.");
      setTurnState("arm_calibrate");
      return;
    }
    if (busy) return;
    setError(null);
    setOverlayOpen(true);
    setTurnState("capturing");

    try {
      if (!gameSessionStarted) {
        const session = await api.startGameSession({
          player_color: "white",
          difficulty,
          skill_level: skillLevel,
          params: DEFAULT_PARAMS,
          capture: true,
          max_mismatches: 0,
          port: resolveSerialPort(robotPort),
          baud: 115200,
        });
        if (session.pipeline) {
          setResult(session.pipeline);
          setLastCapturePath(session.pipeline.image_path ?? null);
          if (session.status !== "ok" && session.pipeline.board_validation_debug) {
            const debug = session.pipeline.board_validation_debug;
            console.log("%c=== BOARD VALIDATION FAILED ===", "color: red; font-size: 14px; font-weight: bold");
            console.log("%cExpected FEN:", "color: blue; font-weight: bold", debug.expected_fen);
            console.log("%cMismatches:", "color: red", debug.mismatch_count);
            console.log("%cWhite:", "color: blue", debug.observed_white_bitmap);
            console.log("%cBlack:", "color: red", debug.observed_black_bitmap);
          }
        }
        if (session.status !== "ok") {
          setError(session.started?.message ?? "Initial board validation failed");
          setTurnState("error");
          return;
        }
        if (session.fen) setGame(new Chess(session.fen));
        setGameSessionStarted(true);
        setMoveLog((current) => [
          ...current,
          session.started?.message ?? "Game session started",
          ...(session.robot_move?.move_uci ? [`Robot: ${session.robot_move.san ?? session.robot_move.move_uci}`] : []),
        ]);
        if (session.robot_move?.move_uci) {
          armMoveId.current += 1;
          setRobotMove(uciToArmMove(session.robot_move.move_uci, session.robot_move.san ?? session.robot_move.move_uci, armMoveId.current));
        }
        setTurnState("human_turn");
        return;
      }

      const response = await api.processGameSessionTurn({
        params: DEFAULT_PARAMS,
        capture: true,
        max_mismatches: 0,
        difficulty,
        skill_level: skillLevel,
        port: resolveSerialPort(robotPort),
        baud: 115200,
      });
      if (response.pipeline) {
        setLastCapturePath(response.pipeline.image_path ?? null);
        setResult(response.pipeline);
      }
      setStepResult(null);
      setTurnState("processing");

      if (response.status !== "ok" && response.status !== "game_over") {
        const humanMove = response.human_move;
        const errorPrefix: Record<string, string> = {
          unchanged: "[BOARD UNCHANGED]", illegal_move: "[ILLEGAL MOVE]",
          in_check: "[IN CHECK]", ambiguous: "[AMBIGUOUS]",
        };
        const prefix = humanMove?.error_code ? errorPrefix[humanMove.error_code] ?? "" : "";
        const baseMsg = humanMove?.message ?? response.robot_move?.message ?? `Game session failed: ${response.status}`;
        setError(prefix ? `${prefix} ${baseMsg}` : baseMsg);
        setTurnState("error");
        return;
      }

      if (response.fen) setGame(new Chess(response.fen));
      if (response.human_move?.move_uci) {
        setMoveLog((current) => [...current, `You: ${response.human_move?.san ?? response.human_move?.move_uci}`]);
        setLastMove(response.human_move.move_uci);
      }
      setTurnState("human_move_found");

      if (response.status === "game_over") {
        setTurnState("human_turn");
        return;
      }

      setTurnState("robot_thinking");
      if (response.robot_move?.move_uci) {
        armMoveId.current += 1;
        setRobotMove(uciToArmMove(response.robot_move.move_uci, response.robot_move.san ?? response.robot_move.move_uci, armMoveId.current));
        setTurnState("robot_moving");
        setMoveLog((current) => [...current, `Robot: ${response.robot_move?.san ?? response.robot_move?.move_uci}`]);
        setLastMove(response.robot_move.move_uci);
      }
      setRobotMove(null);
      setTurnState("human_turn");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to process turn");
      setTurnState("error");
    }
  }, [armCalibrated, difficulty, gameSessionStarted, robotPort, robotStatus, turnState, busy, skillLevel]);

  const testCapture = useCallback(async () => {
    if (busy || testBusy) return;
    setError(null);
    setTestBusy("capture");
    setTurnState("capturing");
    try {
      const response = await api.captureFromCamera();
      setLastCapturePath(response.path);
      setMoveLog((current) => [...current, `Capture: ${response.path}`]);
      setTurnState(armCalibrated ? "human_turn" : "arm_calibrate");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Capture failed");
      setTurnState("error");
    } finally {
      setTestBusy(null);
    }
  }, [armCalibrated, busy, testBusy]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Space") return;
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable) return;
      event.preventDefault();
      void processHumanTurn();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [processHumanTurn]);

  const statusLabel = turnState === "arm_calibrate" ? "Arm calibration required"
    : turnState === "arm_calibrating" ? "Calibrating arm"
    : turnState === "human_turn" ? "Your turn"
    : turnState === "capturing" ? "Taking photo"
    : turnState === "processing" ? "Running vision"
    : turnState === "human_move_found" ? "Human move recognized"
    : turnState === "robot_thinking" ? "Robot is thinking"
    : turnState === "robot_moving" ? "Robot is moving"
    : "Needs attention";

  return (
    <div className="p-5 max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 rounded-md border p-4"
        style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="min-w-[260px] flex-1">
          <h1 className="text-2xl font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>ChArm Game Dashboard</h1>
          <p className="text-sm mt-1" style={{ color: "var(--charm-muted)" }}>CNN vision · SCARA arm · Stockfish engine</p>
          <div className="mt-4">
            <HeaderSystemStatus robotStatus={robotStatus} calibration={calibration} activeModel={activeCnnModel} />
          </div>
        </div>
        <div className="flex min-w-[260px] items-center justify-end gap-2 flex-wrap">
          <button
            type="button"
            onClick={toggleController}
            disabled={controllerBusy}
            title={controllerRunning
              ? "Stop play_game.py (LCD controller flow)"
              : "Launch play_game.py — drives the LCD/rotary controller flow"}
            className="flex items-center gap-2 rounded-md border px-3 py-1.5 font-jetbrains text-xs transition-colors disabled:opacity-50"
            style={controllerRunning ? {
              borderColor: "oklch(0.65 0.22 25 / 0.6)",
              background: "oklch(0.65 0.22 25 / 0.12)",
              color: "oklch(0.65 0.22 25)",
            } : {
              borderColor: "oklch(from var(--charm-cyan) l c h / 0.5)",
              background: "oklch(from var(--charm-cyan) l c h / 0.08)",
              color: "var(--charm-cyan)",
            }}>
            {controllerBusy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : controllerRunning ? (
              <Square className="size-4" />
            ) : (
              <Play className="size-4" />
            )}
            <span className="font-semibold">
              {controllerRunning ? "Stop LCD" : "Run LCD"}
            </span>
          </button>
          {controllerRunning ? (
            <Badge
              variant="outline"
              title={
                controllerPlayerColor
                  ? `LCD game in progress · player=${controllerPlayerColor} · ${controllerMoves.length} moves played`
                  : "LCD controller active — webapp controls are read-only"
              }
              style={{ borderColor: "oklch(from var(--charm-cyan) l c h / 0.5)", color: "var(--charm-cyan)" }}>
              LCD: {controllerPhaseLabel(controllerPhase)}
            </Badge>
          ) : null}
          {controllerLog.length > 0 ? (
            <button
              type="button"
              onClick={() => setShowControllerLog((v) => !v)}
              title="Toggle play_game.py log tail"
              className="flex items-center gap-1.5 rounded-md border px-2 py-1.5 font-jetbrains text-xs"
              style={{ borderColor: "var(--charm-border)", color: "var(--charm-muted)" }}>
              <Terminal className="size-3.5" />
              <span>{showControllerLog ? "Hide log" : "Show log"}</span>
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => { setDraftSkillLevel(skillLevel); setShowSkillModal(true); }}
            title={`Stockfish skill ${skillLevel}/20 (~${estimateEloForSkill(skillLevel)} Elo). Click to change.`}
            className="flex items-center gap-2 rounded-md border px-3 py-1.5 font-jetbrains text-xs transition-colors hover:bg-[oklch(from_var(--charm-cyan)_l_c_h_/_0.14)]"
            style={{ borderColor: "oklch(from var(--charm-cyan) l c h / 0.5)", background: "oklch(from var(--charm-cyan) l c h / 0.08)", color: "var(--charm-cyan)" }}>
            <Swords className="size-4" />
            <span style={{ color: "var(--charm-muted)" }}>Stockfish</span>
            <span className="font-semibold" style={{ color: "var(--charm-cyan)" }}>Lv {skillLevel}/20</span>
            <span style={{ color: "var(--charm-muted)" }}>·</span>
            <span style={{ color: "var(--charm-muted)" }}>~{estimateEloForSkill(skillLevel)} Elo</span>
          </button>
          <Badge variant="outline" style={{ borderColor: "var(--charm-border)", color: turnState === "error" ? "oklch(0.65 0.22 25)" : "var(--charm-cyan)" }}>
            {statusLabel}
          </Badge>
          <Button
            onClick={runStartupCalibrate}
            disabled={turnState === "arm_calibrating" || armCalibrated || controllerRunning}
            title={controllerRunning ? "LCD controller is running — stop it first" : undefined}
            className="font-jetbrains"
            style={{ background: armCalibrated ? "transparent" : "oklch(from var(--charm-cyan) l c h / 0.12)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.4)", color: "var(--charm-cyan)" }}>
            {turnState === "arm_calibrating" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
            {armCalibrated ? "Arm calibrated" : "Arm calibration required"}
          </Button>
          <Button
            variant="outline"
            onClick={runRecalibrate}
            disabled={turnState === "arm_calibrating" || busy || controllerRunning}
            className="font-jetbrains"
            title={controllerRunning
              ? "LCD controller is running — stop it first"
              : "Re-home the arm without resetting the current game state."}
          >
            <ShieldCheck className="size-4" />
            Recalibrate arm
          </Button>
          <Button
            variant="outline"
            onClick={() => setShowManualCalibrationModal(true)}
            className="font-jetbrains"
            title="Manually calibrate the board warp / inner grid used by the CNN scan."
          >
            <Crosshair className="size-4" />
            Manual calibration
          </Button>
          <Button
            onClick={processHumanTurn}
            disabled={busy || !armCalibrated || controllerRunning}
            title={controllerRunning ? "LCD controller is running — stop it first" : undefined}
            className="font-jetbrains"
            style={{ background: "oklch(from var(--charm-cyan) l c h / 0.12)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.4)", color: "var(--charm-cyan)" }}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            {gameSessionStarted ? "Player done" : "Start game"}
          </Button>
        </div>
      </div>

      <FlowRail state={turnState} armCalibrated={armCalibrated} />

      {showControllerLog && (
        <div className="rounded-md border p-3 font-jetbrains text-xs"
          style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <div className="flex items-center justify-between mb-2">
            <span style={{ color: "var(--charm-muted)" }}>
              play_game.py · {controllerRunning ? "running" : "stopped"}
            </span>
            <button
              type="button"
              onClick={() => setShowControllerLog(false)}
              className="text-xs"
              style={{ color: "var(--charm-muted)" }}>
              close
            </button>
          </div>
          <pre className="max-h-48 overflow-auto text-[11px] leading-relaxed whitespace-pre-wrap"
            style={{ color: "var(--charm-text)" }}>
            {controllerLog.length === 0 ? "(no output yet)" : controllerLog.join("\n")}
          </pre>
        </div>
      )}

      {error && (
        <div className="rounded-md border px-4 py-3 text-sm font-jetbrains flex items-center gap-2"
          style={{ background: "oklch(0.65 0.22 25 / 0.1)", borderColor: "oklch(0.65 0.22 25 / 0.3)", color: "oklch(0.65 0.22 25)" }}>
          <XCircle className="size-4" />{error}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(330px,0.65fr)]">
        {/* SCARA Arm card — unchanged */}
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardHeader className="px-4 pt-4 pb-2 flex-row items-center justify-between">
            <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>SCARA Arm</h2>
            <div className="flex gap-1">
              {(["Board", "Arm"] as const).map((v) => (
                <button key={v} onClick={() => setArmView(v)}
                  className="font-jetbrains text-xs px-2 py-1 rounded border"
                  style={{ borderColor: "var(--charm-border)", color: armView === v ? "var(--charm-cyan)" : "var(--charm-muted)", background: armView === v ? "oklch(from var(--charm-cyan) l c h / 0.08)" : "transparent" }}>
                  {v}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-4">
            <svg
              viewBox={armView === "Board" ? `${-10/37.5} ${-10/37.5} ${8 + 2*(10/37.5)} ${8 + 2*(10/37.5)}` : "-1 -4 13 13"}
              className="w-full rounded-md border border-border"
              style={{ background: "var(--background)", display: "block", aspectRatio: "1/1" }}
              aria-hidden="true">
              {Array.from({ length: 11 }, (_, i) => (
                <line key={`gv${i}`} x1={i - 1} y1="-3" x2={i - 1} y2="10" stroke="oklch(0.5 0 0 / 0.18)" strokeWidth="0.025" />
              ))}
              {Array.from({ length: 14 }, (_, i) => (
                <line key={`gh${i}`} x1="-2" y1={i - 3} x2="14" y2={i - 3} stroke="oklch(0.5 0 0 / 0.18)" strokeWidth="0.025" />
              ))}
              <rect x={-10/37.5} y={-10/37.5} width={8 + 2*(10/37.5)} height={8 + 2*(10/37.5)} fill="black" rx="0.05" />
              {Array.from({ length: 64 }, (_, i) => {
                const row = Math.floor(i / 8); const col = i % 8; const light = (row + col) % 2 === 0;
                return <rect key={i} x={col} y={row} width={1} height={1} fill={light ? "var(--charm-board-light)" : "var(--charm-board-dark)"} opacity="0.92" />;
              })}
              <BoardPiecesSvg game={game} visible={scaraPiecesVisible} opacity={scaraPiecesOpacity} />
              <ChessComCoordinates svgBoardUnits />
              <circle cx={ARM_BASE.x} cy={ARM_BASE.y} r="0.18" fill="oklch(0.65 0.22 25)" opacity="0.85" />
              <RobotArmOverlay
                embed move={robotMove}
                mode={turnState === "arm_calibrating" ? "calibrating" : robotMove ? "playing" : "idle"}
                onDone={finishRobotMove} debugTarget={armDebug ? armDebugTarget : null}
                idleTarget={armCalibrated ? armIdleTarget : null}
                opacity={armOpacity} expectedOpacity={expectedOpacity} onAnglesChange={setArmAngles}
              />
            </svg>
            <details className="rounded-md border border-border p-3">
              <summary className="cursor-pointer font-jetbrains text-xs font-semibold" style={{ color: "var(--charm-text)" }}>Arm debug</summary>
              <div className="mt-3 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <label className="flex items-center gap-2 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                    <input type="checkbox" checked={armDebug} onChange={(e) => setArmDebug(e.target.checked)} />
                    target mode
                  </label>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {(["x", "y"] as const).map((axis) => (
                    <label key={axis} className="space-y-1">
                      <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>{axis} target</span>
                      <input type="range" min={-0.5} max={8.5} step="0.1" value={armDebugTarget[axis]}
                        onChange={(e) => setArmDebugTarget((c) => ({ ...c, [axis]: Number(e.target.value) }))} className="w-full" />
                      <span className="font-jetbrains text-xs" style={{ color: "var(--charm-cyan)" }}>{armDebugTarget[axis].toFixed(1)}</span>
                    </label>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <label className="space-y-1">
                    <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>arm opacity</span>
                    <input type="range" min="0.15" max="1" step="0.05" value={armOpacity} onChange={(e) => setArmOpacity(Number(e.target.value))} className="w-full" />
                  </label>
                  <label className="space-y-1">
                    <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>expected opacity</span>
                    <input type="range" min="0" max="0.7" step="0.05" value={expectedOpacity} onChange={(e) => setExpectedOpacity(Number(e.target.value))} className="w-full" />
                  </label>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <label className="flex items-center gap-2 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                    <input type="checkbox" checked={scaraPiecesVisible} onChange={(e) => setScaraPiecesVisible(e.target.checked)} />
                    pieces visible
                  </label>
                  <label className="space-y-1">
                    <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>pieces opacity</span>
                    <input type="range" min="0.05" max="1" step="0.05" value={scaraPiecesOpacity} onChange={(e) => setScaraPiecesOpacity(Number(e.target.value))} className="w-full" />
                  </label>
                </div>
              </div>
            </details>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-md border border-border p-3">
                <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>a1</p>
                <p className="mt-1 font-jetbrains text-sm" style={{ color: "var(--charm-text)" }}>{armAngles.a1.toFixed(1)} deg</p>
              </div>
              <div className="rounded-md border border-border p-3">
                <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>a2</p>
                <p className="mt-1 font-jetbrains text-sm" style={{ color: "var(--charm-text)" }}>{armAngles.a2.toFixed(1)} deg</p>
              </div>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>Robot command preview</p>
              <p className="mt-1 font-jetbrains text-sm" style={{ color: "var(--charm-text)" }}>{robotMove ? `${robotMove.from} -> ${robotMove.to}` : "waiting for accepted human move"}</p>
            </div>
            <div className="max-h-28 overflow-auto rounded-md border border-border p-3 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
              {moveLog.length ? moveLog.slice(-8).map((line, index) => <p key={`${line}-${index}`}>{line}</p>) : <p>No moves yet.</p>}
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-5">
          {/* CV Mode card */}
          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2 flex-row items-center justify-between">
              <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>CV Mode</h2>
              <Link href="/lab/vision-settings" className="font-jetbrains text-xs underline" style={{ color: "var(--charm-muted)" }}>
                advanced
              </Link>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-3">
              <p className="font-jetbrains text-[11px]" style={{ color: "var(--charm-muted)" }}>
                Primary CV runs first; the other is the fallback. Each gets {cvConfig?.attempts_each ?? 5} fresh-frame attempts.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {(["vision", "cnn"] as const).map((mode) => {
                  const active = cvConfig?.primary === mode;
                  const cnnUnavailable = mode === "cnn" && cvConfig?.cnn_active === false;
                  return (
                    <button
                      key={mode}
                      disabled={cvConfigBusy || cnnUnavailable}
                      onClick={() => { void patchCvConfig({ primary: mode }); }}
                      className="rounded border px-3 py-2 font-jetbrains text-xs transition-colors"
                      style={{
                        borderColor: active ? "oklch(from var(--charm-cyan) l c h / 0.6)" : "var(--charm-border)",
                        color: active ? "var(--charm-cyan)" : cnnUnavailable ? "var(--charm-muted)" : "var(--charm-text)",
                        background: active ? "oklch(from var(--charm-cyan) l c h / 0.08)" : "transparent",
                        opacity: cnnUnavailable ? 0.5 : 1,
                        cursor: cnnUnavailable ? "not-allowed" : "pointer",
                      }}
                    >
                      <div className="font-semibold uppercase tracking-wider">{mode === "vision" ? "Vision" : "CNN"}</div>
                      <div className="mt-0.5 text-[10px]" style={{ color: "var(--charm-muted)" }}>
                        {mode === "vision" ? "classical pipeline" : cnnUnavailable ? "no model active" : "neural net"}
                      </div>
                    </button>
                  );
                })}
              </div>
              <label className="flex items-center gap-2 font-jetbrains text-xs" style={{ color: "var(--charm-text)" }}>
                <input
                  type="checkbox"
                  checked={cvConfig?.auto_save_validated ?? true}
                  disabled={cvConfigBusy}
                  onChange={(e) => { void patchCvConfig({ auto_save_validated: e.target.checked }); }}
                />
                Save validated frames to <code style={{ color: "var(--charm-cyan)" }}>{cvConfig?.dataset_name ?? "validated_live"}</code>
              </label>
              {result?.cv_router && (
                <div className="rounded-md border border-border px-3 py-2 font-jetbrains text-[11px]">
                  <p style={{ color: "var(--charm-muted)" }}>Last scan</p>
                  <p className="mt-1" style={{ color: "var(--charm-text)" }}>
                    Validated by <span style={{ color: "var(--charm-cyan)" }}>{result.cv_router.mode_used ?? "—"}</span>
                    {" · "}
                    {result.cv_router.by_mode.vision}× vision, {result.cv_router.by_mode.cnn}× CNN
                  </p>
                  {result.validated_capture?.saved && (
                    <p className="mt-0.5" style={{ color: "var(--charm-muted)" }}>
                      Saved 64 cells → {result.validated_capture.dataset}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* CNN Vision card */}
          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2 flex-row items-center justify-between">
              <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>CNN Vision</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { void refreshCnnState(); setShowCnnModelModal(true); }}
                  className="flex items-center gap-1.5 rounded border px-2 py-1 font-jetbrains text-xs transition-colors"
                  style={{
                    borderColor: activeCnnModel?.run_id ? "oklch(from var(--charm-cyan) l c h / 0.5)" : "var(--charm-border)",
                    color: activeCnnModel?.run_id ? "var(--charm-cyan)" : "var(--charm-muted)",
                    background: activeCnnModel?.run_id ? "oklch(from var(--charm-cyan) l c h / 0.08)" : "transparent",
                  }}>
                  <Zap className="size-3" />
                  {activeCnnModel?.run_id
                    ? `${activeCnnModel.run_id}${activeCnnModel.val_acc != null ? ` · ${(activeCnnModel.val_acc * 100).toFixed(1)}%` : ""}`
                    : "no model — select"}
                </button>
                <Badge variant="outline" className="font-jetbrains" style={{ borderColor: "var(--charm-border)", color: "var(--charm-cyan)" }}>camera on</Badge>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-4">
              <div className="grid grid-cols-2 gap-2">
                <Button variant="outline" size="sm" className="font-jetbrains" onClick={testCapture} disabled={busy || Boolean(testBusy)}>
                  {testBusy === "capture" ? <Loader2 className="size-4 animate-spin" /> : <Camera className="size-4" />}
                  Capture
                </Button>
                <Button variant="outline" size="sm" className="font-jetbrains" onClick={processHumanTurn} disabled={busy || !armCalibrated || Boolean(testBusy)}>
                  <Bot className="size-4" />
                  Game
                </Button>
              </div>
              <div className="rounded-md border border-border px-3 py-2">
                <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>Latest capture</p>
                <p className="mt-1 truncate font-jetbrains text-xs" style={{ color: "var(--charm-text)" }}>{lastCapturePath ?? result?.image_path ?? "waiting"}</p>
              </div>
              <DebugImages
                panels={(result?.cv_mode === "vision" ? DEBUG_PANELS_VISION : DEBUG_PANELS_CNN).map(({ key, label }) => ({
                  key,
                  label,
                  b64: result?.[key as keyof PipelineResult] as string | undefined,
                }))}
                gridClassName="grid grid-cols-2 gap-3"
                imageMaxHeight={210}
              />
              {(() => {
                // Vision pipeline produces color_labels directly. CNN doesn't,
                // so derive a label grid from the bitmaps so the visual board
                // shows in both modes.
                let labels = result?.color_labels;
                if (!labels && result?.white_bitmap && result?.black_bitmap) {
                  labels = result.white_bitmap.map((row, r) =>
                    row.map((wb, c) => {
                      if (wb) return "white" as const;
                      if (result.black_bitmap[r][c]) return "black" as const;
                      return "empty" as const;
                    }),
                  );
                }
                if (!labels) return null;
                return (
                  <div className="overflow-auto">
                    <ChessBoard
                      colorLabels={labels}
                      occupancyScores={result?.occupancy_scores}
                      brightnessScores={result?.brightness_scores}
                      highlightUnknown
                    />
                  </div>
                );
              })()}
            </CardContent>
          </Card>

          {/* Game State card */}
          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2">
              <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>Game State</h2>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-3">
              <LogicalBoard game={game} lastMove={lastMove} />
              <div className="grid grid-cols-1 gap-2">
                <div className="rounded-md border border-border p-2">
                  <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>Last inferred move</p>
                  <p className="mt-1 font-jetbrains text-sm" style={{ color: "var(--charm-cyan)" }}>{stepResult?.inference.move_uci ?? "none"}</p>
                </div>
                <div className="rounded-md border border-border p-2">
                  <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>Mismatch count</p>
                  <p className="mt-1 font-jetbrains text-sm" style={{ color: "var(--charm-text)" }}>{stepResult?.inference.mismatch_count ?? 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* CNN model picker modal */}
      {showCnnModelModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto py-12 backdrop-blur-sm"
          style={{ background: "oklch(0 0 0 / 0.7)" }}
          onClick={() => setShowCnnModelModal(false)}>
          <div className="mx-4 w-full max-w-md rounded-md border shadow-2xl"
            style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--charm-border)" }}>
              <div className="flex items-center gap-2">
                <Zap className="size-4" style={{ color: "var(--charm-cyan)" }} />
                <span className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>Select CNN Model</span>
              </div>
              <button onClick={() => setShowCnnModelModal(false)} className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>✕ close</button>
            </div>
            <div className="space-y-2 p-4">
              {cnnModels.length === 0 && (
                <div className="rounded-md border border-border px-3 py-4 text-center font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                  No trained models found. Train one at <Link href="/lab/cnn" className="underline" style={{ color: "var(--charm-cyan)" }}>/lab/cnn</Link>.
                </div>
              )}
              {cnnModels.map((m) => {
                const isActive = activeCnnModel?.run_id === m.run_id;
                return (
                  <div key={m.run_id} className="flex items-center justify-between rounded-md border px-3 py-2"
                    style={{
                      background: isActive ? "oklch(from var(--charm-cyan) l c h / 0.1)" : "transparent",
                      borderColor: isActive ? "var(--charm-cyan)" : "var(--charm-border)",
                    }}>
                    <div className="font-jetbrains text-xs">
                      <div style={{ color: isActive ? "var(--charm-cyan)" : "var(--charm-text)" }}>{m.run_id}</div>
                      <div style={{ color: "var(--charm-muted)" }}>
                        {m.dataset ?? "?"} · val {m.val_acc != null ? `${(m.val_acc * 100).toFixed(1)}%` : "?"}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant={isActive ? "outline" : "default"}
                      disabled={cnnModelBusy}
                      onClick={() => void activateCnnModel(m.run_id)}>
                      {cnnModelBusy && isActive ? <Loader2 className="size-3 animate-spin" /> : isActive ? "active" : "activate"}
                    </Button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Stockfish skill modal */}
      {showSkillModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto py-12 backdrop-blur-sm"
          style={{ background: "oklch(0 0 0 / 0.7)" }}
          onClick={() => setShowSkillModal(false)}>
          <div className="mx-4 w-full max-w-md rounded-md border shadow-2xl"
            style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--charm-border)" }}>
              <div className="flex items-center gap-2">
                <Swords className="size-4" style={{ color: "var(--charm-cyan)" }} />
                <span className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>Stockfish Difficulty</span>
              </div>
              <button onClick={() => setShowSkillModal(false)} className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>✕ close</button>
            </div>
            <div className="space-y-5 p-5">
              <div className="flex items-baseline justify-between">
                <div>
                  <div className="font-jetbrains text-xs uppercase tracking-wider" style={{ color: "var(--charm-muted)" }}>Skill Level</div>
                  <div className="font-jetbrains text-3xl font-semibold" style={{ color: "var(--charm-cyan)" }}>
                    {draftSkillLevel}<span className="ml-1 text-base" style={{ color: "var(--charm-muted)" }}>/ 20</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-jetbrains text-xs uppercase tracking-wider" style={{ color: "var(--charm-muted)" }}>Estimated Elo</div>
                  <div className="font-jetbrains text-2xl font-semibold" style={{ color: "var(--charm-text)" }}>~{estimateEloForSkill(draftSkillLevel)}</div>
                  <div className="font-jetbrains text-xs mt-0.5" style={{ color: "var(--charm-muted)" }}>{skillTier(draftSkillLevel)}</div>
                </div>
              </div>
              <Slider value={[draftSkillLevel]} min={MIN_SKILL_LEVEL} max={MAX_SKILL_LEVEL} step={1}
                onValueChange={(v) => {
                  const next = Array.isArray(v) ? v[0] : v;
                  if (Number.isFinite(next)) setDraftSkillLevel(Math.max(MIN_SKILL_LEVEL, Math.min(MAX_SKILL_LEVEL, next as number)));
                }} className="w-full" />
              <div className="flex justify-between font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                <span>1 · Beginner</span><span>10 · Club</span><span>20 · Master</span>
              </div>
              <div className="rounded-md border px-3 py-2 font-jetbrains text-xs"
                style={{ borderColor: "var(--charm-border)", background: "oklch(from var(--charm-cyan) l c h / 0.04)", color: "var(--charm-muted)" }}>
                Stockfish reconfigures on every robot move, so changes apply to the <span style={{ color: "var(--charm-cyan)" }}>next</span> move — including mid-game.
              </div>
              {draftSkillLevel !== skillLevel && (
                <div className="rounded-md border px-3 py-2 font-jetbrains text-xs flex items-center justify-between"
                  style={{ borderColor: "oklch(from var(--charm-cyan) l c h / 0.4)", background: "oklch(from var(--charm-cyan) l c h / 0.07)", color: "var(--charm-text)" }}>
                  <span>Current: <span style={{ color: "var(--charm-muted)" }}>Lv {skillLevel} (~{estimateEloForSkill(skillLevel)} Elo)</span></span>
                  <span>Pending: <span style={{ color: "var(--charm-cyan)" }}>Lv {draftSkillLevel} (~{estimateEloForSkill(draftSkillLevel)} Elo)</span></span>
                </div>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" onClick={() => setShowSkillModal(false)}
                  className="rounded-md border px-3 py-1.5 font-jetbrains text-xs"
                  style={{ borderColor: "var(--charm-border)", color: "var(--charm-muted)", background: "transparent" }}>
                  Cancel
                </button>
                <button type="button"
                  onClick={() => { setSkillLevel(draftSkillLevel); setSkillApplyToast({ level: draftSkillLevel, at: Date.now() }); setShowSkillModal(false); }}
                  disabled={draftSkillLevel === skillLevel}
                  className="rounded-md border px-3 py-1.5 font-jetbrains text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ borderColor: "oklch(from var(--charm-cyan) l c h / 0.5)", background: "oklch(from var(--charm-cyan) l c h / 0.15)", color: "var(--charm-cyan)" }}>
                  Apply
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {skillApplyToast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] rounded-md border px-4 py-2 font-jetbrains text-xs shadow-lg flex items-center gap-2"
          style={{ borderColor: "oklch(from var(--charm-cyan) l c h / 0.5)", background: "var(--charm-card)", color: "var(--charm-text)" }}>
          <CheckCircle2 className="size-4" style={{ color: "var(--charm-cyan)" }} />
          Stockfish skill level set to <span style={{ color: "var(--charm-cyan)" }}>{skillApplyToast.level}/20</span>
          <span style={{ color: "var(--charm-muted)" }}>(~{estimateEloForSkill(skillApplyToast.level)} Elo)</span>
          <span style={{ color: "var(--charm-muted)" }}>— applies on next robot move.</span>
        </div>
      )}

      {showManualCalibrationModal && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 backdrop-blur-sm"
          style={{ background: "oklch(0 0 0 / 0.7)" }}
          onClick={() => setShowManualCalibrationModal(false)}
        >
          <div
            className="w-full max-w-7xl max-h-[95vh] overflow-y-auto rounded-md border shadow-2xl bg-black"
            style={{ borderColor: "var(--charm-border)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b px-4 py-2" style={{ borderColor: "var(--charm-border)" }}>
              <span className="font-jetbrains text-sm font-semibold text-white">Manual Calibration</span>
              <button
                onClick={() => setShowManualCalibrationModal(false)}
                className="font-jetbrains text-xs"
                style={{ color: "var(--charm-muted)" }}
              >
                ✕ close
              </button>
            </div>
            <div className="bg-background">
              <ManualCalibration imagePath={lastCapturePath} />
            </div>
          </div>
        </div>
      )}

      {/* CNN scan overlay (bottom right) */}
      {overlayOpen && result && (
        <div className="fixed bottom-4 right-4 z-50 w-90 max-w-[calc(100vw-2rem)] rounded-md border p-3 shadow-2xl"
          style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <div className="mb-2 flex justify-end">
            <button onClick={() => setOverlayOpen(false)} className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>close</button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <ImagePanel title="warp" image={result.refined_warp} />
            <ImagePanel title="CNN" image={result.cnn_overlay} active={turnState === "processing"} />
          </div>
          <p className="mt-2 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
            {result.image_path ?? "latest frame"} · {stepResult?.inference.move_uci ? `move ${stepResult.inference.move_uci}` : "move pending"}
          </p>
        </div>
      )}
    </div>
  );
}
