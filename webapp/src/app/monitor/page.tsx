"use client";

import { useState, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import { createDemoPipelineResult } from "@/lib/demo";
import { DEFAULT_PARAMS, PipelineResult, PipelineParams } from "@/lib/types";
import DebugImages from "@/components/DebugImages";
import ChessBoard from "@/components/ChessBoard";

const PIPELINE_STEPS = [
  { key: "original", label: "1. Raw Input" },
  { key: "first_warp", label: "2. First Warp" },
  { key: "refined_warp", label: "3. Refined Warp" },
  { key: "preprocessed", label: "4. Preprocessed" },
  { key: "grid_debug", label: "5. Grid Detection" },
  { key: "occupancy_debug", label: "6. Occupancy" },
  { key: "piece_color_debug", label: "7. Piece Colors" },
] as const;

export default function MonitorPage() {
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<"demo" | "latest" | "upload">("latest");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = useCallback(async (params: PipelineParams = DEFAULT_PARAMS) => {
    setLoading(true);
    setError(null);
    try {
      let r: PipelineResult;
      if (source === "demo") {
        r = createDemoPipelineResult(params);
      } else if (source === "upload" && uploadedFile) {
        r = await api.uploadAndRun(uploadedFile, params);
      } else {
        r = await api.runPipeline(params);
      }
      setResult(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
    } finally {
      setLoading(false);
    }
  }, [source, uploadedFile]);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-mono font-semibold text-text-bright">Pipeline Monitor</h1>
          <p className="text-text-muted text-sm mt-1">Full debug view of each pipeline step</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex rounded-md overflow-hidden border border-border">
            {(["demo", "latest", "upload"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSource(s)}
                className={`px-3 py-2 text-xs font-mono transition-colors ${
                  source === s
                    ? "bg-cyan-glow text-cyan-DEFAULT"
                    : "text-text-muted hover:text-text"
                }`}
              >
                {s === "demo" ? "Demo" : s === "latest" ? "latest_raw.jpg" : "Upload"}
              </button>
            ))}
          </div>

          {source === "upload" && (
            <>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => setUploadedFile(e.target.files?.[0] ?? null)}
              />
              <button
                onClick={() => fileRef.current?.click()}
                className="px-3 py-2 text-xs font-mono rounded-md border border-border text-text-muted hover:text-text hover:border-border-bright"
              >
                {uploadedFile ? uploadedFile.name : "Choose file..."}
              </button>
            </>
          )}

          <button
            onClick={() => run()}
            disabled={loading || (source === "upload" && !uploadedFile)}
            className="btn-cyan px-5 py-2 rounded-md text-sm font-mono font-semibold flex items-center gap-2"
          >
            {loading ? (
              <>
                <span className="w-3 h-3 border-2 border-cyan-DEFAULT border-t-transparent rounded-full animate-spin" />
                Running...
              </>
            ) : (
              "▶ Run"
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-dim/20 border border-red-DEFAULT/30 rounded-md text-sm font-mono text-red-DEFAULT">
          {error}
        </div>
      )}

      {result?.warp_error && (
        <div className="mb-4 px-4 py-3 bg-amber-glow border border-amber-DEFAULT/30 rounded-md text-xs font-mono text-amber-DEFAULT">
          ⚠ Warp fallback: {result.warp_error}
        </div>
      )}

      {result ? (
        <div className="animate-fade-in space-y-6">
          <div className="grid grid-cols-4 gap-3">
            <div className="card px-4 py-3 text-center">
              <p className="text-xs text-text-muted font-mono">Total</p>
              <p className="text-xl font-mono text-cyan-DEFAULT font-semibold">{result.total_ms.toFixed(0)} ms</p>
            </div>
            <div className="card px-4 py-3 text-center">
              <p className="text-xs text-text-muted font-mono">Occupied</p>
              <p className="text-xl font-mono text-text-bright font-semibold">{result.stats.occupied}</p>
            </div>
            <div className="card px-4 py-3 text-center">
              <p className="text-xs text-text-muted font-mono">White</p>
              <p className="text-xl font-mono text-cyan-DEFAULT font-semibold">{result.stats.white_pieces}</p>
            </div>
            <div className="card px-4 py-3 text-center">
              <p className="text-xs text-text-muted font-mono">Black</p>
              <p className="text-xl font-mono text-amber-DEFAULT font-semibold">{result.stats.black_pieces}</p>
            </div>
          </div>

          <div>
            <h2 className="text-sm font-mono font-semibold text-text-bright mb-3">Pipeline Steps</h2>
            <DebugImages
              panels={PIPELINE_STEPS.map(({ key, label }) => ({
                key,
                label,
                b64: result[key as keyof PipelineResult] as string | undefined,
              }))}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card p-5">
              <h2 className="text-sm font-mono font-semibold text-text-bright mb-4">Detected Board State</h2>
              <ChessBoard
                colorLabels={result.color_labels}
                occupancyScores={result.occupancy_scores}
                brightnessScores={result.brightness_scores}
                highlightUnknown
              />
            </div>

            <div className="card p-5">
              <h2 className="text-sm font-mono font-semibold text-text-bright mb-4">Occupancy Score Heatmap</h2>
              <div className="inline-block">
                {result.occupancy_scores.map((row, ri) => (
                  <div key={ri} className="flex gap-0.5 mb-0.5">
                    {row.map((score, ci) => {
                      const occ = result.occupancy_matrix[ri][ci];
                      const norm = Math.min(1, score / 10);
                      const bg = occ
                        ? `rgba(0,212,255,${0.2 + norm * 0.6})`
                        : `rgba(90,112,144,${norm * 0.3})`;
                      return (
                        <div
                          key={ci}
                          className="w-9 h-9 rounded-sm flex items-center justify-center relative group"
                          style={{ background: bg, border: "1px solid rgba(26,37,64,0.5)" }}
                        >
                          <span className="text-xs font-mono" style={{ fontSize: 8, color: occ ? "#00d4ff" : "#5a7090" }}>
                            {score.toFixed(1)}
                          </span>
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-10">
                            <div className="bg-card border border-border rounded px-2 py-1 text-xs font-mono whitespace-nowrap">
                              r{ri}c{ci}: <span className="text-cyan-DEFAULT">{score.toFixed(3)}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}
                <div className="mt-2 flex items-center gap-3 text-xs font-mono text-text-muted">
                  <span>score {'>'} <span className="text-cyan-DEFAULT">{DEFAULT_PARAMS.occupancy_threshold}</span> = occupied</span>
                </div>
              </div>
            </div>
          </div>

          <div className="text-xs font-mono text-text-muted text-right">
            {result.image_path} · {new Date(result.timestamp * 1000).toLocaleTimeString()}
          </div>
        </div>
      ) : (
        <div className="card p-16 text-center">
          <div className="text-4xl mb-4 opacity-30">◉</div>
          <p className="text-text-muted font-mono text-sm">Click Run to process latest_raw.jpg through the pipeline</p>
        </div>
      )}
    </div>
  );
}
