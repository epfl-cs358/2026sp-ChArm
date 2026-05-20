"use client";

import { useCallback, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

export type BulkLabel = "empty" | "white" | "black";

const ALL_SQUARES: string[] = (() => {
  const out: string[] = [];
  for (let rank = 1; rank <= 8; rank++)
    for (const file of "abcdefgh") out.push(`${file}${rank}`);
  return out;
})();

// Visual palette for each brush. Matches the rest of the wizard.
const BRUSH_STYLE: Record<BulkLabel | "none", { bg: string; border: string; label: string }> = {
  none: {
    bg: "transparent",
    border: "var(--charm-border)",
    label: "—",
  },
  empty: {
    bg: "color-mix(in oklab, var(--charm-muted) 25%, transparent)",
    border: "var(--charm-muted)",
    label: "empty",
  },
  white: {
    bg: "color-mix(in oklab, #ffffff 70%, transparent)",
    border: "#ffffff",
    label: "white",
  },
  black: {
    bg: "color-mix(in oklab, #1f2937 80%, transparent)",
    border: "#1f2937",
    label: "black",
  },
};

export interface BulkPaintBoardProps {
  labels: Record<string, BulkLabel>;
  onChange: (next: Record<string, BulkLabel>) => void;
  busy?: boolean;
  // Capture-stage counts already in the dataset, per square, per label. Used
  // for the small badge that shows how much data the square already has.
  counts?: {
    empty?: Record<string, number>;
    white?: Record<string, number>;
    black?: Record<string, number>;
  };
}

/**
 * 8x8 board overlay with drag-paint to assign labels to multiple squares at
 * once. Brushes: empty / white / black / erase. Painted squares are remembered
 * in the parent's `labels` map. The parent provides a capture button that
 * sends `labels` to the bulk endpoint.
 *
 * Mapping note: square "a1" is rendered at the bottom-left (standard chess
 * notation). The backend's bulk endpoint maps that to the right cell of the
 * (180°-rotated) warped capture using the same convention as the CNN dataset
 * builder, so painting "a1" really saves to bulk/<color>/a1/.
 */
export default function BulkPaintBoard({
  labels,
  onChange,
  busy,
  counts,
}: BulkPaintBoardProps) {
  const [brush, setBrush] = useState<BulkLabel | "erase">("white");
  const [isMouseDown, setIsMouseDown] = useState(false);

  const apply = useCallback(
    (sq: string) => {
      const next = { ...labels };
      if (brush === "erase") {
        delete next[sq];
      } else {
        next[sq] = brush;
      }
      onChange(next);
    },
    [brush, labels, onChange],
  );

  const handleDown = (sq: string) => {
    if (busy) return;
    setIsMouseDown(true);
    apply(sq);
  };
  const handleEnter = (sq: string) => {
    if (busy) return;
    if (!isMouseDown) return;
    apply(sq);
  };
  const handleUp = () => setIsMouseDown(false);

  const paintedCounts = useMemo(() => {
    const c = { empty: 0, white: 0, black: 0 };
    for (const v of Object.values(labels)) c[v]++;
    return c;
  }, [labels]);

  const clearAll = () => onChange({});
  const fillAll = (label: BulkLabel) => {
    const next: Record<string, BulkLabel> = {};
    for (const sq of ALL_SQUARES) next[sq] = label;
    onChange(next);
  };

  return (
    <div className="space-y-3" onMouseUp={handleUp} onMouseLeave={handleUp}>
      <div
        className="rounded-md border p-3 flex flex-wrap items-center gap-2 font-jetbrains text-xs"
        style={{ borderColor: "var(--charm-border)" }}
      >
        <span style={{ color: "var(--charm-muted)" }} className="pr-1">Brush:</span>
        {(["empty", "white", "black"] as BulkLabel[]).map((b) => {
          const active = brush === b;
          const style = BRUSH_STYLE[b];
          return (
            <Button
              key={b}
              size="sm"
              variant={active ? "default" : "outline"}
              onClick={() => setBrush(b)}
              disabled={busy}
              style={{
                background: active ? style.bg : undefined,
                borderColor: style.border,
                color: b === "white" ? "#111" : undefined,
              }}
            >
              {style.label}
            </Button>
          );
        })}
        <Button
          size="sm"
          variant={brush === "erase" ? "default" : "outline"}
          onClick={() => setBrush("erase")}
          disabled={busy}
        >
          erase
        </Button>
        <span className="ml-3" style={{ color: "var(--charm-muted)" }}>
          Painted: {paintedCounts.white}w · {paintedCounts.black}b · {paintedCounts.empty}e
          {" · "}
          {Object.keys(labels).length}/64
        </span>
        <span className="flex-1" />
        <Button size="sm" variant="outline" onClick={clearAll} disabled={busy}>
          clear
        </Button>
        <Button size="sm" variant="outline" onClick={() => fillAll("empty")} disabled={busy}>
          fill empty
        </Button>
      </div>
      <div
        className="grid grid-cols-8 gap-1 w-fit select-none"
        // Capture pointer-up anywhere so we don't get stuck in "dragging"
        // state when the user releases off-board.
      >
        {Array.from({ length: 8 }).map((_, rowIdx) =>
          Array.from({ length: 8 }).map((_, colIdx) => {
            const file = "abcdefgh"[colIdx];
            const rank = 8 - rowIdx;
            const sq = `${file}${rank}`;
            const lbl = labels[sq];
            const style = lbl ? BRUSH_STYLE[lbl] : BRUSH_STYLE.none;
            const existing =
              (counts?.white?.[sq] ?? 0) +
              (counts?.black?.[sq] ?? 0) +
              (counts?.empty?.[sq] ?? 0);
            return (
              <button
                key={sq}
                type="button"
                disabled={busy}
                onMouseDown={() => handleDown(sq)}
                onMouseEnter={() => handleEnter(sq)}
                className="rounded text-[10px] font-jetbrains border h-11 w-11 flex flex-col items-center justify-center hover:border-cyan-400 disabled:opacity-40"
                style={{
                  background: style.bg,
                  borderColor: lbl ? style.border : "var(--charm-border)",
                  borderWidth: lbl ? 2 : 1,
                  color: lbl === "white" ? "#111" : undefined,
                }}
                title={`${sq}${lbl ? ` = ${lbl}` : ""}${existing ? ` (${existing} existing)` : ""}`}
              >
                <span>{sq}</span>
                <span style={{ opacity: 0.7 }}>
                  {lbl ? style.label[0].toUpperCase() : existing ? existing : ""}
                </span>
              </button>
            );
          }),
        )}
      </div>
      <p className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
        Click + drag to paint multiple squares. Each painted square will save a
        crop into <code>bulk/&lt;color&gt;/&lt;sq&gt;/</code> on capture.
      </p>
    </div>
  );
}
