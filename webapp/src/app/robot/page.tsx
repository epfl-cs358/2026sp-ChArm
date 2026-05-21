"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Cable, Check, Crosshair, Database, Gamepad2, Home, MapPin, Play, RotateCcw, Save, SquareArrowOutUpRight, StepBack, StepForward, Trash2, Unplug, X } from "lucide-react";
import { api } from "@/lib/api";
import { RobotCalibration, RobotCalibrationWrite, RobotCommandResult, RobotStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type PointKey = "a1" | "h1" | "h8";
type Point3DKey = "home" | "capture_bin";
type PieceKey = "pawn" | "knight" | "bishop" | "rook" | "queen" | "king";

const DEFAULT_SERIAL_PORT = "/dev/ttyUSB0";
const ROBOT_PORT_STORAGE_KEY = "charm.robot.port";
const PIECES: PieceKey[] = ["pawn", "knight", "bishop", "rook", "queen", "king"];
const DEFAULT_PICK_Z: Record<PieceKey, number> = {
  pawn: 3,
  knight: 0,
  bishop: 11,
  rook: 11,
  queen: 17,
  king: 19,
};

const DEFAULT_PLACE_Z: Record<PieceKey, number> = {
  pawn: 30,
  knight: 30,
  bishop: 32,
  rook: 35,
  queen: 38,
  king: 40,
};

const DEFAULT_FORM: RobotCalibrationWrite = {
  a1: { x: 0, y: 0 },
  h1: { x: 262.5, y: 0 },
  h8: { x: 262.5, y: 262.5 },
  z_hover: 60,
  z_down: 5,
  home: { x: 0, y: 0, z: 60 },
  capture_bin: { x: 0, y: 0, z: 5 },
  pick_z: DEFAULT_PICK_Z,
  place_z: DEFAULT_PLACE_Z,
};

function numberValue(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

const ARROW_LEN = 22;
const COMPASS_MARGIN = 52;
const DEFAULT_FILE_VECTOR = { x: 1, y: 0 };
const DEFAULT_RANK_VECTOR = { x: 0, y: 1 };

function BoardViz({
  square,
  onSquareClick,
  livePosition,
  calibration,
}: {
  square: string;
  onSquareClick: (sq: string) => void;
  livePosition: { x: number; y: number; z: number } | null;
  calibration: RobotCalibration | null;
}) {
  const CELL = 36;
  const BOARD = CELL * 8;
  const W = BOARD + COMPASS_MARGIN;
  const H = BOARD;

  const fv = calibration?.file_vector ?? DEFAULT_FILE_VECTOR;
  const rv = calibration?.rank_vector ?? DEFAULT_RANK_VECTOR;

  const liveFrac = useMemo(() => {
    if (!livePosition || !calibration) return null;
    const { a1 } = calibration;
    const dx = livePosition.x - a1.x;
    const dy = livePosition.y - a1.y;
    const det = fv.x * rv.y - fv.y * rv.x;
    if (Math.abs(det) < 0.001) return null;
    return {
      fi: (dx * rv.y - dy * rv.x) / det,
      ri: (fv.x * dy - fv.y * dx) / det,
    };
  }, [livePosition, calibration, fv, rv]);

  // Direction of robot +X in SVG space: normalize(rv.y, fv.y)
  // Direction of robot +Y in SVG space: normalize(-rv.x, -fv.x)
  const axisX = useMemo(() => {
    const len = Math.hypot(rv.y, fv.y);
    return len < 0.001 ? { dx: 1, dy: 0 } : { dx: rv.y / len, dy: fv.y / len };
  }, [fv, rv]);

  const axisY = useMemo(() => {
    const len = Math.hypot(rv.x, fv.x);
    return len < 0.001 ? { dx: 0, dy: -1 } : { dx: -rv.x / len, dy: -fv.x / len };
  }, [fv, rv]);

  const CAL_COLORS: Record<string, string> = {
    a1: "var(--charm-cyan)",
    h1: "oklch(0.78 0.18 65)",
    h8: "oklch(0.78 0.22 145)",
  };

  const cx0 = BOARD + COMPASS_MARGIN / 2;
  const cy0 = BOARD / 2;

  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      {/* Board squares */}
      {Array.from({ length: 8 }, (_, rankIdx) =>
        Array.from({ length: 8 }, (_, fileIdx) => {
          const rank = 8 - rankIdx;
          const sq = `${String.fromCharCode(97 + fileIdx)}${rank}`;
          const isLight = (fileIdx + rank) % 2 !== 0;
          const isSelected = square === sq;
          const calColor = CAL_COLORS[sq];
          const x = fileIdx * CELL;
          const y = rankIdx * CELL;
          return (
            <g key={sq} onClick={() => onSquareClick(sq)} style={{ cursor: "pointer" }}>
              <rect
                x={x} y={y} width={CELL} height={CELL}
                style={{ fill: isSelected ? "oklch(0.55 0.18 200 / 0.65)" : isLight ? "var(--charm-board-light)" : "var(--charm-board-dark)" }}
                stroke={isSelected ? "var(--charm-cyan)" : "none"}
                strokeWidth={isSelected ? 2 : 0}
              />
              {!calColor && (
                <text x={x + 2} y={y + 9} fontSize="7" style={{ fill: isLight ? "oklch(0.38 0.04 70)" : "oklch(0.72 0.03 70)", pointerEvents: "none", userSelect: "none" }}>
                  {sq}
                </text>
              )}
              {calColor && (
                <>
                  <circle cx={x + CELL / 2} cy={y + CELL / 2} r={8} style={{ fill: calColor, opacity: 0.92, pointerEvents: "none" }} />
                  <text x={x + CELL / 2} y={y + CELL / 2 + 3} fontSize="7" textAnchor="middle" style={{ fill: "var(--background)", fontWeight: "bold", pointerEvents: "none", userSelect: "none" }}>
                    {sq}
                  </text>
                </>
              )}
            </g>
          );
        })
      )}

      {/* Live position crosshair */}
      {liveFrac && (
        <g style={{ pointerEvents: "none" }}>
          <circle
            cx={liveFrac.fi * CELL + CELL / 2}
            cy={(7 - liveFrac.ri) * CELL + CELL / 2}
            r={11} fill="none" stroke="oklch(0.85 0.28 145)" strokeWidth={2.5}
          />
          <line
            x1={liveFrac.fi * CELL + CELL / 2 - 8} y1={(7 - liveFrac.ri) * CELL + CELL / 2}
            x2={liveFrac.fi * CELL + CELL / 2 + 8} y2={(7 - liveFrac.ri) * CELL + CELL / 2}
            stroke="oklch(0.85 0.28 145)" strokeWidth={2}
          />
          <line
            x1={liveFrac.fi * CELL + CELL / 2} y1={(7 - liveFrac.ri) * CELL + CELL / 2 - 8}
            x2={liveFrac.fi * CELL + CELL / 2} y2={(7 - liveFrac.ri) * CELL + CELL / 2 + 8}
            stroke="oklch(0.85 0.28 145)" strokeWidth={2}
          />
        </g>
      )}

      {/* Axis compass */}
      <rect x={BOARD} y={0} width={COMPASS_MARGIN} height={H} style={{ fill: "oklch(0.14 0 0 / 0.6)" }} />
      {/* X axis arrow (orange) */}
      <line
        x1={cx0} y1={cy0}
        x2={cx0 + axisX.dx * ARROW_LEN} y2={cy0 + axisX.dy * ARROW_LEN}
        stroke="oklch(0.78 0.18 65)" strokeWidth={2} markerEnd="url(#arrowX)"
      />
      <text
        x={cx0 + axisX.dx * (ARROW_LEN + 8)}
        y={cy0 + axisX.dy * (ARROW_LEN + 8) + 4}
        fontSize="9" textAnchor="middle" style={{ fill: "oklch(0.78 0.18 65)", fontFamily: "monospace", userSelect: "none" }}
      >X</text>
      {/* Y axis arrow (cyan) */}
      <line
        x1={cx0} y1={cy0}
        x2={cx0 + axisY.dx * ARROW_LEN} y2={cy0 + axisY.dy * ARROW_LEN}
        stroke="var(--charm-cyan)" strokeWidth={2} markerEnd="url(#arrowY)"
      />
      <text
        x={cx0 + axisY.dx * (ARROW_LEN + 8)}
        y={cy0 + axisY.dy * (ARROW_LEN + 8) + 4}
        fontSize="9" textAnchor="middle" style={{ fill: "var(--charm-cyan)", fontFamily: "monospace", userSelect: "none" }}
      >Y</text>

      <defs>
        <marker id="arrowX" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" style={{ fill: "oklch(0.78 0.18 65)" }} />
        </marker>
        <marker id="arrowY" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" style={{ fill: "var(--charm-cyan)" }} />
        </marker>
      </defs>
    </svg>
  );
}

function OutputLog({ result, error }: { result: RobotCommandResult | null; error: string | null }) {
  return (
    <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
      <CardHeader className="px-4 pt-4 pb-2">
        <h2 className="text-sm font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Serial Output</h2>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="min-h-32 rounded-md border border-border p-3 font-jetbrains text-xs" style={{ background: "var(--background)", color: "var(--charm-muted)" }}>
          {error ? (
            <p style={{ color: "oklch(0.65 0.22 25)" }}>{error}</p>
          ) : result ? (
            result.responses.length > 0 ? result.responses.map((line, index) => <p key={`${line}-${index}`}>{line}</p>) : <p>No response before timeout.</p>
          ) : (
            <p>Run a robot command to see Arduino responses.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function RobotPage() {
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const [form, setForm] = useState<RobotCalibrationWrite>(DEFAULT_FORM);
  const [port, setPort] = useState(() => {
    if (typeof window === "undefined") return DEFAULT_SERIAL_PORT;
    return window.localStorage.getItem(ROBOT_PORT_STORAGE_KEY) || DEFAULT_SERIAL_PORT;
  });
  const [baud, setBaud] = useState(115200);
  const [square, setSquare] = useState("e4");
  const [uci, setUci] = useState("e2e4");
  const [raw, setRaw] = useState("pos");
  const [pieceType, setPieceType] = useState<PieceKey>("pawn");
  const [goto, setGoto] = useState({ x: 0, y: 0, z: 35 });
  const [squareSize, setSquareSize] = useState(37.5);
  const [livePosition, setLivePosition] = useState<{ x: number; y: number; z: number } | null>(null);
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [keyboardJog, setKeyboardJog] = useState(false);
  const [jogModeHint, setJogModeHint] = useState(false);
  const [boardCalModeHint, setBoardCalModeHint] = useState(false);
  const [down, setDown] = useState(false);
  const [flags, setFlags] = useState({ capture: false, castling: false, promotion: false });
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<RobotCommandResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [eepromLoaded, setEepromLoaded] = useState(false);
  const eepromAutoLoadRef = useRef(false);
  const jogInFlightRef = useRef(false);
  const lastJogAtRef = useRef(0);

  useEffect(() => {
    window.localStorage.setItem(ROBOT_PORT_STORAGE_KEY, port);
  }, [port]);

  const applyStatus = useCallback((next: RobotStatus) => {
    setStatus(next);
    setPort((current) => {
      const detected = next.detected_port || next.active_port || null;
      if (!detected) return current;
      if (!current || current === DEFAULT_SERIAL_PORT) return detected;
      const knownPorts = new Set(next.ports.map((p) => p.device));
      return knownPorts.has(current) ? current : detected;
    });

    const c = next.robot_calibration.calibration;
    setSquareSize(Math.hypot(c.file_vector.x, c.file_vector.y));
    const a1 = c.a1;
    const h1 = {
      x: a1.x + c.file_vector.x * 7,
      y: a1.y + c.file_vector.y * 7,
    };
    const h8 = {
      x: h1.x + c.rank_vector.x * 7,
      y: h1.y + c.rank_vector.y * 7,
    };
    setForm({
      a1,
      h1,
      h8,
      z_hover: c.z_hover,
      z_down: c.z_down,
      home: c.home,
      capture_bin: c.capture_bin,
      pick_z: { ...DEFAULT_PICK_Z, ...c.pick_z },
      place_z: { ...DEFAULT_PLACE_Z, ...c.place_z },
    });
  }, []);

  const resolveSerialPort = useCallback((currentPort?: string | null) => {
    const current = currentPort || port;
    const detected = status?.detected_port || status?.active_port || null;
    if (!current) return detected || undefined;
    if (current === DEFAULT_SERIAL_PORT) return detected || undefined;
    if (status?.ports.some((p) => p.device === current)) return current;
    return detected || current;
  }, [port, status]);

  const applyBoardInfo = useCallback((response: RobotCommandResult) => {
    const boardInfo = response.board_info;
    if (!boardInfo?.calibration) return false;

    const c = boardInfo.calibration;
    const a1 = c.a1;
    const h1 = {
      x: a1.x + c.file_vector.x * 7,
      y: a1.y + c.file_vector.y * 7,
    };
    const h8 = {
      x: h1.x + c.rank_vector.x * 7,
      y: h1.y + c.rank_vector.y * 7,
    };
    setSquareSize(Math.hypot(c.file_vector.x, c.file_vector.y));
    setForm((current) => ({
      ...current,
      a1,
      h1,
      h8,
      capture_bin: c.capture_bin,
    }));
    setEepromLoaded(true);
    setSaveStatus("Loaded EEPROM calibration from Arduino");
    return true;
  }, []);

  const refresh = useCallback(async () => {
    const next = await api.getRobotStatus();
    applyStatus(next);
    return next;
  }, [applyStatus]);

  useEffect(() => {
    let cancelled = false;
    api.getRobotStatus()
      .then((next) => {
        if (!cancelled) applyStatus(next);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load robot status");
      });
    return () => {
      cancelled = true;
    };
  }, [applyStatus]);

  const readEeprom = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setBusy("read-eeprom");
      setError(null);
      setSaveStatus(null);
      setResult(null);
    }
    try {
      const response = await api.readRobotEeprom(resolveSerialPort(), baud);
      if (!options?.silent) setResult(response);
      if (response.position) setLivePosition(response.position);
      if (!applyBoardInfo(response) && !options?.silent) {
        setError("EEPROM board calibration is incomplete or missing on Arduino");
      }
    } catch (e: unknown) {
      if (!options?.silent) {
        setError(e instanceof Error ? e.message : "Failed to read Arduino EEPROM");
      }
    } finally {
      if (!options?.silent) setBusy(null);
    }
  }, [applyBoardInfo, baud, port]);

  useEffect(() => {
    if (!status || eepromAutoLoadRef.current) return;
    const resolvedPort = port || status.detected_port || status.active_port;
    if (!resolvedPort) return;
    eepromAutoLoadRef.current = true;
    void readEeprom({ silent: true });
  }, [port, readEeprom, status]);

  const computedA8 = useMemo(() => ({
    x: form.a1.x + form.h8.x - form.h1.x,
    y: form.a1.y + form.h8.y - form.h1.y,
  }), [form.a1, form.h1, form.h8]);

  const updatePoint = (key: PointKey, axis: "x" | "y", value: string) => {
    setForm((current) => ({ ...current, [key]: { ...current[key], [axis]: numberValue(value) } }));
  };

  const updatePoint3D = (key: Point3DKey, axis: "x" | "y" | "z", value: string) => {
    setForm((current) => ({ ...current, [key]: { ...current[key], [axis]: numberValue(value) } }));
  };

  const updatePickZ = (piece: PieceKey, value: string) => {
    setForm((current) => ({ ...current, pick_z: { ...current.pick_z, [piece]: numberValue(value) } }));
  };

  const updatePlaceZ = (piece: PieceKey, value: string) => {
    setForm((current) => ({ ...current, place_z: { ...current.place_z, [piece]: numberValue(value) } }));
  };

  const captureCorner = async (corner: PointKey) => {
    setBusy(`capture-${corner}`);
    setError(null);
    setResult(null);
    try {
      const response = await api.sendRobotCommand({
        command: "capture-corner",
        port: resolveSerialPort(),
        baud,
        corner,
      });
      setResult(response);
      const position = response.position ?? livePosition;
      if (position) {
        setLivePosition(position);
        setForm((current) => ({ ...current, [corner]: { x: position.x, y: position.y } }));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : `Failed to capture ${corner.toUpperCase()}`);
    } finally {
      setBusy(null);
    }
  };

  const saveCalibration = async () => {
    setBusy("save");
    setError(null);
    setSaveStatus(null);
    try {
      await api.updateRobotCalibration(form);
      setSaveStatus("Saved robot_calibration.json");
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save calibration");
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (!liveEnabled || keyboardJog) return;
    if (!port) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await api.getRobotPosition(resolveSerialPort(), baud);
        if (!cancelled && response.position) {
          setLivePosition(response.position);
        }
      } catch {
        if (!cancelled) setLivePosition(null);
      }
    };
    const interval = window.setInterval(poll, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [baud, keyboardJog, liveEnabled, port]);

  const sendJog = useCallback(async (key: "w" | "a" | "s" | "d" | "u" | "j" | "c" | "v") => {
    const now = performance.now();
    if (jogInFlightRef.current || now - lastJogAtRef.current < 45) return;
    jogInFlightRef.current = true;
    lastJogAtRef.current = now;
    setError(null);
    try {
      const response = await api.sendRobotCommand({
        command: "jog",
        port: resolveSerialPort(),
        baud,
        raw: key,
      });
      setResult(response);
      if (response.position) {
        setLivePosition(response.position);
      } else {
        const posResponse = await api.getRobotPosition(resolveSerialPort(), baud);
        if (posResponse.position) setLivePosition(posResponse.position);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Jog command failed");
    } finally {
      jogInFlightRef.current = false;
    }
  }, [baud, port]);

  const sendBoardCalKey = useCallback(async (key: "w" | "a" | "s" | "d" | "u" | "j" | "v" | "n" | "p" | "q") => {
    const now = performance.now();
    if (jogInFlightRef.current || now - lastJogAtRef.current < 45) return;
    jogInFlightRef.current = true;
    lastJogAtRef.current = now;
    setError(null);
    try {
      const response = await api.sendRobotCommand({
        command: "board-cal-key",
        port: resolveSerialPort(),
        baud,
        raw: key,
      });
      setResult(response);
      if (response.position) {
        setLivePosition(response.position);
      } else {
        const posResponse = await api.getRobotPosition(resolveSerialPort(), baud);
        if (posResponse.position) setLivePosition(posResponse.position);
      }
      if (response.responses.some((line) => line.includes("Saved to EEPROM") || line.includes("Cancelled") || line.includes("Incomplete"))) {
        setBoardCalModeHint(false);
        await refresh();
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Board calibration command failed");
    } finally {
      jogInFlightRef.current = false;
    }
  }, [baud, port, refresh]);

  useEffect(() => {
    if (!keyboardJog) return;
    const keyMap: Record<string, "w" | "a" | "s" | "d" | "u" | "j" | "c" | "v"> = {
      w: "w",
      z: "w",
      a: "a",
      q: "a",
      s: "s",
      d: "d",
      u: "u",
      j: "j",
      c: "c",
      v: "v",
    };
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.tagName === "SELECT" || target?.isContentEditable) return;
      if (boardCalModeHint) {
        const calKey = event.key.toLowerCase();
        if (!["w", "z", "a", "q", "s", "d", "u", "j", "v", "n", "p", "escape"].includes(calKey)) return;
        event.preventDefault();
        const normalized = calKey === "z" ? "w" : calKey === "escape" ? "q" : calKey === "q" ? "a" : calKey;
        void sendBoardCalKey(normalized as "w" | "a" | "s" | "d" | "u" | "j" | "v" | "n" | "p" | "q");
        return;
      }
      const jogKey = keyMap[event.key.toLowerCase()];
      if (!jogKey) return;
      event.preventDefault();
      void sendJog(jogKey);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [boardCalModeHint, keyboardJog, sendBoardCalKey, sendJog]);

  const toggleControllerMode = async () => {
    setBusy("cm");
    setError(null);
    try {
      const response = jogModeHint
        ? await api.sendRobotCommand({
            command: "jog",
            port: resolveSerialPort(),
            baud,
            raw: "q",
          })
        : await api.sendRobotCommand({
            command: "raw",
            port: resolveSerialPort(),
            baud,
            raw: "cm",
          });
      setResult(response);
      setJogModeHint((current) => !current);
      if (!jogModeHint) setBoardCalModeHint(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to toggle controller mode");
    } finally {
      setBusy(null);
    }
  };

  const startBoardCalibration = async () => {
    setBusy("board-calibrate");
    setError(null);
    try {
      const response = await api.sendRobotCommand({
        command: "board-calibrate",
        port: resolveSerialPort(),
        baud,
      });
      setResult(response);
      setBoardCalModeHint(true);
      setJogModeHint(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start board calibration");
    } finally {
      setBusy(null);
    }
  };

  const clearBoardCalibration = async () => {
    setBusy("board-cal-clear");
    setError(null);
    try {
      const response = await api.sendRobotCommand({
        command: "board-cal-clear",
        port: resolveSerialPort(),
        baud,
      });
      setResult(response);
      setBoardCalModeHint(false);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to clear Arduino board calibration");
    } finally {
      setBusy(null);
    }
  };

  const runCommand = async (command: "pos" | "arm-calibrate" | "board-info" | "move-square" | "move" | "raw" | "goto") => {
    setBusy(command);
    setError(null);
    setResult(null);
    try {
      const response = await api.sendRobotCommand({
        command,
        port: resolveSerialPort(),
        baud,
        square,
        uci,
        raw,
        x: goto.x,
        y: goto.y,
        z: goto.z,
        piece_type: pieceType,
        down,
        ...flags,
      });
      setResult(response);
      if (response.position) setLivePosition(response.position);
      const loadedBoardInfo = command === "board-info" ? applyBoardInfo(response) : false;
      if (!loadedBoardInfo) await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Command failed");
    } finally {
      setBusy(null);
    }
  };

  const traceBoard = async () => {
    setBusy("trace");
    setError(null);
    setResult(null);
    try {
      for (const sq of ["a1", "h1", "h8", "a8", "a1"]) {
        const response = await api.sendRobotCommand({
          command: "move-square",
          port: resolveSerialPort(),
          baud,
          square: sq,
        });
        setResult(response);
        if (response.position) setLivePosition(response.position);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Trace board failed");
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    setBusy("disconnect");
    try {
      await api.disconnectRobot();
      await refresh();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Scara Calibration</h1>
          <p className="text-sm mt-1" style={{ color: "var(--charm-muted)" }}>PySerial calibration and square movement tests</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" style={{ borderColor: "var(--charm-border)", color: status?.robot_calibration.exists ? "var(--charm-cyan)" : "oklch(0.72 0.18 65)" }}>
            {status?.robot_calibration.exists ? "calibrated" : "needs calibration"}
          </Badge>
          <Badge variant="outline" style={{ borderColor: "var(--charm-border)", color: status?.serial_connected ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
            {status?.serial_connected ? `connected ${status.active_port}` : "serial idle"}
          </Badge>
          <Badge variant="outline" style={{ borderColor: "var(--charm-border)", color: boardCalModeHint ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
            Arduino cal {boardCalModeHint ? "active" : "off"}
          </Badge>
        </div>
      </div>

      {!status?.robot_calibration.exists && (
        <div className="rounded-md border px-4 py-3 flex gap-3 text-sm font-jetbrains" style={{ borderColor: "oklch(0.72 0.18 65 / 0.35)", background: "oklch(0.72 0.18 65 / 0.08)", color: "oklch(0.78 0.16 75)" }}>
          <AlertTriangle className="size-4 mt-0.5 shrink-0" />
          <p>Save a robot calibration before sending movement commands. The default grid preview is only a placeholder.</p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1.05fr_0.95fr] gap-6">
        <div className="space-y-6">
          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2">
              <h2 className="text-sm font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Serial Link</h2>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-[1fr_120px] gap-3">
                <label className="space-y-1">
                  <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>Port</span>
                  <input value={port} onChange={(e) => { setPort(e.target.value); setLivePosition(null); }} placeholder={status?.detected_port ?? DEFAULT_SERIAL_PORT} className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>Baud</span>
                  <input value={baud} onChange={(e) => setBaud(Number(e.target.value) || 115200)} className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains" />
                </label>
              </div>
              {status?.ports && status.ports.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {status.ports.map((p) => (
                    <button key={p.device} onClick={() => { setPort(p.device); setLivePosition(null); }} className="rounded-md border border-border px-2 py-1 text-xs font-jetbrains hover:border-border-bright" style={{ color: "var(--charm-muted)" }}>
                      {p.device}
                    </button>
                  ))}
                </div>
              )}
              <div className="flex gap-2 flex-wrap">
                <Button onClick={() => runCommand("pos")} disabled={!!busy} variant="outline" className="font-jetbrains"><Crosshair className="size-4" />Pos</Button>
                <Button onClick={() => runCommand("arm-calibrate")} disabled={!!busy} variant="outline" className="font-jetbrains"><RotateCcw className="size-4" />Arm Calibrate</Button>
                <Button onClick={() => runCommand("board-info")} disabled={!!busy} variant="outline" className="font-jetbrains"><MapPin className="size-4" />Board Info</Button>
                <Button onClick={() => readEeprom()} disabled={!!busy} variant="outline" className="font-jetbrains"><Database className="size-4" />Read EEPROM</Button>
                <Button onClick={startBoardCalibration} disabled={!!busy || jogModeHint} variant="outline" className="font-jetbrains"><MapPin className="size-4" />Start cal</Button>
                <Button onClick={disconnect} disabled={!!busy} variant="outline" className="font-jetbrains"><Unplug className="size-4" />Disconnect</Button>
              </div>
              <div className="rounded-md border border-border p-3">
                <p className="text-xs font-jetbrains uppercase mb-2" style={{ color: "var(--charm-muted)" }}>Real Arduino homing sequence</p>
                <div className="grid grid-cols-1 md:grid-cols-5 gap-2 text-[10px] font-jetbrains">
                  {[
                    "Z bottom switch",
                    "Z backoff + zero",
                    "J1 limit switch",
                    "J1 offset + zero",
                    "J2 min/max + center",
                  ].map((step, index) => (
                    <div key={step} className="rounded-md border border-border px-2 py-2">
                      <span style={{ color: "var(--charm-cyan)" }}>{index + 1}</span>{" "}
                      <span style={{ color: "var(--charm-muted)" }}>{step}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-md border border-border p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="text-xs font-jetbrains uppercase" style={{ color: "var(--charm-muted)" }}>Live arm position</p>
                  <label className="flex items-center gap-2 text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    <input type="checkbox" checked={liveEnabled} onChange={(e) => setLiveEnabled(e.target.checked)} />
                    poll
                  </label>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {(["x", "y", "z"] as const).map((axis) => (
                    <div key={axis} className="rounded-md border border-border px-3 py-2">
                      <p className="text-[10px] font-jetbrains uppercase" style={{ color: "var(--charm-muted)" }}>{axis}</p>
                      <p className="font-jetbrains text-lg" style={{ color: livePosition ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
                        {livePosition ? livePosition[axis].toFixed(1) : "--"}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2 flex flex-row items-center justify-between">
              <h2 className="text-sm font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Robot Calibration</h2>
              <Badge variant="outline" style={{ borderColor: "var(--charm-border)", color: eepromLoaded ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
                {eepromLoaded ? "EEPROM loaded" : "local JSON"}
              </Badge>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(["a1", "h1", "h8"] as PointKey[]).map((key) => (
                  <div key={key} className="rounded-md border border-border p-3">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs font-jetbrains uppercase" style={{ color: "var(--charm-muted)" }}>
                        {key} — Arduino board corner
                      </p>
                      <button
                        type="button"
                        disabled={!!busy}
                        onClick={() => captureCorner(key)}
                        className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-jetbrains disabled:opacity-30"
                        style={{ background: "oklch(from var(--charm-cyan) l c h / 0.12)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.35)", color: "var(--charm-cyan)" }}
                      >
                        <MapPin className="size-2.5" />copy pos
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <input value={form[key].x} onChange={(e) => updatePoint(key, "x", e.target.value)} className="rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains" />
                      <input value={form[key].y} onChange={(e) => updatePoint(key, "y", e.target.value)} className="rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains" />
                    </div>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 opacity-60">
                {([
                  { label: "a8", tag: "a1 + h8 − h1", x: computedA8.x, y: computedA8.y },
                ] as const).map(({ label, tag, x, y }) => (
                  <div key={label} className="rounded-md border border-border p-3">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs font-jetbrains uppercase" style={{ color: "var(--charm-muted)" }}>{label}</p>
                      <span className="text-[10px] font-jetbrains px-1.5 py-0.5 rounded" style={{ background: "oklch(0.5 0 0 / 0.2)", color: "var(--charm-muted)" }}>{tag}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <input readOnly value={x.toFixed(2)} className="rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains cursor-not-allowed" />
                      <input readOnly value={y.toFixed(2)} className="rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains cursor-not-allowed" />
                    </div>
                  </div>
                ))}
                <div className="rounded-md border border-border p-3">
                  <p className="text-xs font-jetbrains uppercase mb-2" style={{ color: "var(--charm-muted)" }}>file step mm</p>
                  <input
                    readOnly
                    value={squareSize}
                    className="w-full rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains cursor-not-allowed"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(["home", "capture_bin"] as Point3DKey[]).map((key) => (
                  <div key={key} className="rounded-md border border-border p-3">
                    <p className="text-xs font-jetbrains uppercase mb-2" style={{ color: "var(--charm-muted)" }}>{key.replace("_", " ")}</p>
                    <div className="grid grid-cols-3 gap-2">
                      {(["x", "y", "z"] as const).map((axis) => (
                        <input key={axis} value={form[key][axis]} onChange={(e) => updatePoint3D(key, axis, e.target.value)} className="rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains" />
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="space-y-1">
                  <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>Z hover</span>
                  <input value={form.z_hover} onChange={(e) => setForm((f) => ({ ...f, z_hover: numberValue(e.target.value) }))} className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>Z down</span>
                  <input value={form.z_down} onChange={(e) => setForm((f) => ({ ...f, z_down: numberValue(e.target.value) }))} className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains" />
                </label>
              </div>

              <div className="rounded-md border border-border p-3 space-y-3">
                <div>
                  <p className="text-xs font-jetbrains uppercase mb-2" style={{ color: "var(--charm-muted)" }}>Pick Z by piece</p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {PIECES.map((piece) => (
                      <label key={piece} className="space-y-1">
                        <span className="text-[10px] font-jetbrains uppercase" style={{ color: "var(--charm-muted)" }}>{piece}</span>
                        <input
                          value={form.pick_z[piece]}
                          onChange={(e) => updatePickZ(piece, e.target.value)}
                          className="w-full rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains"
                        />
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-jetbrains uppercase mb-2" style={{ color: "var(--charm-muted)" }}>Place Z by piece</p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {PIECES.map((piece) => (
                      <label key={piece} className="space-y-1">
                        <span className="text-[10px] font-jetbrains uppercase" style={{ color: "var(--charm-muted)" }}>{piece}</span>
                        <input
                          value={form.place_z[piece]}
                          onChange={(e) => updatePlaceZ(piece, e.target.value)}
                          className="w-full rounded-md border border-border bg-transparent px-2 py-1.5 text-sm font-jetbrains"
                        />
                      </label>
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                  Firmware stores A1/H1/H8 in Arduino EEPROM via cal. This JSON mirrors the same geometry for backend move previews.
                </p>
                <Button onClick={saveCalibration} disabled={!!busy} className="font-jetbrains" style={{ background: "oklch(from var(--charm-cyan) l c h / 0.12)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.4)", color: "var(--charm-cyan)" }}>
                  <Save className="size-4" />{busy === "save" ? "Saving..." : "Save Calibration"}
                </Button>
              </div>
              {saveStatus && <p className="text-xs font-jetbrains" style={{ color: "var(--charm-cyan)" }}>{saveStatus}</p>}
            </CardContent>
          </Card>

          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2">
              <h2 className="text-sm font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Arduino Board Cal Wizard</h2>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-3">
              <div className="flex flex-wrap gap-2">
                <Button onClick={startBoardCalibration} disabled={!!busy || jogModeHint} variant="outline" className="font-jetbrains">
                  <MapPin className="size-4" />Start cal
                </Button>
                <Button onClick={() => sendBoardCalKey("v")} disabled={!!busy || !boardCalModeHint} variant="outline" className="font-jetbrains">
                  <Check className="size-4" />Validate
                </Button>
                <Button onClick={() => sendBoardCalKey("n")} disabled={!!busy || !boardCalModeHint} variant="outline" className="font-jetbrains">
                  <StepForward className="size-4" />Skip
                </Button>
                <Button onClick={() => sendBoardCalKey("p")} disabled={!!busy || !boardCalModeHint} variant="outline" className="font-jetbrains">
                  <StepBack className="size-4" />Prev
                </Button>
                <Button onClick={() => sendBoardCalKey("q")} disabled={!!busy || !boardCalModeHint} variant="outline" className="font-jetbrains">
                  <X className="size-4" />Cancel
                </Button>
                <Button onClick={clearBoardCalibration} disabled={!!busy || boardCalModeHint} variant="outline" className="font-jetbrains">
                  <Trash2 className="size-4" />Clear EEPROM
                </Button>
              </div>
              <div className="grid grid-cols-[56px_56px_56px] gap-2 justify-center">
                <div />
                <Button type="button" onClick={() => sendBoardCalKey("w")} disabled={!boardCalModeHint} variant="outline" className="h-12 font-jetbrains">W/Z</Button>
                <div />
                <Button type="button" onClick={() => sendBoardCalKey("a")} disabled={!boardCalModeHint} variant="outline" className="h-12 font-jetbrains">A/Q</Button>
                <Button type="button" onClick={() => sendBoardCalKey("s")} disabled={!boardCalModeHint} variant="outline" className="h-12 font-jetbrains">S</Button>
                <Button type="button" onClick={() => sendBoardCalKey("d")} disabled={!boardCalModeHint} variant="outline" className="h-12 font-jetbrains">D</Button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button type="button" onClick={() => sendBoardCalKey("u")} disabled={!boardCalModeHint} variant="outline" className="font-jetbrains">U Z+</Button>
                <Button type="button" onClick={() => sendBoardCalKey("j")} disabled={!boardCalModeHint} variant="outline" className="font-jetbrains">J Z-</Button>
              </div>
              <p className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                Firmware order is H1, A1, H8. Validate writes the current corner; after H8 it saves to EEPROM.
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2">
              <h2 className="text-sm font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Movement Tests</h2>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-4">
              <div className="flex justify-center">
                <BoardViz
                  square={square}
                  onSquareClick={(sq) => setSquare(sq)}
                  livePosition={livePosition}
                  calibration={status?.robot_calibration.calibration ?? null}
                />
              </div>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex flex-wrap gap-3 text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                  <span><span style={{ color: "var(--charm-cyan)" }}>●</span> a1</span>
                  <span><span style={{ color: "oklch(0.78 0.18 65)" }}>●</span> h1</span>
                  <span><span style={{ color: "oklch(0.78 0.22 145)" }}>●</span> h8</span>
                  <span><span style={{ color: "oklch(0.85 0.28 145)" }}>⊕</span> live</span>
                  <span><span style={{ color: "oklch(0.78 0.18 65)" }}>→</span> X&nbsp;&nbsp;<span style={{ color: "var(--charm-cyan)" }}>→</span> Y</span>
                </div>
                <Button onClick={traceBoard} disabled={!!busy} variant="outline" className="font-jetbrains text-xs h-7 px-2">
                  <SquareArrowOutUpRight className="size-3" />{busy === "trace" ? "Tracing…" : "Trace Board"}
                </Button>
              </div>
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <input value={square} onChange={(e) => setSquare(e.target.value.toLowerCase())} className="rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains" />
                <Button onClick={() => runCommand("move-square")} disabled={!!busy} variant="outline" className="font-jetbrains"><SquareArrowOutUpRight className="size-4" />Move Square</Button>
              </div>
              <label className="flex items-center gap-2 text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                <input type="checkbox" checked={down} onChange={(e) => setDown(e.target.checked)} />
                Use z_down for pickup/drop height
              </label>

              <div className="grid grid-cols-[1fr_auto] gap-2">
                <input value={uci} onChange={(e) => setUci(e.target.value.toLowerCase())} className="rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains" />
                <Button onClick={() => runCommand("move")} disabled={!!busy} variant="outline" className="font-jetbrains"><Play className="size-4" />Run Move</Button>
              </div>
              <label className="space-y-1 block">
                <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>Piece type for move pickup Z</span>
                <select
                  value={pieceType}
                  onChange={(e) => setPieceType(e.target.value as PieceKey)}
                  className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains"
                >
                  {PIECES.map((piece) => (
                    <option key={piece} value={piece}>{piece}</option>
                  ))}
                </select>
              </label>
              <div className="flex gap-3 flex-wrap text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                {(["capture", "castling", "promotion"] as const).map((key) => (
                  <label key={key} className="flex items-center gap-2">
                    <input type="checkbox" checked={flags[key]} onChange={(e) => setFlags((f) => ({ ...f, [key]: e.target.checked }))} />
                    {key}
                  </label>
                ))}
              </div>

              <div className="rounded-md border border-border p-3 space-y-3">
                <p className="text-xs font-jetbrains uppercase" style={{ color: "var(--charm-muted)" }}>Debug Goto XYZ</p>
                <div className="grid grid-cols-3 gap-2">
                  {(["x", "y", "z"] as const).map((axis) => (
                    <input
                      key={axis}
                      value={goto[axis]}
                      onChange={(e) => setGoto((current) => ({ ...current, [axis]: numberValue(e.target.value) }))}
                      className="rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains"
                      aria-label={`goto ${axis}`}
                    />
                  ))}
                </div>
                <Button onClick={() => runCommand("goto")} disabled={!!busy} variant="outline" className="font-jetbrains w-full">
                  <Crosshair className="size-4" />Goto XYZ
                </Button>
              </div>

              <div className="grid grid-cols-[1fr_auto] gap-2">
                <input value={raw} onChange={(e) => setRaw(e.target.value)} className="rounded-md border border-border bg-transparent px-3 py-2 text-sm font-jetbrains" />
                <Button onClick={() => runCommand("raw")} disabled={!!busy} variant="outline" className="font-jetbrains"><Cable className="size-4" />Raw</Button>
              </div>

              <div className="rounded-md border border-border p-3 text-xs font-jetbrains space-y-1" style={{ color: "var(--charm-muted)" }}>
                <p><Home className="inline size-3 mr-1" />Calibrate arm first, then use raw <span style={{ color: "var(--charm-text)" }}>cm</span> and jog keys to capture a1/h1/h8 centers.</p>
                <p>For board corners, prefer the Arduino <span style={{ color: "var(--charm-text)" }}>cal</span> wizard above so A1/H1/H8 are saved to EEPROM.</p>
                <p>Arduino jog in controller mode: w/s Y, a/d X, u/j Z, c/v gripper, q exits.</p>
              </div>
            </CardContent>
          </Card>

          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2">
              <h2 className="text-sm font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Keyboard Jog</h2>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button onClick={toggleControllerMode} disabled={!!busy} variant="outline" className="font-jetbrains">
                  <Gamepad2 className="size-4" />{jogModeHint ? "Exit cm" : "Send cm"}
                </Button>
                <Button
                  onClick={() => setKeyboardJog((enabled) => !enabled)}
                  variant={keyboardJog ? "default" : "outline"}
                  className="font-jetbrains"
                  style={keyboardJog ? { background: "oklch(from var(--charm-cyan) l c h / 0.12)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.4)", color: "var(--charm-cyan)" } : undefined}
                >
                  {keyboardJog ? "Keyboard active" : "Enable WASD"}
                </Button>
                <Badge variant="outline" style={{ borderColor: "var(--charm-border)", color: jogModeHint ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
                  Arduino cm {jogModeHint ? "sent" : "not sent"}
                </Badge>
              </div>

              <div className="grid grid-cols-[56px_56px_56px] gap-2 justify-center">
                <div />
                <Button type="button" onClick={() => sendJog("w")} variant="outline" className="h-12 font-jetbrains">W/Z</Button>
                <div />
                <Button type="button" onClick={() => sendJog("a")} variant="outline" className="h-12 font-jetbrains">A/Q</Button>
                <Button type="button" onClick={() => sendJog("s")} variant="outline" className="h-12 font-jetbrains">S</Button>
                <Button type="button" onClick={() => sendJog("d")} variant="outline" className="h-12 font-jetbrains">D</Button>
              </div>

              <div className="grid grid-cols-4 gap-2">
                <Button type="button" onClick={() => sendJog("u")} variant="outline" className="font-jetbrains">U Z+</Button>
                <Button type="button" onClick={() => sendJog("j")} variant="outline" className="font-jetbrains">J Z-</Button>
                <Button type="button" onClick={() => sendJog("c")} variant="outline" className="font-jetbrains">C close</Button>
                <Button type="button" onClick={() => sendJog("v")} variant="outline" className="font-jetbrains">V open</Button>
              </div>

              <div className="rounded-md border border-border p-3 text-xs font-jetbrains space-y-1" style={{ color: "var(--charm-muted)" }}>
                <p>Press <span style={{ color: "var(--charm-text)" }}>Send cm</span> once before jogging so Arduino uses Cartesian controller mode; exit sends q.</p>
                <p>W/Z = +Y, S = -Y, A/Q = -X, D = +X. Holding a key repeats jog commands.</p>
              </div>
            </CardContent>
          </Card>

          <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
            <CardHeader className="px-4 pt-4 pb-2">
              <h2 className="text-sm font-jetbrains font-semibold" style={{ color: "var(--charm-text)" }}>Sample Squares</h2>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="grid grid-cols-2 gap-2">
                {status && Object.entries(status.robot_calibration.samples).map(([name, xy]) => (
                  <div key={name} className="rounded-md border border-border px-3 py-2 font-jetbrains text-xs flex justify-between">
                    <span style={{ color: "var(--charm-cyan)" }}>{name}</span>
                    <span style={{ color: "var(--charm-muted)" }}>{xy[0].toFixed(1)}, {xy[1].toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <OutputLog result={result} error={error} />
        </div>
      </div>
    </div>
  );
}
