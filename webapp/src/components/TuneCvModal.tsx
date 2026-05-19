"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { PipelineParams } from "@/lib/types";

type Label = "empty" | "white" | "black";

export interface TunedThresholds {
  occupancy_threshold: number;
  occupancy_delta_threshold?: number;
  white_threshold: number;
  black_threshold: number;
  white_delta_threshold?: number;
  black_delta_threshold?: number;
}

interface Props {
  onClose: () => void;
  refinedWarpB64: string | undefined;
  imagePath?: string | null;
  params: PipelineParams;
  onTuned: (t: TunedThresholds) => void;
}

const LABEL_COLORS: Record<Label, string> = {
  empty: "rgba(239, 68, 68, 0.55)",
  white: "rgba(229, 231, 235, 0.65)",
  black: "rgba(17, 24, 39, 0.65)",
};

export function TuneCvModal({ onClose, refinedWarpB64, imagePath, params, onTuned }: Props) {
  const [activeLabel, setActiveLabel] = useState<Label>("empty");
  const [annotations, setAnnotations] = useState<Record<string, Label>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TunedThresholds | null>(null);

  const counts = useMemo(() => {
    const c: Record<Label, number> = { empty: 0, white: 0, black: 0 };
    for (const label of Object.values(annotations)) c[label]++;
    return c;
  }, [annotations]);

  const ready = counts.empty >= 1 && counts.white >= 1 && counts.black >= 1;

  const handleCellClick = (row: number, col: number) => {
    const key = `${row},${col}`;
    setAnnotations((prev) => {
      const next = { ...prev };
      if (next[key] === activeLabel) {
        delete next[key];
      } else {
        next[key] = activeLabel;
      }
      return next;
    });
  };

  const handleApply = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      const payload = {
        annotations: Object.entries(annotations).map(([key, label]) => {
          const [row, col] = key.split(",").map((n) => parseInt(n, 10));
          return { row, col, label };
        }),
        params,
        image_path: imagePath ?? undefined,
      };
      const response = await api.tuneCv(payload);
      const tuned: TunedThresholds = {
        occupancy_threshold: response.tuning.occupancy_threshold,
        occupancy_delta_threshold: response.tuning.occupancy_delta_threshold,
        white_threshold: response.tuning.white_threshold,
        black_threshold: response.tuning.black_threshold,
        white_delta_threshold: response.tuning.white_delta_threshold,
        black_delta_threshold: response.tuning.black_delta_threshold,
      };
      setResult(tuned);
      onTuned(tuned);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tune failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto py-8 backdrop-blur-sm"
      style={{ background: "oklch(0 0 0 / 0.7)" }}
      onClick={onClose}
    >
      <div
        className="mx-4 w-full max-w-3xl rounded-md border shadow-2xl"
        style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--charm-border)" }}>
          <span className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
            Tune CV
          </span>
          <button onClick={onClose} className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
            ✕ close
          </button>
        </div>

        <div className="space-y-4 p-4">
          <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
            Pick a label, then click squares on the warped board. Provide at least one cell of each label. Click again to clear.
          </p>

          <div className="flex flex-wrap gap-2">
            {(Object.keys(LABEL_COLORS) as Label[]).map((label) => (
              <button
                key={label}
                onClick={() => setActiveLabel(label)}
                className={`flex items-center gap-2 rounded border px-3 py-1.5 font-jetbrains text-xs uppercase ${
                  activeLabel === label ? "ring-2 ring-cyan-400" : ""
                }`}
                style={{ borderColor: "var(--charm-border)", color: "var(--charm-text)" }}
              >
                <span className="size-3 rounded" style={{ background: LABEL_COLORS[label] }} />
                {label} ({counts[label]})
              </button>
            ))}
          </div>

          <div className="relative mx-auto aspect-square w-full max-w-[480px] border" style={{ borderColor: "var(--charm-border)" }}>
            {refinedWarpB64 ? (
              <img
                src={`data:image/jpeg;base64,${refinedWarpB64}`}
                alt="warped board"
                className="absolute inset-0 h-full w-full select-none"
                draggable={false}
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                Run pipeline first to get a warped board image.
              </div>
            )}
            <div className="absolute inset-0 grid grid-cols-8 grid-rows-8">
              {Array.from({ length: 64 }).map((_, idx) => {
                const row = Math.floor(idx / 8);
                const col = idx % 8;
                const key = `${row},${col}`;
                const label = annotations[key];
                return (
                  <button
                    key={key}
                    onClick={() => handleCellClick(row, col)}
                    className="border border-white/10 transition-colors hover:bg-white/10"
                    style={{ background: label ? LABEL_COLORS[label] : "transparent" }}
                    aria-label={`cell ${row},${col}`}
                    disabled={!refinedWarpB64}
                  />
                );
              })}
            </div>
          </div>

          {error && (
            <div className="rounded border px-3 py-2 font-jetbrains text-xs" style={{ borderColor: "var(--charm-border)", color: "#fca5a5" }}>
              {error}
            </div>
          )}

          {result && (
            <div className="rounded border px-3 py-2 font-jetbrains text-xs" style={{ borderColor: "var(--charm-border)", color: "var(--charm-text)" }}>
              <div className="mb-1 uppercase" style={{ color: "var(--charm-muted)" }}>tuned thresholds</div>
              <div>occupancy (edge+std): {result.occupancy_threshold}</div>
              {result.occupancy_delta_threshold !== undefined && (
                <div>occupancy Δ (vs empty ref): {result.occupancy_delta_threshold}</div>
              )}
              <div>white brightness: {result.white_threshold}</div>
              <div>black brightness: {result.black_threshold}</div>
              {result.black_delta_threshold !== undefined && (
                <div>black dark-Δ (vs empty ref): {result.black_delta_threshold}</div>
              )}
              {result.occupancy_delta_threshold === undefined && (
                <div className="mt-2" style={{ color: "var(--charm-muted)" }}>
                  Tip: capture an Empty board reference to also tune the Δ-thresholds (the ones the live pipeline actually uses).
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" className="font-jetbrains" onClick={onClose} disabled={busy}>
              Close
            </Button>
            <Button
              size="sm"
              className="font-jetbrains"
              onClick={handleApply}
              disabled={!ready || !refinedWarpB64 || busy}
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : null}
              Apply & save
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
