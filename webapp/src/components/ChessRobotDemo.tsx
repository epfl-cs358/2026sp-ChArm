"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import { RotateCcw } from "lucide-react";
import RobotArmOverlay, { ArmMove } from "@/components/RobotArmOverlay";
import { Button } from "@/components/ui/button";

const FILES = ["h", "g", "f", "e", "d", "c", "b", "a"];
const RANKS = ["1", "2", "3", "4", "5", "6", "7", "8"];
const PIECES: Record<string, string> = {
  wp: "♙", wn: "♘", wb: "♗", wr: "♖", wq: "♕", wk: "♔",
  bp: "♟", bn: "♞", bb: "♝", br: "♜", bq: "♛", bk: "♚",
};

type EngineStatus = "ready" | "fallback";
type DemoStep = "calibration" | "play";

function moveToArmMove(move: Move, id: number): ArmMove {
  return {
    id,
    from: move.from,
    to: move.to,
    label: `robot ${move.san}`,
    piece: PIECES[`b${move.piece}`] ?? "♟",
  };
}

function fallbackMove(game: Chess) {
  const moves = game.moves({ verbose: true });
  const captures = moves.filter((move) => move.captured);
  const checks = moves.filter((move) => move.san.includes("+"));
  return (checks[0] ?? captures[0] ?? moves[Math.floor(Math.random() * moves.length)])?.lan;
}

export default function ChessRobotDemo({ embedded = false }: { embedded?: boolean }) {
  const [game, setGame] = useState(() => new Chess());
  const [selected, setSelected] = useState<Square | null>(null);
  const [legalTargets, setLegalTargets] = useState<string[]>([]);
  const [thinking, setThinking] = useState(false);
  const [status, setStatus] = useState<EngineStatus>("ready");
  const [armMove, setArmMove] = useState<ArmMove | null>(null);
  const [pendingRobotGame, setPendingRobotGame] = useState<Chess | null>(null);
  const [robotMovingFrom, setRobotMovingFrom] = useState<Square | null>(null);
  const [moveLog, setMoveLog] = useState<string[]>([]);
  const [step, setStep] = useState<DemoStep>("calibration");
  const [calibrating, setCalibrating] = useState(false);
  const [calibrated, setCalibrated] = useState(false);
  const moveId = useRef(0);

  const board = useMemo(() => game.board(), [game]);
  const gameOver = game.isGameOver();

  const startCalibration = () => {
    setStep("calibration");
    setCalibrating(true);
    setCalibrated(false);
    window.setTimeout(() => {
      setCalibrating(false);
      setCalibrated(true);
      setStep("play");
    }, 2800);
  };

  const requestBestMove = useCallback(
    (snapshot: Chess) =>
      new Promise<string | null>((resolve) => {
        const fallback = () => resolve(fallbackMove(snapshot) ?? null);
        fetch("/api/stockfish", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fen: snapshot.fen(), depth: 8 }),
        })
          .then((res) => {
            if (!res.ok) throw new Error("Stockfish request failed");
            return res.json() as Promise<{ bestMove?: string }>;
          })
          .then((data) => {
            setStatus("ready");
            resolve(data.bestMove ?? fallbackMove(snapshot) ?? null);
          })
          .catch(() => {
            setStatus("fallback");
            fallback();
          });
      }),
    []
  );

  const robotReply = useCallback(
    async (afterHuman: Chess) => {
      if (afterHuman.isGameOver()) return;
      setThinking(true);
      const best = await requestBestMove(afterHuman);
      if (!best) {
        setThinking(false);
        return;
      }
      const next = new Chess(afterHuman.fen());
      const robotMove = next.move(best);
      if (robotMove) {
        setPendingRobotGame(next);
        setRobotMovingFrom(robotMove.from);
        moveId.current += 1;
        setArmMove(moveToArmMove(robotMove, moveId.current));
      }
    },
    [requestBestMove]
  );

  const finishRobotMove = useCallback(
    (finishedMove: ArmMove) => {
      if (!pendingRobotGame || armMove?.id !== finishedMove.id) return;
      setGame(pendingRobotGame);
      setMoveLog((moves) => [...moves, finishedMove.label.replace(/^robot\s+/, "")]);
      setPendingRobotGame(null);
      setRobotMovingFrom(null);
      setThinking(false);
    },
    [armMove?.id, pendingRobotGame]
  );

  const reset = () => {
    setGame(new Chess());
    setSelected(null);
    setLegalTargets([]);
    setThinking(false);
    setArmMove(null);
    setPendingRobotGame(null);
    setRobotMovingFrom(null);
    setMoveLog([]);
    setStep(calibrated ? "play" : "calibration");
  };

  const clickSquare = (square: Square) => {
    if (!calibrated || thinking || gameOver || game.turn() !== "w") return;
    const piece = game.get(square);

    if (!selected) {
      if (piece?.color === "w") {
        setSelected(square);
        setLegalTargets(game.moves({ square, verbose: true }).map((move) => move.to));
      }
      return;
    }

    if (selected === square) {
      setSelected(null);
      setLegalTargets([]);
      return;
    }

    const next = new Chess(game.fen());
    const move = next.move({ from: selected, to: square, promotion: "q" });
    if (move) {
      setGame(next);
      setMoveLog((moves) => [...moves, move.san]);
      setSelected(null);
      setLegalTargets([]);
      void robotReply(next);
    } else if (piece?.color === "w") {
      setSelected(square);
      setLegalTargets(game.moves({ square, verbose: true }).map((candidate) => candidate.to));
    }
  };

  const title = !calibrated
    ? "Calibration required"
    : gameOver
    ? game.isCheckmate()
      ? game.turn() === "w"
        ? "Stockfish wins by checkmate"
        : "You win by checkmate"
      : "Game over"
    : thinking
    ? "Robot is thinking"
    : game.turn() === "w"
    ? "Your move"
    : "Robot move";

  return (
    <div className={embedded ? "mx-auto w-full max-w-[980px]" : "mx-auto max-w-screen-2xl"}>
      {!embedded && (
        <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-mono text-2xl font-semibold text-foreground">Chess Robot Demo</h1>
            <p className="mt-1 text-sm text-muted-foreground">Calibrate the arm, then play white against Stockfish.</p>
          </div>
          <HeaderActions status={status} reset={reset} startCalibration={startCalibration} calibrated={calibrated} calibrating={calibrating} />
        </div>
      )}

      {embedded && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-mono text-lg font-semibold text-foreground">Robot chess demo</h2>
            <p className="text-sm text-muted-foreground">Step 1 runs the Arduino homing sequence, step 2 starts the playable board.</p>
          </div>
          <HeaderActions status={status} reset={reset} startCalibration={startCalibration} calibrated={calibrated} calibrating={calibrating} />
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(520px,720px)_minmax(260px,1fr)]">
        <div className="card p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="font-mono text-sm font-semibold text-foreground">{title}</h2>
            <span className="font-mono text-xs text-muted-foreground">{calibrated ? game.fen().split(" ")[0] : "homing first"}</span>
          </div>
          <div className="relative mx-auto aspect-square w-full max-w-[640px] overflow-visible">
            <RobotArmOverlay mode={calibrating ? "calibrating" : armMove ? "playing" : "idle"} move={armMove} onDone={finishRobotMove} />
            <div className="absolute inset-0 grid grid-cols-8 grid-rows-8 overflow-hidden rounded-md border border-border">
              {board.map((row, rowIndex) =>
                row.map((piece, colIndex) => {
                  const square = `${FILES[colIndex]}${RANKS[rowIndex]}` as Square;
                  const light = (rowIndex + colIndex) % 2 === 0;
                  const active = selected === square;
                  const target = legalTargets.includes(square);
                  const pieceKey = piece ? `${piece.color}${piece.type}` : "";
                  const hiddenForRobot = robotMovingFrom === square;
                  return (
                    <button
                      key={square}
                      type="button"
                      data-square={square}
                      aria-label={square}
                      onClick={() => clickSquare(square)}
                      className="relative flex aspect-square min-h-0 min-w-0 items-center justify-center overflow-hidden text-[clamp(1.6rem,5vw,3.6rem)] transition-transform hover:scale-[1.02]"
                      style={{
                        background: active
                          ? "oklch(0.78 0.14 210 / 0.55)"
                          : light
                          ? "oklch(0.86 0.035 88)"
                          : "oklch(0.46 0.055 185)",
                      }}
                    >
                      {target && <span className="absolute h-[22%] w-[22%] rounded-full bg-primary/60" />}
                      {piece && !hiddenForRobot && (
                        <span
                          className="relative select-none font-serif leading-none"
                          style={{
                            color: piece.color === "w" ? "white" : "black",
                            textShadow: piece.color === "w" ? "0 1px 2px black, 0 0 1px black" : "0 1px 1px white, 0 0 1px white",
                          }}
                        >
                          {PIECES[pieceKey]}
                        </span>
                      )}
                      <span className="absolute bottom-1 right-1 font-mono text-[10px] text-black/45">{square}</span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <InfoBox label="Last moves" value={moveLog.slice(-8).join(" ") || "none"} />
            <InfoBox label="Robot command" value={armMove ? `${armMove.from} -> ${armMove.to}` : "waiting"} />
          </div>
        </div>

        <div className="card p-5">
          <h2 className="font-mono text-sm font-semibold text-foreground">Sequence</h2>
          <div className="mt-4 space-y-3">
            <StepRow active={step === "calibration"} done={calibrated} title="1. Calibrate" text="Arduino sequence: Z bottom switch, J1 switch, J1 zero offset, J2 min/max sweep, J2 center zero." />
            <StepRow active={step === "play"} done={false} title="2. Play chess" text={calibrated ? "Move a white piece. Stockfish controls the black pieces." : "Available after calibration."} />
            <StepRow active={!!armMove} done={false} title="3. Robot move" text={armMove ? "Pick up, translate over the board, place down." : "Waiting for the engine response."} />
          </div>
        </div>
      </div>
    </div>
  );
}

function HeaderActions({
  status,
  reset,
  startCalibration,
  calibrated,
  calibrating,
}: {
  status: EngineStatus;
  reset: () => void;
  startCalibration: () => void;
  calibrated: boolean;
  calibrating: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="rounded-md border border-border bg-card px-3 py-1.5 font-mono text-xs text-muted-foreground">
        engine: {status === "ready" ? "Stockfish" : "fallback"}
      </span>
      <Button variant={calibrated ? "outline" : "default"} onClick={startCalibration} disabled={calibrating} className="font-mono">
        {calibrating ? "Calibrating..." : calibrated ? "Recalibrate" : "Start calibration"}
      </Button>
      <Button variant="outline" onClick={reset} className="font-mono">
        <RotateCcw className="size-4" />
        Reset
      </Button>
    </div>
  );
}

function InfoBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-secondary/30 p-3">
      <p className="font-mono text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 min-h-6 font-mono text-sm text-foreground">{value}</p>
    </div>
  );
}

function StepRow({ active, done, title, text }: { active: boolean; done: boolean; title: string; text: string }) {
  return (
    <div className="rounded-md border border-border bg-secondary/30 p-3">
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${done ? "status-ok" : active ? "status-loading" : ""}`} style={!done && !active ? { background: "var(--muted-foreground)" } : undefined} />
        <p className="font-mono text-sm font-semibold text-foreground">{title}</p>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{text}</p>
    </div>
  );
}
