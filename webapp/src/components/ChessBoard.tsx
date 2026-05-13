"use client";

import { ColorLabel } from "@/lib/types";

interface Props {
  colorLabels: ColorLabel[][];
  occupancyScores?: number[][];
  brightnessScores?: number[][];
  highlightUnknown?: boolean;
  onCellAnnotate?: (row: number, col: number, color: "black" | "white" | "clear") => void;
  labeledCells?: boolean[][];
  annotationLabels?: ColorLabel[][];
}

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];
const RANKS = ["8", "7", "6", "5", "4", "3", "2", "1"];

function PieceMarker({
  color,
  score,
  brightness,
  labeled,
}: {
  color: ColorLabel;
  score?: number;
  brightness?: number;
  labeled?: boolean;
}) {
  if (color === "empty" && !labeled) return null;

  const dotStyle: Record<ColorLabel, React.CSSProperties> = {
    white: {
      background: "oklch(0.98 0 0)",
      boxShadow: "0 1px 8px oklch(0 0 0 / 0.35)",
      border: "2px solid oklch(0.78 0 0)",
    },
    black: {
      background: "oklch(0.16 0 0)",
      boxShadow: "0 1px 8px oklch(0 0 0 / 0.5)",
      border: "2px solid oklch(0.42 0 0)",
    },
    unknown: {
      background: "oklch(0.65 0.2 310)",
      boxShadow: "0 0 6px oklch(0.65 0.2 310 / 0.7)",
      border: "2px solid oklch(0.65 0.2 310 / 0.4)",
      animation: "pulse 1s infinite",
    },
    empty: {},
  };

  if (color === "empty") {
    return (
      <div className="relative group w-full h-full flex flex-col items-center justify-center gap-px">
        <div
          className="w-4 h-4 rounded-sm border border-dashed"
          style={{ borderColor: "var(--charm-muted)", opacity: 0.75 }}
        />
        {score !== undefined && (
          <span
            className="font-jetbrains leading-none"
            style={{ fontSize: "7px", color: "var(--charm-muted)", opacity: 0.8 }}
          >
            {score.toFixed(1)}
          </span>
        )}
      </div>
    );
  }

  const scoreColor =
    color === "white"
      ? "oklch(0.45 0 0)"
      : color === "black"
      ? "var(--charm-cyan)"
      : "oklch(0.65 0.2 310)";

  return (
    <div className="relative group w-full h-full flex flex-col items-center justify-center gap-px">
      <div className="w-4 h-4 rounded-full" style={dotStyle[color]} />
      {brightness !== undefined && (
        <span
          className="font-jetbrains leading-none"
          style={{ fontSize: "7px", color: scoreColor }}
        >
          {brightness.toFixed(0)}
        </span>
      )}
      {(score !== undefined || brightness !== undefined) && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-10 hidden group-hover:block pointer-events-none">
          <div
            className="rounded px-2 py-1 text-xs font-jetbrains whitespace-nowrap"
            style={{
              background: "var(--charm-card)",
              border: "1px solid var(--charm-border)",
            }}
          >
            {score !== undefined && (
              <div style={{ color: "var(--charm-muted)" }}>
                edge:{" "}
                <span style={{ color: "var(--charm-cyan)" }}>{score.toFixed(2)}</span>
              </div>
            )}
            {brightness !== undefined && (
              <div style={{ color: "var(--charm-muted)" }}>
                bright:{" "}
                <span style={{ color: "var(--charm-amber)" }}>{brightness.toFixed(0)}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function AnnotationMarker({ color }: { color: ColorLabel }) {
  if (color === "empty") return null;

  const style: Record<ColorLabel, React.CSSProperties> = {
    white: {
      background: "oklch(1 0 0 / 0.42)",
      border: "2px solid oklch(0.96 0 0 / 0.9)",
    },
    black: {
      background: "oklch(0 0 0 / 0.34)",
      border: "2px solid oklch(0.05 0 0 / 0.82)",
    },
    unknown: {
      background: "oklch(0.65 0.2 310 / 0.28)",
      border: "2px solid oklch(0.65 0.2 310 / 0.7)",
    },
    empty: {},
  };

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      <div className="h-8 w-8 rounded-full" style={style[color]} />
    </div>
  );
}

export default function ChessBoard({
  colorLabels,
  occupancyScores,
  brightnessScores,
  highlightUnknown,
  onCellAnnotate,
  labeledCells,
  annotationLabels,
}: Props) {
  return (
    <div className="inline-block">
      <div className="flex items-center gap-1 mb-1">
        <div className="w-5" />
        {FILES.map((f) => (
          <div
            key={f}
            className="w-11 text-center text-xs font-jetbrains"
            style={{ color: "var(--charm-muted)" }}
          >
            {f}
          </div>
        ))}
      </div>

      {colorLabels.map((row, ri) => (
        <div key={ri} className="flex items-center gap-1 mb-1">
          <div
            className="w-5 text-right text-xs font-jetbrains pr-1"
            style={{ color: "var(--charm-muted)" }}
          >
            {RANKS[ri]}
          </div>
          {row.map((cell, ci) => {
            const isLight = (ri + ci) % 2 === 0;
            const canAnnotate = Boolean(onCellAnnotate);
            const annotationColor = annotationLabels?.[ri]?.[ci] ?? "empty";
            return (
              <div
                key={ci}
                className={`w-11 h-11 relative flex items-center justify-center rounded-sm ${
                  canAnnotate ? "cursor-pointer hover:ring-2 hover:ring-primary/70" : ""
                }`}
                onClick={(event) =>
                  onCellAnnotate?.(ri, ci, event.shiftKey || event.altKey ? "clear" : "black")
                }
                onContextMenu={(event) => {
                  if (!onCellAnnotate) return;
                  event.preventDefault();
                  onCellAnnotate(ri, ci, "white");
                }}
                style={{
                  background: isLight
                    ? "var(--charm-board-light)"
                    : "var(--charm-board-dark)",
                  outline:
                    cell === "unknown" && highlightUnknown
                      ? "1px solid oklch(0.65 0.2 310 / 0.6)"
                      : "none",
                }}
              >
                {labeledCells?.[ri]?.[ci] && <AnnotationMarker color={annotationColor} />}
                <PieceMarker
                  color={cell}
                  score={occupancyScores?.[ri]?.[ci]}
                  brightness={brightnessScores?.[ri]?.[ci]}
                />
              </div>
            );
          })}
        </div>
      ))}

      <div className="mt-2 flex items-center gap-3">
        {[
          { color: "var(--charm-cyan)", label: "white" },
          { color: "var(--charm-amber)", label: "black" },
          { color: "oklch(0.65 0.2 310)", label: "unknown" },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1.5">
            <span
              className="w-3 h-3 rounded-full inline-block"
              style={{ background: color }}
            />
            <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
              {label}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
