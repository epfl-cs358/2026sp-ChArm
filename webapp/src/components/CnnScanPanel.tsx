"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  CnnActiveModel,
  CnnCellPrediction,
  CnnScanResult,
} from "@/lib/api";
import { imageSrc } from "@/lib/image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import DebugImages from "@/components/DebugImages";

// We don't reuse <ChessBoard /> directly here because it expects ColorLabel[][]
// and we want to overlay confidence + low-confidence/disagreement rings per
// cell. Same row/col convention (row 0 = rank 8, col 0 = file a).

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];
const RANKS = ["8", "7", "6", "5", "4", "3", "2", "1"];
const LOW_CONFIDENCE_THRESHOLD = 0.7;

type LabelKey = "empty" | "white" | "black";

function colorFor(label: LabelKey): string {
  if (label === "white") return "oklch(0.96 0 0)";
  if (label === "black") return "oklch(0.18 0 0)";
  return "transparent";
}

function disagreementMap(scan: CnnScanResult | null): Map<string, string> {
  const out = new Map<string, string>();
  if (!scan?.classical_comparison?.disagreement_cells) return out;
  for (const d of scan.classical_comparison.disagreement_cells) {
    out.set(`${d.row}-${d.col}`, `CNN ${d.cnn} vs classical ${d.classical}`);
  }
  return out;
}

interface Props {
  /** Render-only mode (used in the wizard); the panel is otherwise self-driving. */
  initialScan?: CnnScanResult | null;
}

export default function CnnScanPanel({ initialScan = null }: Props) {
  const [active, setActive] = useState<CnnActiveModel | null>(null);
  const [scan, setScan] = useState<CnnScanResult | null>(initialScan);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number } | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  const refreshActive = useCallback(async () => {
    try {
      const a = await api.cnnActiveModel();
      setActive(a);
    } catch (e) {
      setActive(null);
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refreshActive();
  }, [refreshActive]);

  const runScan = useCallback(async (capture: boolean) => {
    setScanning(true);
    setError(null);
    try {
      const r = await api.cnnScan({ capture, compare_classical: true });
      setScan(r);
      setSelectedCell(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScanning(false);
    }
  }, []);

  const selectedPrediction: CnnCellPrediction | null =
    scan && selectedCell
      ? scan.predictions.find(
          (p) => p.row === selectedCell.row && p.col === selectedCell.col,
        ) ?? null
      : null;

  const selectedCrop: string | null =
    scan && selectedCell
      ? scan.cell_crops_b64[selectedCell.row * 8 + selectedCell.col] ?? null
      : null;

  const disagreements = disagreementMap(scan);

  const debugPanels = scan
    ? [
        { key: "cnn_warped", label: "Warped board (CNN input)", b64: scan.warped_board_b64 },
        { key: "cnn_overlay", label: "Per-cell labels + confidence", b64: scan.cnn_overlay_b64 },
      ]
    : [];

  const submitFeedback = useCallback(
    async (trueLabel: LabelKey) => {
      if (!scan || !selectedCell || !active?.run_id) return;
      setFeedbackBusy(true);
      setFeedbackMsg(null);
      try {
        const res = await api.cnnFeedback({
          run_id: active.run_id,
          row: selectedCell.row,
          col: selectedCell.col,
          true_label: trueLabel,
          crop_b64: selectedCrop ?? undefined,
        });
        if (res.appended_to_source) {
          setFeedbackMsg(
            `Saved as bulk cell to source dataset "${res.source_dataset}" at ${res.square}. ` +
              `Re-run Step 3 (build) + Step 4 (train) to fold it into the model.`,
          );
        } else {
          setFeedbackMsg(
            `Queued for retrain. ${res.reason ?? "Rebuild the CNN dataset so future feedback can append directly."}`,
          );
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setFeedbackBusy(false);
      }
    },
    [scan, selectedCell, selectedCrop, active?.run_id],
  );

  return (
    <div className="flex flex-col gap-4">
      <div
        className="flex items-center justify-between p-3 rounded-md"
        style={{ background: "var(--charm-card)", border: "1px solid var(--charm-border)" }}
      >
        <div className="flex items-center gap-3 text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
          <span>active model:</span>
          {active?.run_id ? (
            <span style={{ color: active.loaded ? "var(--charm-cyan)" : "var(--charm-amber)" }}>
              {active.run_id}
              {active.val_acc != null && ` · val ${(active.val_acc * 100).toFixed(1)}%`}
              {!active.loaded && " (loading)"}
            </span>
          ) : (
            <span style={{ color: "var(--charm-amber)" }}>none — activate one in step 5</span>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => runScan(true)}
            disabled={!active?.run_id || scanning}
          >
            {scanning ? "scanning…" : "capture & classify"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => runScan(false)}
            disabled={!active?.run_id || scanning}
          >
            re-run on cached frame
          </Button>
        </div>
      </div>

      {error && (
        <div
          className="p-3 rounded-md text-xs font-jetbrains"
          style={{
            background: "oklch(0.95 0.06 30 / 0.15)",
            color: "var(--charm-amber)",
            border: "1px solid oklch(0.65 0.18 40 / 0.5)",
          }}
        >
          {error}
        </div>
      )}

      {scan && (
        <div className="flex flex-wrap gap-6">
          {/* Board with overlay */}
          <div className="inline-block">
            <div className="flex items-center gap-1 mb-1">
              <div className="w-5" />
              {FILES.map((f) => (
                <div
                  key={f}
                  className="w-12 text-center text-xs font-jetbrains"
                  style={{ color: "var(--charm-muted)" }}
                >
                  {f}
                </div>
              ))}
            </div>
            {scan.white_bitmap.map((_, ri) => (
              <div key={ri} className="flex items-center gap-1 mb-1">
                <div
                  className="w-5 text-right text-xs font-jetbrains pr-1"
                  style={{ color: "var(--charm-muted)" }}
                >
                  {RANKS[ri]}
                </div>
                {scan.white_bitmap[ri].map((_, ci) => {
                  const pred = scan.predictions.find((p) => p.row === ri && p.col === ci);
                  const label = (pred?.label ?? "empty") as LabelKey;
                  const confidence = pred?.confidence ?? 0;
                  const isLight = (ri + ci) % 2 === 0;
                  const lowConfidence = confidence < LOW_CONFIDENCE_THRESHOLD;
                  const disagreesWith = disagreements.get(`${ri}-${ci}`);
                  const isSelected = selectedCell?.row === ri && selectedCell?.col === ci;
                  let ring = "none";
                  if (disagreesWith) ring = "2px solid oklch(0.65 0.22 30)";
                  else if (lowConfidence && label !== "empty")
                    ring = "2px solid oklch(0.85 0.16 90)";
                  else if (lowConfidence) ring = "2px dashed oklch(0.85 0.16 90 / 0.6)";
                  if (isSelected) ring = "2px solid var(--charm-cyan)";
                  return (
                    <button
                      key={ci}
                      onClick={() => setSelectedCell({ row: ri, col: ci })}
                      title={disagreesWith ?? `${label} · ${(confidence * 100).toFixed(1)}%`}
                      className="w-12 h-12 relative flex flex-col items-center justify-center rounded-sm cursor-pointer"
                      style={{
                        background: isLight
                          ? "var(--charm-board-light)"
                          : "var(--charm-board-dark)",
                        outline: ring,
                      }}
                    >
                      {label !== "empty" && (
                        <div
                          className="w-5 h-5 rounded-full"
                          style={{
                            background: colorFor(label),
                            border:
                              label === "white"
                                ? "1px solid oklch(0.78 0 0)"
                                : "1px solid oklch(0.42 0 0)",
                            boxShadow: "0 1px 4px oklch(0 0 0 / 0.35)",
                          }}
                        />
                      )}
                      <span
                        className="font-jetbrains leading-none mt-0.5"
                        style={{ fontSize: "8px", color: "var(--charm-muted)" }}
                      >
                        {(confidence * 100).toFixed(0)}
                      </span>
                    </button>
                  );
                })}
              </div>
            ))}
            <div
              className="mt-2 text-xs font-jetbrains flex gap-4"
              style={{ color: "var(--charm-muted)" }}
            >
              <span>
                <span
                  className="inline-block w-3 h-3 rounded-sm align-middle mr-1"
                  style={{ border: "2px solid oklch(0.85 0.16 90)" }}
                />
                low conf &lt; {Math.round(LOW_CONFIDENCE_THRESHOLD * 100)}%
              </span>
              <span>
                <span
                  className="inline-block w-3 h-3 rounded-sm align-middle mr-1"
                  style={{ border: "2px solid oklch(0.65 0.22 30)" }}
                />
                disagrees w/ classical
              </span>
              <span>inference: {scan.inference_ms.toFixed(1)} ms</span>
            </div>
          </div>

          {/* Cell drill-down */}
          <Card
            className="flex-1 min-w-72"
            style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
          >
            <CardHeader className="px-4 py-3">
              <span className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                {selectedCell
                  ? `cell ${FILES[selectedCell.col]}${RANKS[selectedCell.row]} (row ${selectedCell.row}, col ${selectedCell.col})`
                  : "select a cell"}
              </span>
            </CardHeader>
            <CardContent className="p-4 flex flex-col gap-3">
              {selectedPrediction && selectedCrop ? (
                <>
                  <div className="flex items-center gap-3">
                    <img
                      src={imageSrc(selectedCrop)}
                      alt="cell crop"
                      className="rounded"
                      style={{ width: 96, height: 96, imageRendering: "pixelated" }}
                    />
                    <div className="flex-1 flex flex-col gap-1.5">
                      {(["empty", "white", "black"] as const).map((cls) => {
                        const p = selectedPrediction.probs[cls] ?? 0;
                        return (
                          <div key={cls} className="text-xs font-jetbrains">
                            <div className="flex justify-between" style={{ color: "var(--charm-muted)" }}>
                              <span>{cls}</span>
                              <span>{(p * 100).toFixed(1)}%</span>
                            </div>
                            <div
                              className="h-1.5 rounded-sm"
                              style={{ background: "oklch(0.3 0 0)" }}
                            >
                              <div
                                className="h-1.5 rounded-sm"
                                style={{
                                  width: `${Math.max(2, p * 100)}%`,
                                  background:
                                    cls === selectedPrediction.label
                                      ? "var(--charm-cyan)"
                                      : "oklch(0.5 0 0)",
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div
                    className="text-xs font-jetbrains flex flex-col gap-1.5 pt-2 border-t"
                    style={{ color: "var(--charm-muted)", borderColor: "var(--charm-border)" }}
                  >
                    <span>
                      mark this prediction as wrong — appends a hard-negative
                      bulk cell to the source dataset:
                    </span>
                    <div className="flex gap-2">
                      {(["empty", "white", "black"] as const).map((cls) =>
                        cls === selectedPrediction.label ? null : (
                          <Button
                            key={cls}
                            size="sm"
                            variant="outline"
                            disabled={feedbackBusy || !active?.run_id}
                            onClick={() => submitFeedback(cls)}
                          >
                            actually {cls}
                          </Button>
                        ),
                      )}
                    </div>
                    {feedbackMsg && (
                      <span style={{ color: "var(--charm-cyan)" }}>{feedbackMsg}</span>
                    )}
                  </div>
                </>
              ) : (
                <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                  click any cell to inspect its softmax distribution.
                </span>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {scan && debugPanels.length > 0 && (
        <div>
          <p
            className="text-xs font-jetbrains mb-2"
            style={{ color: "var(--charm-muted)" }}
          >
            CNN debug
          </p>
          <DebugImages panels={debugPanels} />
        </div>
      )}

      {scan?.classical_comparison?.error && (
        <p className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
          classical comparison unavailable: {scan.classical_comparison.error}
        </p>
      )}
    </div>
  );
}
