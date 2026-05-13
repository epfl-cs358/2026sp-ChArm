"use client";

import { imageSrc } from "@/lib/image";
import { ColorLabel } from "@/lib/types";

export type OverlayMode = "grid" | "occupancy" | "colors";

interface Props {
  title: string;
  image?: string;
  active?: boolean;
  maxHeight?: number | string;
  overlay?: OverlayMode;
  colorLabels?: ColorLabel[][];
  occupancyMatrix?: number[][];
  occupancyScores?: number[][];
}

function cellColor(label: ColorLabel) {
  if (label === "white") return "oklch(0.98 0 0 / 0.72)";
  if (label === "black") return "oklch(0.08 0 0 / 0.72)";
  if (label === "unknown") return "oklch(0.65 0.2 310 / 0.62)";
  return "transparent";
}

export function VisionOverlay({
  mode,
  colorLabels,
  occupancyMatrix,
  occupancyScores,
}: {
  mode: OverlayMode;
  colorLabels?: ColorLabel[][];
  occupancyMatrix?: number[][];
  occupancyScores?: number[][];
}) {
  const rows = Array.from({ length: 8 }, (_, row) => row);
  const cols = Array.from({ length: 8 }, (_, col) => col);

  return (
    <div className="pointer-events-none absolute inset-0 grid grid-cols-8 grid-rows-8">
      {rows.flatMap((row) =>
        cols.map((col) => {
          const occupied = Boolean(occupancyMatrix?.[row]?.[col]);
          const score = occupancyScores?.[row]?.[col] ?? 0;
          const label = colorLabels?.[row]?.[col] ?? "empty";
          const intensity = Math.min(0.5, 0.1 + score / 24);

          return (
            <div
              key={`${row}-${col}`}
              className="relative border"
              style={{
                borderColor: mode === "grid" ? "oklch(1 0 0 / 0.42)" : "oklch(1 0 0 / 0.18)",
                background:
                  mode === "occupancy" && occupied
                    ? `oklch(0.75 0.16 215 / ${intensity})`
                    : "transparent",
              }}
            >
              {mode === "colors" && label !== "empty" && (
                <span
                  className="absolute left-1/2 top-1/2 block h-[42%] w-[42%] -translate-x-1/2 -translate-y-1/2 rounded-full"
                  style={{
                    background: cellColor(label),
                    border:
                      label === "white"
                        ? "1px solid oklch(0.78 0 0 / 0.9)"
                        : "1px solid oklch(1 0 0 / 0.35)",
                    boxShadow: "0 1px 8px oklch(0 0 0 / 0.32)",
                  }}
                />
              )}
            </div>
          );
        }),
      )}
    </div>
  );
}

export default function VisionImage({
  title,
  image,
  active,
  maxHeight = 128,
  overlay,
  colorLabels,
  occupancyMatrix,
  occupancyScores,
}: Props) {
  return (
    <div
      className="overflow-hidden rounded-md border"
      style={{
        borderColor: active ? "oklch(from var(--charm-cyan) l c h / 0.45)" : "var(--charm-border)",
        background: "var(--background)",
      }}
    >
      <div className="flex items-center justify-between border-b border-border px-2 py-1.5">
        <span className="font-jetbrains text-xs" style={{ color: active ? "var(--charm-cyan)" : "var(--charm-muted)" }}>
          {title}
        </span>
        {active && <span className="h-1.5 w-1.5 rounded-full status-loading" />}
      </div>
      {image ? (
        <div className="flex justify-center p-0">
          <div className="relative aspect-square w-full overflow-hidden">
            <img
              src={imageSrc(image)}
              alt={title}
              className="h-full w-full object-contain"
              style={{ maxHeight }}
            />
            {overlay && (
              <VisionOverlay
                mode={overlay}
                colorLabels={colorLabels}
                occupancyMatrix={occupancyMatrix}
                occupancyScores={occupancyScores}
              />
            )}
          </div>
        </div>
      ) : (
        <div className="flex h-32 items-center justify-center font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
          waiting
        </div>
      )}
    </div>
  );
}
