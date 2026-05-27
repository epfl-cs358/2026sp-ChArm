"use client";

import { useState, useCallback, useEffect } from "react";
import { api } from "@/lib/api";
import { DEFAULT_PARAMS, PipelineResult } from "@/lib/types";
import DebugImages from "@/components/DebugImages";
import ManualCalibration from "@/components/ManualCalibration";
import ArucoCalibration from "@/components/ArucoCalibration";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const OCCUPANCY_STORAGE_KEY = "charm.occupancy-threshold";

const DEBUG_PANELS = [
  { key: "original", label: "Raw" },
  { key: "board_edges_debug", label: "Board Edges" },
  { key: "first_warp", label: "Board Warp" },
  { key: "refined_warp", label: "Refined Warp" },
  { key: "preprocessed", label: "Preprocessed" },
  { key: "grid_debug", label: "Grid" },
  { key: "occupancy_debug", label: "Occupancy" },
  { key: "piece_color_debug", label: "Piece Colors" },
] as const;

export default function LabPage() {
  const [occupancyThreshold, setOccupancyThreshold] = useState(DEFAULT_PARAMS.occupancy_threshold);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showManualCalibration, setShowManualCalibration] = useState(false);
  const [showArucoCalibration, setShowArucoCalibration] = useState(false);
  const [rawImages, setRawImages] = useState<{ name: string; path: string }[]>([]);
  const [selectedRawImage, setSelectedRawImage] = useState<string | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(OCCUPANCY_STORAGE_KEY);
    if (stored) {
      const parsed = parseFloat(stored);
      if (Number.isFinite(parsed)) setOccupancyThreshold(Math.max(0.5, Math.min(80, parsed)));
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(OCCUPANCY_STORAGE_KEY, String(occupancyThreshold));
  }, [occupancyThreshold]);

  useEffect(() => {
    api.listImages()
      .then((r) => {
        setRawImages(r.images);
        if (r.images.length > 0) setSelectedRawImage(r.images[0].path);
      })
      .catch(() => null);
  }, []);

  const runPipeline = useCallback(async (imagePath?: string) => {
    setLoading(true);
    setError(null);
    try {
      const path = imagePath ?? selectedRawImage;
      const r = await api.runPipeline({
        ...DEFAULT_PARAMS,
        occupancy_threshold: occupancyThreshold,
        ...(path ? { image_path: path } : {}),
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
    } finally {
      setLoading(false);
    }
  }, [occupancyThreshold, selectedRawImage]);

  const captureAndRun = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const capture = await api.captureFromCamera();
      setSelectedRawImage(capture.path);
      setRawImages((cur) =>
        cur.some((i) => i.path === capture.path)
          ? cur
          : [{ name: capture.path.split("/").pop() ?? "latest", path: capture.path }, ...cur],
      );
      await runPipeline(capture.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Capture failed");
      setLoading(false);
    }
  }, [runPipeline]);

  return (
    <div className="p-6 max-w-screen-xl mx-auto">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-mono font-semibold text-text-bright">Vision Pipeline</h1>
          <p className="text-text-muted text-sm mt-1">Run the pipeline and calibrate the board warp</p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={captureAndRun}
            disabled={loading}
            className="btn-cyan px-4 py-2 rounded-md text-sm font-mono font-semibold disabled:opacity-50"
          >
            {loading ? "Running..." : "▶ Capture & Run"}
          </button>
          <button
            onClick={() => runPipeline()}
            disabled={loading || !selectedRawImage}
            className="px-3 py-2 text-xs font-mono rounded-md border border-border text-text-muted hover:text-text hover:border-border-bright disabled:opacity-50"
          >
            ▶ Run Image
          </button>

          {rawImages.length > 0 ? (
            <Select
              value={selectedRawImage ?? rawImages[0]?.path}
              onValueChange={setSelectedRawImage}
            >
              <SelectTrigger
                size="sm"
                className="min-w-48 border-border bg-transparent font-mono text-xs text-text-muted hover:text-text"
              >
                <SelectValue placeholder="Choose raw image" />
              </SelectTrigger>
              <SelectContent align="end" className="border-border bg-card font-mono text-xs">
                {rawImages.map((img) => (
                  <SelectItem key={img.path} value={img.path}>
                    {img.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <div className="rounded-md border border-border px-3 py-2 text-xs font-mono text-text-muted">
              No raw images
            </div>
          )}

          <button
            onClick={() => setShowManualCalibration((v) => !v)}
            className={`px-3 py-2 text-xs font-mono rounded-md border transition-colors ${
              showManualCalibration
                ? "border-cyan-DEFAULT/40 text-cyan-DEFAULT bg-cyan-glow"
                : "border-border text-text-muted hover:text-text hover:border-border-bright"
            }`}
          >
            Set Image Warp
          </button>
          <button
            onClick={() => setShowArucoCalibration((v) => !v)}
            className={`px-3 py-2 text-xs font-mono rounded-md border transition-colors ${
              showArucoCalibration
                ? "border-cyan-DEFAULT/40 text-cyan-DEFAULT bg-cyan-glow"
                : "border-border text-text-muted hover:text-text hover:border-border-bright"
            }`}
          >
            ArUco calibration
          </button>
        </div>
      </div>

      {/* Occupancy threshold — the only VISION parameter exposed here */}
      <div
        className="mb-6 card px-4 py-4 max-w-sm"
        style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
      >
        <div className="mb-3 flex items-center gap-2">
          <span
            className="text-[10px] font-jetbrains font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded"
            style={{
              color: "var(--charm-cyan)",
              border: "1px solid oklch(from var(--charm-cyan) l c h / 0.35)",
              background: "oklch(from var(--charm-cyan) l c h / 0.08)",
            }}
          >
            VISION
          </span>
          <p className="text-xs font-jetbrains font-semibold text-text-bright">Occupancy Threshold</p>
          <span className="ml-auto font-mono text-sm" style={{ color: "var(--charm-cyan)" }}>
            {occupancyThreshold.toFixed(1)}
          </span>
        </div>
        <Slider
          min={0.5}
          max={80}
          step={0.5}
          value={[occupancyThreshold]}
          onValueChange={(vals) => setOccupancyThreshold(Array.isArray(vals) ? vals[0] : vals)}
          className="w-full"
        />
        <div className="mt-1 flex justify-between">
          <span className="text-xs font-jetbrains text-text-muted opacity-40">0.5</span>
          <span className="text-xs font-jetbrains text-text-muted opacity-30">
            default: {DEFAULT_PARAMS.occupancy_threshold}
          </span>
          <span className="text-xs font-jetbrains text-text-muted opacity-40">80</span>
        </div>
        <p className="mt-2 text-[10px] font-jetbrains text-text-muted leading-snug">
          Min score for a square to count as occupied. Lower = more sensitive to faint pieces.
        </p>
      </div>

      {/* Calibration panels */}
      {showArucoCalibration && (
        <div className="mb-6 rounded-md border border-border p-4">
          <ArucoCalibration />
        </div>
      )}
      {showManualCalibration && (
        <div className="mb-6 rounded-md border border-border">
          <ManualCalibration imagePath={selectedRawImage} />
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm font-mono" style={{
          background: "oklch(0.3 0.12 25 / 0.2)",
          border: "1px solid oklch(0.6 0.22 25 / 0.3)",
          color: "oklch(0.7 0.22 25)",
        }}>
          {error}
        </div>
      )}

      {/* Pipeline output */}
      {result ? (
        <div className="space-y-4">
          <div
            className="card px-4 py-3"
            style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono text-text-muted">Pipeline result</span>
              <span className="text-xs font-mono" style={{ color: "var(--charm-cyan)" }}>
                {result.total_ms.toFixed(0)} ms
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div>
                <p className="font-mono text-lg font-semibold text-text-bright">{result.stats.occupied}</p>
                <p className="text-text-muted text-xs font-mono">occupied</p>
              </div>
              <div>
                <p className="font-mono text-lg font-semibold" style={{ color: "var(--charm-cyan)" }}>
                  {result.stats.white_pieces}
                </p>
                <p className="text-text-muted text-xs font-mono">white</p>
              </div>
              <div>
                <p className="font-mono text-lg font-semibold" style={{ color: "var(--charm-amber)" }}>
                  {result.stats.black_pieces}
                </p>
                <p className="text-text-muted text-xs font-mono">black</p>
              </div>
            </div>
          </div>
          <DebugImages
            panels={DEBUG_PANELS.map(({ key, label }) => ({
              key,
              label,
              b64: result[key as keyof PipelineResult] as string | undefined,
            }))}
            gridClassName="grid grid-cols-2 sm:grid-cols-4 gap-3"
            imageMaxHeight={200}
          />
        </div>
      ) : (
        <div
          className="card p-10 text-center"
          style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
        >
          <p className="text-text-muted font-mono text-sm">
            Run the pipeline to see the board warp and occupancy debug images.
          </p>
        </div>
      )}
    </div>
  );
}
