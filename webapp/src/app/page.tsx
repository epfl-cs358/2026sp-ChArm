"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Chess, Square } from "chess.js";
import {
  Activity,
  ArrowRight,
  Bot,
  Camera,
  CheckCircle2,
  Cpu,
  Eye,
  Gauge,
  Grid3X3,
  Loader2,
  Settings,
  ShieldCheck,
  UserRound,
  XCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { imageSrc } from "@/lib/image";
import {
  CalibrationData,
  DEFAULT_PARAMS,
  GameStepResult,
  PipelineResult,
  RobotStatus,
} from "@/lib/types";
import ChessBoard from "@/components/ChessBoard";
import { BASE as ARM_BASE, type ArmAngles, type ArmDebugTarget, type ArmMove } from "@/components/RobotArmOverlay";
import VisionImage from "@/components/VisionImage";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const RobotArmOverlay = dynamic(() => import("@/components/RobotArmOverlay"), { ssr: false });

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
const PIECE_NAMES: Record<string, string> = {
  p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king",
};
const PIECE_IMAGE_PATHS: Record<string, string> = {
  wp: "/chesscom-pieces/wp.png",
  wn: "/chesscom-pieces/wn.png",
  wb: "/chesscom-pieces/wb.png",
  wr: "/chesscom-pieces/wr.png",
  wq: "/chesscom-pieces/wq.png",
  wk: "/chesscom-pieces/wk.png",
  bp: "/chesscom-pieces/bp.png",
  bn: "/chesscom-pieces/bn.png",
  bb: "/chesscom-pieces/bb.png",
  br: "/chesscom-pieces/br.png",
  bq: "/chesscom-pieces/bq.png",
  bk: "/chesscom-pieces/bk.png",
};

type TurnState =
  | "arm_calibrate"
  | "arm_calibrating"
  | "human_turn"
  | "capturing"
  | "processing"
  | "human_move_found"
  | "robot_thinking"
  | "robot_moving"
  | "error";

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
  return {
    id,
    from: uci.slice(0, 2),
    to: uci.slice(2, 4),
    label: `robot ${san}`,
    piece: "♟",
  };
}

function moveFromUci(game: Chess, uci: string) {
  return game.move({
    from: uci.slice(0, 2) as Square,
    to: uci.slice(2, 4) as Square,
    promotion: (uci[4] as "q" | "r" | "b" | "n" | undefined) ?? "q",
  });
}

function fallbackMove(game: Chess) {
  const moves = game.moves({ verbose: true });
  const captures = moves.filter((move) => move.captured);
  const checks = moves.filter((move) => move.san.includes("+"));
  return (checks[0] ?? captures[0] ?? moves[0])?.lan ?? null;
}

function ChessComCoordinates({ svgBoardUnits = false }: { svgBoardUnits?: boolean }) {
  const labels = [...COORDINATE_RANKS, ...COORDINATE_FILES];
  const content = labels.map((coord) => (
    <text
      key={coord.label}
      x={coord.x}
      y={coord.y}
      fontSize="2.8"
      fontWeight="700"
      fontFamily="Arial, Helvetica, sans-serif"
      fill={COORDINATE_COLORS[coord.tone]}
    >
      {coord.label}
    </text>
  ));

  if (svgBoardUnits) {
    return (
      <g transform="scale(0.08)" pointerEvents="none" aria-hidden="true">
        {content}
      </g>
    );
  }

  return (
    <svg viewBox="0 0 100 100" className="pointer-events-none absolute inset-0" aria-hidden="true">
      {content}
    </svg>
  );
}

function BoardPiecesSvg({
  game,
  visible,
  opacity,
}: {
  game: Chess;
  visible: boolean;
  opacity: number;
}) {
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
              href={pieceImage}
              x={colIndex + 0.03}
              y={rowIndex - 0.02}
              width={0.94}
              height={0.94}
              preserveAspectRatio="xMidYMid meet"
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
              <div
                key={square}
                className="relative flex min-h-0 min-w-0 items-center justify-center"
                style={{
                  background: highlighted
                    ? "oklch(0.78 0.14 210 / 0.55)"
                    : light
                    ? "var(--charm-board-light)"
                    : "var(--charm-board-dark)",
                }}
              >
                {pieceImage && (
                  <span
                    aria-hidden="true"
                    className="block h-[92%] w-[92%] bg-contain bg-center bg-no-repeat"
                    style={{
                      backgroundImage: `url(${pieceImage})`,
                    }}
                  />
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
          <div
            key={step.key}
            className="rounded-md border px-3 py-2"
            style={{
              borderColor: active ? "oklch(from var(--charm-cyan) l c h / 0.45)" : "var(--charm-border)",
              background: active ? "oklch(from var(--charm-cyan) l c h / 0.1)" : "var(--charm-card)",
            }}
          >
            <div className="flex items-center gap-2">
              {done ? <CheckCircle2 className="size-4" style={{ color: "var(--charm-cyan)" }} /> : <Icon className="size-4" style={{ color: active ? "var(--charm-cyan)" : "var(--charm-muted)" }} />}
              <span className="font-jetbrains text-xs" style={{ color: active ? "var(--charm-text)" : "var(--charm-muted)" }}>{step.label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ImagePanel({ title, image, active }: { title: string; image?: string; active?: boolean }) {
  return (
    <div
      className="overflow-hidden rounded-md border"
      style={{
        borderColor: active ? "oklch(from var(--charm-cyan) l c h / 0.45)" : "var(--charm-border)",
        background: "var(--background)",
      }}
    >
      <div className="flex items-center justify-between border-b border-border px-2 py-1.5">
        <span className="font-jetbrains text-xs" style={{ color: active ? "var(--charm-cyan)" : "var(--charm-muted)" }}>{title}</span>
        {active && <span className="h-1.5 w-1.5 rounded-full status-loading" />}
      </div>
      {image ? (
        <img src={imageSrc(image)} alt={title} className="h-32 w-full object-contain" />
      ) : (
        <div className="flex h-32 items-center justify-center font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>waiting</div>
      )}
    </div>
  );
}

function HeaderSystemStatus({ robotStatus, calibration }: { robotStatus: RobotStatus | null; calibration: CalibrationData | null }) {
  const visionReady = Boolean(calibration?.board && calibration?.inner);
  const robotReady = Boolean(robotStatus?.robot_calibration.exists);

  return (
    <div className="flex flex-wrap items-stretch gap-2">
      <Link href="/lab" className="min-w-[170px] rounded-md border px-3 py-2" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="flex items-center gap-2">
          <Grid3X3 className="size-4" style={{ color: visionReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }} />
          <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>Vision calibration</p>
        </div>
        <p className="mt-1 truncate font-jetbrains text-xs" style={{ color: visionReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }}>
          {visionReady ? "ready" : "needs corners"}
        </p>
      </Link>

      <Link href="/robot" className="min-w-[170px] rounded-md border px-3 py-2" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="flex items-center gap-2">
          <Settings className="size-4" style={{ color: robotReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }} />
          <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>Robot calibration</p>
        </div>
        <p className="mt-1 truncate font-jetbrains text-xs" style={{ color: robotReady ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }}>
          {robotReady ? "complete" : "a1 / h1 / h8"}
        </p>
      </Link>

      <div className="min-w-[190px] rounded-md border px-3 py-2" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="flex items-center gap-2">
          <Gauge className="size-4" style={{ color: robotStatus?.serial_connected ? "var(--charm-cyan)" : "var(--charm-muted)" }} />
          <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>Serial</p>
        </div>
        <p className="mt-1 max-w-[180px] truncate font-jetbrains text-xs" style={{ color: robotStatus?.serial_connected ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
          {robotStatus?.serial_connected ? robotStatus.active_port : robotStatus?.detected_port ?? "idle"}
        </p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [game, setGame] = useState(() => new Chess());
  const [moves, setMoves] = useState<string[]>([]);
  const [turnState, setTurnState] = useState<TurnState>("arm_calibrate");
  const [armCalibrated, setArmCalibrated] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [stepResult, setStepResult] = useState<GameStepResult | null>(null);
  const [robotMove, setRobotMove] = useState<ArmMove | null>(null);
  const [armView, setArmView] = useState<"Board" | "Arm">("Board");
  const [armDebug, setArmDebug] = useState(false);
  const [armDebugTarget, setArmDebugTarget] = useState<ArmDebugTarget>({ x: 4, y: 6 });
  const [armOpacity, setArmOpacity] = useState(0.78);
  const [expectedOpacity, setExpectedOpacity] = useState(0.26);
  const [scaraPiecesVisible, setScaraPiecesVisible] = useState(true);
  const [scaraPiecesOpacity, setScaraPiecesOpacity] = useState(0.9);
  const [armAngles, setArmAngles] = useState<ArmAngles>({ a1: 0, a2: 0 });
  const [lastMove, setLastMove] = useState<string | null>(null);
  const [moveLog, setMoveLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [testBusy, setTestBusy] = useState<"capture" | "pipeline" | null>(null);
  const [lastCapturePath, setLastCapturePath] = useState<string | null>(null);
  const [overlayOpen, setOverlayOpen] = useState(false);
  const [robotStatus, setRobotStatus] = useState<RobotStatus | null>(null);
  const [calibration, setCalibration] = useState<CalibrationData | null>(null);
  const armMoveId = useRef(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getRobotStatus(), api.getCalibration()])
      .then(([robot, vision]) => {
        if (cancelled) return;
        setRobotStatus(robot);
        setCalibration(vision);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const requestBestMove = useCallback(async (fen: string) => {
    const response = await fetch("/api/stockfish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fen, depth: 8 }),
    });
    if (!response.ok) throw new Error("Stockfish request failed");
    const data = (await response.json()) as { bestMove?: string };
    return data.bestMove ?? null;
  }, []);

  const runStartupCalibrate = useCallback(async () => {
    if (turnState === "arm_calibrating") return;
    setError(null);
    setTurnState("arm_calibrating");
    try {
      const response = await api.sendRobotCommand({ command: "arm-calibrate" });
      setMoveLog((current) => [
        ...current,
        response.responses.length > 0 ? `Calibrate: ${response.responses.at(-1)}` : "Calibrate: command sent",
      ]);
      setArmCalibrated(true);
      setTurnState("human_turn");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Arm calibration failed");
      setTurnState("error");
    }
  }, [turnState]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const finishRobotMove = useCallback((_finishedMove: ArmMove) => {
    // Animation ended — game state update happens when the Arduino command returns.
  }, []);

  const busy = turnState === "arm_calibrating" || turnState === "capturing" || turnState === "processing" || turnState === "robot_thinking" || turnState === "robot_moving";

  const processHumanTurn = useCallback(async () => {
    if (!armCalibrated) {
      setError("Run startup arm calibration before the first turn.");
      setTurnState("arm_calibrate");
      return;
    }
    if (turnState === "arm_calibrating" || turnState === "capturing" || turnState === "processing" || turnState === "robot_thinking" || turnState === "robot_moving") return;
    setError(null);
    setOverlayOpen(true);
    setTurnState("capturing");

    try {
      const response = await api.processGameStep({
        moves,
        params: DEFAULT_PARAMS,
        capture: true,
        max_mismatches: 0,
      });
      setLastCapturePath(response.pipeline.image_path ?? null);
      setStepResult(response);
      setResult(response.pipeline);
      setTurnState("processing");

      if (!response.inference.accepted || !response.inference.move_uci) {
        setError(`Vision could not accept a move: ${response.inference.status}, mismatches=${response.inference.mismatch_count}`);
        setTurnState("error");
        return;
      }

      const afterHuman = new Chess(game.fen());
      const humanMove = moveFromUci(afterHuman, response.inference.move_uci);
      if (!humanMove) {
        setError(`Move detected but illegal in UI state: ${response.inference.move_uci}`);
        setTurnState("error");
        return;
      }

      const humanUci = `${humanMove.from}${humanMove.to}${humanMove.promotion ?? ""}`;
      setGame(afterHuman);
      setMoves((current) => [...current, humanUci]);
      setMoveLog((current) => [...current, `You: ${humanMove.san}`]);
      setLastMove(humanUci);
      setTurnState("human_move_found");

      if (afterHuman.isGameOver()) {
        setTurnState("human_turn");
        return;
      }

      setTurnState("robot_thinking");
      const best = (await requestBestMove(afterHuman.fen())) ?? fallbackMove(afterHuman);
      if (!best) {
        setError("Stockfish did not return a robot move.");
        setTurnState("error");
        return;
      }

      const robotPreview = new Chess(afterHuman.fen());
      const robotChessMove = moveFromUci(robotPreview, best);
      if (!robotChessMove) {
        setError(`Robot move is illegal: ${best}`);
        setTurnState("error");
        return;
      }

      const robotUci = `${robotChessMove.from}${robotChessMove.to}${robotChessMove.promotion ?? ""}`;
      const isCapture = !!robotChessMove.captured;
      const isCastling = robotChessMove.piece === "k" &&
        Math.abs(robotChessMove.from.charCodeAt(0) - robotChessMove.to.charCodeAt(0)) === 2;
      const isPromotion = !!robotChessMove.promotion;
      const pieceType = PIECE_NAMES[robotChessMove.piece] ?? "pawn";

      armMoveId.current += 1;
      setRobotMove(uciToArmMove(best, robotChessMove.san, armMoveId.current));
      setTurnState("robot_moving");

      await api.sendRobotCommand({
        command: "move",
        uci: best,
        capture: isCapture,
        castling: isCastling,
        promotion: isPromotion,
        piece_type: pieceType,
      });

      setGame(robotPreview);
      setMoves((current) => [...current, robotUci]);
      setMoveLog((current) => [...current, `Robot: ${robotChessMove.san}`]);
      setLastMove(robotUci);
      setRobotMove(null);
      setTurnState("human_turn");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to process turn");
      setTurnState("error");
    }
  }, [armCalibrated, game, moves, requestBestMove, turnState]);

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

  const testVisionPipeline = useCallback(async () => {
    if (busy || testBusy) return;
    setError(null);
    setOverlayOpen(true);
    setTestBusy("pipeline");
    setTurnState("capturing");
    try {
      const capture = await api.captureFromCamera();
      setLastCapturePath(capture.path);
      setTurnState("processing");
      const pipeline = await api.runPipeline({ ...DEFAULT_PARAMS, image_path: capture.path });
      setResult(pipeline);
      setMoveLog((current) => [...current, `Pipeline: ${pipeline.stats.occupied} pieces, ${pipeline.total_ms.toFixed(0)} ms`]);
      setTurnState(armCalibrated ? "human_turn" : "arm_calibrate");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline test failed");
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

  const statusLabel = turnState === "arm_calibrate"
    ? "Arm calibration required"
    : turnState === "arm_calibrating"
    ? "Calibrating arm"
    : turnState === "human_turn"
    ? "Your turn"
    : turnState === "capturing"
    ? "Taking photo"
    : turnState === "processing"
    ? "Running vision"
    : turnState === "human_move_found"
    ? "Human move recognized"
    : turnState === "robot_thinking"
    ? "Robot is thinking"
    : turnState === "robot_moving"
    ? "Robot is moving"
    : "Needs attention";

  return (
    <div className="p-5 max-w-7xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4 rounded-md border p-4" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <div className="min-w-[260px] flex-1">
          <h1 className="text-2xl font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>ChArm Game Dashboard</h1>
          <p className="text-sm mt-1" style={{ color: "var(--charm-muted)" }}>Camera is always active. Player move, capture, vision, then robot move.</p>
          <div className="mt-4">
            <HeaderSystemStatus robotStatus={robotStatus} calibration={calibration} />
          </div>
        </div>
        <div className="flex min-w-[260px] items-center justify-end gap-2 flex-wrap">
          <Badge variant="outline" style={{ borderColor: "var(--charm-border)", color: turnState === "error" ? "oklch(0.65 0.22 25)" : "var(--charm-cyan)" }}>
            {statusLabel}
          </Badge>
          <Button
            onClick={runStartupCalibrate}
            disabled={turnState === "arm_calibrating" || armCalibrated}
            className="font-jetbrains"
            style={{ background: armCalibrated ? "transparent" : "oklch(from var(--charm-cyan) l c h / 0.12)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.4)", color: "var(--charm-cyan)" }}
          >
            {turnState === "arm_calibrating" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
            {armCalibrated ? "Arm calibrated" : "Arm calibration required"}
          </Button>
          <Button
            onClick={processHumanTurn}
            disabled={busy || !armCalibrated}
            className="font-jetbrains"
            style={{ background: "oklch(from var(--charm-cyan) l c h / 0.12)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.4)", color: "var(--charm-cyan)" }}
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            Player done
          </Button>
        </div>
      </div>

      <FlowRail state={turnState} armCalibrated={armCalibrated} />

      {error && (
        <div className="rounded-md border px-4 py-3 text-sm font-jetbrains flex items-center gap-2" style={{ background: "oklch(0.65 0.22 25 / 0.1)", borderColor: "oklch(0.65 0.22 25 / 0.3)", color: "oklch(0.65 0.22 25)" }}>
          <XCircle className="size-4" />{error}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(330px,0.65fr)]">
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardHeader className="px-4 pt-4 pb-2 flex-row items-center justify-between">
            <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>SCARA Arm</h2>
            <div className="flex gap-1">
              {(["Board", "Arm"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setArmView(v)}
                  className="font-jetbrains text-xs px-2 py-1 rounded border"
                  style={{ borderColor: "var(--charm-border)", color: armView === v ? "var(--charm-cyan)" : "var(--charm-muted)", background: armView === v ? "oklch(from var(--charm-cyan) l c h / 0.08)" : "transparent" }}
                >
                  {v}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-4">
            <svg
              viewBox={armView === "Board"
                ? `${-10/37.5} ${-10/37.5} ${8 + 2*(10/37.5)} ${8 + 2*(10/37.5)}`
                : "-1 -4 13 13"}
              className="w-full rounded-md border border-border"
              style={{ background: "var(--background)", display: "block", aspectRatio: "1/1" }}
              aria-hidden="true"
            >
              {/* Grid lines */}
              {Array.from({ length: 11 }, (_, i) => (
                <line key={`gv${i}`} x1={i - 1} y1="-3" x2={i - 1} y2="10" stroke="oklch(0.5 0 0 / 0.18)" strokeWidth="0.025" />
              ))}
              {Array.from({ length: 14 }, (_, i) => (
                <line key={`gh${i}`} x1="-2" y1={i - 3} x2="14" y2={i - 3} stroke="oklch(0.5 0 0 / 0.18)" strokeWidth="0.025" />
              ))}
              {/* Board border (10mm margin, square=37.5mm → ratio 10/37.5) */}
              <rect
                x={-10/37.5} y={-10/37.5}
                width={8 + 2*(10/37.5)} height={8 + 2*(10/37.5)}
                fill="black" rx="0.05"
              />
              {/* Board squares */}
              {Array.from({ length: 64 }, (_, i) => {
                const row = Math.floor(i / 8);
                const col = i % 8;
                const light = (row + col) % 2 === 0;
                return (
                  <rect key={i} x={col} y={row} width={1} height={1}
                    fill={light ? "var(--charm-board-light)" : "var(--charm-board-dark)"}
                    opacity="0.92"
                  />
                );
              })}
              <BoardPiecesSvg game={game} visible={scaraPiecesVisible} opacity={scaraPiecesOpacity} />
              <ChessComCoordinates svgBoardUnits />
              {/* Arm base marker */}
              <circle cx={ARM_BASE.x} cy={ARM_BASE.y} r="0.18" fill="oklch(0.65 0.22 25)" opacity="0.85" />
              {/* Arm */}
              <RobotArmOverlay
                embed
                move={robotMove}
                mode={turnState === "arm_calibrating" ? "calibrating" : robotMove ? "playing" : "idle"}
                onDone={finishRobotMove}
                debugTarget={armDebug ? armDebugTarget : null}
                opacity={armOpacity}
                expectedOpacity={expectedOpacity}
                onAnglesChange={setArmAngles}
              />
            </svg>
            <details className="rounded-md border border-border p-3">
              <summary className="cursor-pointer font-jetbrains text-xs font-semibold" style={{ color: "var(--charm-text)" }}>Arm debug</summary>
              <div className="mt-3 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <label className="flex items-center gap-2 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                  <input type="checkbox" checked={armDebug} onChange={(event) => setArmDebug(event.target.checked)} />
                  target mode
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {(["x", "y"] as const).map((axis) => (
                  <label key={axis} className="space-y-1">
                    <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>{axis} target</span>
                    <input
                      type="range"
                      min={axis === "x" ? -0.5 : -0.5}
                      max={axis === "x" ? 8.5 : 8.5}
                      step="0.1"
                      value={armDebugTarget[axis]}
                      onChange={(event) => setArmDebugTarget((current) => ({ ...current, [axis]: Number(event.target.value) }))}
                      className="w-full"
                    />
                    <span className="font-jetbrains text-xs" style={{ color: "var(--charm-cyan)" }}>{armDebugTarget[axis].toFixed(1)}</span>
                  </label>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="space-y-1">
                  <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>arm opacity</span>
                  <input type="range" min="0.15" max="1" step="0.05" value={armOpacity} onChange={(event) => setArmOpacity(Number(event.target.value))} className="w-full" />
                </label>
                <label className="space-y-1">
                  <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>expected opacity</span>
                  <input type="range" min="0" max="0.7" step="0.05" value={expectedOpacity} onChange={(event) => setExpectedOpacity(Number(event.target.value))} className="w-full" />
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="flex items-center gap-2 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                  <input type="checkbox" checked={scaraPiecesVisible} onChange={(event) => setScaraPiecesVisible(event.target.checked)} />
                  pieces visible
                </label>
                <label className="space-y-1">
                  <span className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>pieces opacity</span>
                  <input type="range" min="0.05" max="1" step="0.05" value={scaraPiecesOpacity} onChange={(event) => setScaraPiecesOpacity(Number(event.target.value))} className="w-full" />
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
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardHeader className="px-4 pt-4 pb-2 flex-row items-center justify-between">
            <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>Vision Pipeline</h2>
            <Badge variant="outline" className="font-jetbrains" style={{ borderColor: "var(--charm-border)", color: "var(--charm-cyan)" }}>camera on</Badge>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-4">
            <div className="grid grid-cols-3 gap-2">
              <Button variant="outline" size="sm" className="font-jetbrains" onClick={testCapture} disabled={busy || Boolean(testBusy)}>
                {testBusy === "capture" ? <Loader2 className="size-4 animate-spin" /> : <Camera className="size-4" />}
                Capture
              </Button>
              <Button variant="outline" size="sm" className="font-jetbrains" onClick={testVisionPipeline} disabled={busy || Boolean(testBusy)}>
                {testBusy === "pipeline" ? <Loader2 className="size-4 animate-spin" /> : <Eye className="size-4" />}
                Pipeline
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
            <div className="grid grid-cols-2 gap-3">
              <ImagePanel title="Raw photo" image={result?.original} active={turnState === "capturing"} />
              <ImagePanel title="Preprocessed" image={result?.preprocessed} active={turnState === "processing"} />
              <VisionImage title="Grid" image={result?.preprocessed} overlay="grid" />
              <VisionImage title="Occupancy" image={result?.preprocessed} overlay="occupancy" occupancyMatrix={result?.occupancy_matrix} occupancyScores={result?.occupancy_scores} />
              <VisionImage title="Colors" image={result?.refined_warp} overlay="colors" colorLabels={result?.color_labels} />
              <ImagePanel title="Warped" image={result?.refined_warp} />
            </div>

            {result && (
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md border border-border p-3">
                  <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>Pieces</p>
                  <p className="mt-1 font-jetbrains text-lg" style={{ color: "var(--charm-text)" }}>{result.stats.occupied}</p>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>Pipeline</p>
                  <p className="mt-1 font-jetbrains text-lg" style={{ color: "var(--charm-cyan)" }}>{result.total_ms.toFixed(0)} ms</p>
                </div>
              </div>
            )}

            {result && (
              <div className="overflow-auto">
                <ChessBoard colorLabels={result.color_labels} occupancyScores={result.occupancy_scores} brightnessScores={result.brightness_scores} highlightUnknown />
              </div>
            )}
          </CardContent>
        </Card>

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

      {overlayOpen && result && (
        <div className="fixed bottom-4 right-4 z-50 w-90 max-w-[calc(100vw-2rem)] rounded-md border p-3 shadow-2xl" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="size-4" style={{ color: "var(--charm-cyan)" }} />
              <p className="font-jetbrains text-xs font-semibold" style={{ color: "var(--charm-text)" }}>Latest camera analysis</p>
            </div>
            <button onClick={() => setOverlayOpen(false)} className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>close</button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <ImagePanel title="raw" image={result.original} />
            <ImagePanel title="pre" image={result.preprocessed} />
            <VisionImage title="colors" image={result.refined_warp} overlay="colors" colorLabels={result.color_labels} />
          </div>
          <p className="mt-2 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
            {result.image_path ?? "latest frame"} · {stepResult?.inference.move_uci ? `move ${stepResult.inference.move_uci}` : "move pending"}
          </p>
        </div>
      )}
    </div>
  );
}
