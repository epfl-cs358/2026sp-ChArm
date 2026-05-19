"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { api } from "@/lib/api";
import {
  ClassifierTrainResult,
  ColorLabel,
  DEFAULT_PARAMS,
  PipelineParams,
  PipelineResult,
} from "@/lib/types";
import ParamControls from "@/components/ParamControls";
import ChessBoard from "@/components/ChessBoard";
import DebugImages from "@/components/DebugImages";
import ManualCalibration from "@/components/ManualCalibration";
import ArucoCalibration from "@/components/ArucoCalibration";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

type SupervisedLabel = "black" | "white" | "unlabeled";
type ClassLabel = "empty" | "white" | "black";

const CLAHE_TILE_CHOICES = [4, 8, 16] as const;
const RANDOM_SEARCH_TRIALS = 200;
const RANDOM_SEARCH_DELAY_MS = 180;

interface SupervisionScore {
  labeled: number;
  correct: number;
  accuracy: number;
  macroF1: number;
  objective: number;
}

function createUnlabeledGrid(): SupervisedLabel[][] {
  return Array.from({ length: 8 }, () =>
    Array.from({ length: 8 }, () => "unlabeled" as SupervisedLabel),
  );
}

function toBoardLabels(labels: SupervisedLabel[][]): ColorLabel[][] {
  return labels.map((row) =>
    row.map((label) => (label === "unlabeled" ? "empty" : label)),
  );
}

function toLabeledMask(labels: SupervisedLabel[][]): boolean[][] {
  return labels.map((row) => row.map((label) => label !== "unlabeled"));
}

function resultToSupervisedLabels(result: PipelineResult): SupervisedLabel[][] {
  return result.color_labels.map((row) =>
    row.map((label) => (label === "black" || label === "white" ? label : "unlabeled")),
  );
}

function roundToStep(value: number, step: number) {
  return Number((Math.round(value / step) * step).toFixed(2));
}

function randomBetween(min: number, max: number, step: number) {
  return roundToStep(min + Math.random() * (max - min), step);
}

function randomChoice<T>(values: readonly T[]): T {
  return values[Math.floor(Math.random() * values.length)];
}

function randomizeParams(currentParams: PipelineParams): PipelineParams {
  const sharpenStrength = randomBetween(0.0, 0.6, 0.05);
  const cannyLow = randomBetween(10, 80, 5);
  const cannyHighRatio = randomBetween(2.0, 4.0, 0.05);
  const whiteThreshold = randomBetween(150, 220, 1);
  const blackMargin = randomBetween(30, 80, 1);

  return {
    ...DEFAULT_PARAMS,
    auto_detect_board: currentParams.auto_detect_board,
    apply_inner_warp: currentParams.apply_inner_warp,
    board_canny_low: currentParams.board_canny_low,
    board_canny_high: currentParams.board_canny_high,
    board_dilation_iterations: currentParams.board_dilation_iterations,
    board_min_area: currentParams.board_min_area,
    board_max_side_ratio: currentParams.board_max_side_ratio,
    board_min_area_ratio: currentParams.board_min_area_ratio,
    board_max_area_ratio: currentParams.board_max_area_ratio,
    board_min_color_ratio: currentParams.board_min_color_ratio,
    board_padding_ratio: currentParams.board_padding_ratio,
    board_hough_refine: currentParams.board_hough_refine,
    board_hough_canny_low: currentParams.board_hough_canny_low,
    board_hough_canny_high: currentParams.board_hough_canny_high,
    board_hough_threshold: currentParams.board_hough_threshold,
    board_hough_min_line_ratio: currentParams.board_hough_min_line_ratio,
    board_hough_max_line_gap: currentParams.board_hough_max_line_gap,
    board_hough_max_line_distance: currentParams.board_hough_max_line_distance,
    board_hough_min_area_keep: currentParams.board_hough_min_area_keep,
    board_hough_max_area_grow: currentParams.board_hough_max_area_grow,
    board_hough_max_corner_shift_ratio: currentParams.board_hough_max_corner_shift_ratio,
    warp_size: 800,
    saturation_boost: 1.0,
    brightness_boost: 1.0,
    clahe_clip_limit: randomBetween(1.0, 4.0, 0.1),
    clahe_tile_size: randomChoice(CLAHE_TILE_CHOICES),
    sharpen_alpha: roundToStep(1 + sharpenStrength, 0.05),
    sharpen_beta: roundToStep(-sharpenStrength, 0.05),
    canny_low: cannyLow,
    canny_high: roundToStep(cannyLow * cannyHighRatio, 5),
    occupancy_std_weight: randomBetween(0.0, 1.2, 0.05),
    occupancy_threshold: randomBetween(2.0, 50.0, 0.5),
    white_threshold: whiteThreshold,
    black_threshold: whiteThreshold - blackMargin,
  };
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitWhilePaused(isPaused: () => boolean) {
  while (isPaused()) {
    await wait(120);
  }
}

function expectedLabelAt(labels: SupervisedLabel[][], row: number, col: number): ClassLabel {
  const label = labels[row][col];
  return label === "unlabeled" ? "empty" : label;
}

function scoreResult(result: PipelineResult | null, labels: SupervisedLabel[][]): SupervisionScore {
  if (!result) {
    return { labeled: 64, correct: 0, accuracy: 0, macroF1: 0, objective: 0 };
  }

  let correct = 0;
  const classes: ClassLabel[] = ["empty", "white", "black"];
  const counts = Object.fromEntries(
    classes.map((label) => [label, { tp: 0, fp: 0, fn: 0 }]),
  ) as Record<ClassLabel, { tp: number; fp: number; fn: number }>;

  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 8; col += 1) {
      const expected = expectedLabelAt(labels, row, col);
      const predicted = result.color_labels[row]?.[col] ?? "empty";
      const scoredPrediction: ClassLabel =
        predicted === "white" || predicted === "black" ? predicted : "empty";

      if (scoredPrediction === expected) {
        correct += 1;
        counts[expected].tp += 1;
      } else {
        counts[scoredPrediction].fp += 1;
        counts[expected].fn += 1;
      }
    }
  }

  const f1Scores = classes.map((label) => {
    const { tp, fp, fn } = counts[label];
    const denominator = 2 * tp + fp + fn;
    return denominator === 0 ? 1 : (2 * tp) / denominator;
  });
  const macroF1 = f1Scores.reduce((sum, score) => sum + score, 0) / f1Scores.length;

  return {
    labeled: 64,
    correct,
    accuracy: correct / 64,
    macroF1,
    objective: macroF1,
  };
}

function ScoreBadge({ score }: { score: SupervisionScore }) {
  return (
    <div className="rounded-md border border-border px-2 py-1 font-mono text-[10px] text-text-muted">
      <span className="text-cyan-DEFAULT">{Math.round(score.accuracy * 100)}%</span>{" "}
      {score.correct}/64 cells · F1 {score.macroF1.toFixed(2)}
    </div>
  );
}

function ConfusionMatrix({ cm }: { cm: [[number, number], [number, number]] }) {
  const labels = ["white", "black"];
  return (
    <div>
      <p className="text-[10px] font-mono text-text-muted mb-1">Confusion matrix (val)</p>
      <table className="text-[10px] font-mono border-collapse">
        <thead>
          <tr>
            <th className="px-1 text-text-muted font-normal text-left">pred↓ / true→</th>
            {labels.map((l) => (
              <th key={l} className="px-2 py-0.5 text-text-muted font-normal">{l}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cm.map((row, ri) => (
            <tr key={ri}>
              <td className="px-1 text-text-muted">{labels[ri]}</td>
              {row.map((val, ci) => (
                <td
                  key={ci}
                  className="px-2 py-0.5 text-center font-semibold"
                  style={{ color: ri === ci ? "var(--charm-cyan)" : "var(--charm-amber)" }}
                >
                  {val}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClassifierPanel({
  retrainResult,
  retraining,
  annotationStats,
  onRetrain,
}: {
  retrainResult: ClassifierTrainResult | null;
  retraining: boolean;
  annotationStats: { count: number; n_white: number; n_black: number; n_scenes: number } | null;
  onRetrain: () => void;
}) {
  return (
    <div
      className="card flex flex-col h-full"
      style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
    >
      <div className="px-3 pt-3 pb-1 border-b border-border mb-2">
        <p className="text-xs font-jetbrains font-semibold uppercase tracking-widest text-[oklch(0.65_0.2_50)]">
          Color Classifier
        </p>
      </div>
      <div className="px-3 pb-3 flex-1 flex flex-col gap-2">
        <button
          onClick={onRetrain}
          disabled={retraining}
          className="btn-cyan px-2 py-1 rounded-md text-[10px] font-mono disabled:opacity-50 w-full"
        >
          {retraining ? "Training..." : "Retrain classifier"}
        </button>

        {annotationStats && (
          <div className="text-[10px] font-mono text-text-muted space-y-0.5">
            <p>
              <span className="text-text">{annotationStats.count}</span> images ·{" "}
              <span className="text-text">{annotationStats.n_scenes}</span> scenes
            </p>
            <p>
              <span className="text-cyan-DEFAULT">{annotationStats.n_white}</span> white ·{" "}
              <span className="text-amber-DEFAULT">{annotationStats.n_black}</span> black samples
            </p>
          </div>
        )}

        {retrainResult && (
          <div className="space-y-2 text-[10px] font-mono">
            <div className="space-y-0.5">
              <p className="text-text-muted">
                k = <span className="text-cyan-DEFAULT font-semibold">{retrainResult.best_k}</span>{" "}
                (auto-selected)
              </p>
              <p className="text-text-muted">
                CV F1{" "}
                <span className="text-text">
                  {retrainResult.chosen_cv_mean_f1.toFixed(3)} ± {retrainResult.chosen_cv_std_f1.toFixed(3)}
                </span>
              </p>
              {retrainResult.val_f1 !== null && (
                <p className="text-text-muted">
                  Val F1{" "}
                  <span
                    className="font-semibold"
                    style={{
                      color:
                        retrainResult.val_f1 >= 0.9
                          ? "var(--charm-cyan)"
                          : retrainResult.val_f1 >= 0.75
                          ? "var(--charm-amber)"
                          : "oklch(0.65 0.22 25)",
                    }}
                  >
                    {retrainResult.val_f1.toFixed(3)}
                  </span>
                </p>
              )}
              <p className="text-text-muted">
                Train{" "}
                <span className="text-text">{retrainResult.n_train}</span> · Val{" "}
                <span className="text-text">{retrainResult.n_val}</span>
              </p>
            </div>

            {retrainResult.val_confusion_matrix && (
              <ConfusionMatrix cm={retrainResult.val_confusion_matrix} />
            )}

            {retrainResult.warnings.length > 0 && (
              <div className="space-y-0.5">
                {retrainResult.warnings.map((w, i) => (
                  <p key={i} className="text-[oklch(0.65_0.22_50)]">
                    ⚠ {w}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SupervisionPanel({
  labels,
  result,
  bestScore,
  searching,
  paused,
  savedStatus,
  onClear,
  onSetDetected,
  onPauseToggle,
  onSaveParams,
  onSaveSnapshot,
  onLoadParams,
  onSearch,
}: {
  labels: SupervisedLabel[][];
  result: PipelineResult | null;
  bestScore: SupervisionScore | null;
  searching: boolean;
  paused: boolean;
  savedStatus: string | null;
  onClear: () => void;
  onSetDetected: () => void;
  onPauseToggle: () => void;
  onSaveParams: () => void;
  onSaveSnapshot: () => void;
  onLoadParams: () => void;
  onSearch: () => void;
}) {
  const score = scoreResult(result, labels);
  const compactButtonClass =
    "px-2 py-1 rounded-md border border-border text-[10px] font-mono text-text-muted hover:text-text hover:border-border-bright disabled:opacity-50";

  return (
    <div
      className="card flex flex-col h-full"
      style={{
        background: "var(--charm-card)",
        borderColor: "var(--charm-border)",
      }}
    >
      <div className="px-3 pt-3 pb-1 border-b border-border mb-2">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-jetbrains font-semibold uppercase tracking-widest text-[oklch(0.65_0.2_310)]">
            Supervised Labels
          </p>
          <ScoreBadge score={score} />
        </div>
      </div>

      <div className="px-3 pb-3 flex-1 flex flex-col gap-2">
        <div className="grid grid-cols-1 gap-1.5">
          <button
            onClick={onSetDetected}
            disabled={result === null || searching}
            className={`${compactButtonClass} w-full`}
          >
            Detected → Expected
          </button>
          <button
            onClick={onSearch}
            disabled={searching}
            className="btn-cyan px-2 py-1 rounded-md text-[10px] font-mono disabled:opacity-50 w-full"
          >
            {searching ? "Searching..." : `Auto tune x${RANDOM_SEARCH_TRIALS}`}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-1.5">
          <button
            onClick={onSaveParams}
            disabled={result === null || searching}
            className={`${compactButtonClass} w-full`}
          >
            Save JSON
          </button>
          <button
            onClick={onSaveSnapshot}
            disabled={result === null || searching}
            className={`${compactButtonClass} w-full`}
          >
            Save Images
          </button>
          <button
            onClick={onLoadParams}
            disabled={searching}
            className={`${compactButtonClass} w-full`}
          >
            Load JSON
          </button>
        </div>

        <div className="grid grid-cols-1 gap-1.5">
          <button
            onClick={onPauseToggle}
            disabled={!searching}
            className={`${compactButtonClass} w-full`}
          >
            {paused ? "Resume" : "Pause"}
          </button>
          <button
            onClick={onClear}
            className={`${compactButtonClass} w-full`}
          >
            Clear labels
          </button>
        </div>

        {(bestScore && bestScore.labeled > 0) || savedStatus ? (
          <div className="mt-auto pt-2 text-[10px] font-mono text-center flex flex-col gap-1">
            {bestScore && bestScore.labeled > 0 && (
              <span className="text-amber-DEFAULT">
                best F1 {bestScore.macroF1.toFixed(2)}
              </span>
            )}
            {savedStatus && <span className="text-text-muted truncate">{savedStatus}</span>}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ResultPanel({
  result,
  label,
  supervisedLabels,
  onCellAnnotate,
  showDebugImages = true,
  showFinalDetected = true,
}: {
  result: PipelineResult;
  label: string;
  supervisedLabels?: SupervisedLabel[][];
  onCellAnnotate?: (row: number, col: number, color: "black" | "white" | "clear") => void;
  showDebugImages?: boolean;
  showFinalDetected?: boolean;
}) {
  return (
    <div className="space-y-4">
      <div className="card px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono text-text-muted">{label}</span>
          <span className="text-xs font-mono text-cyan-DEFAULT">{result.total_ms.toFixed(0)} ms</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-text-bright font-mono text-lg font-semibold">{result.stats.occupied}</p>
            <p className="text-text-muted text-xs font-mono">occupied</p>
          </div>
          <div>
            <p className="text-cyan-DEFAULT font-mono text-lg font-semibold">{result.stats.white_pieces}</p>
            <p className="text-text-muted text-xs font-mono">white</p>
          </div>
          <div>
            <p className="text-amber-DEFAULT font-mono text-lg font-semibold">{result.stats.black_pieces}</p>
            <p className="text-text-muted text-xs font-mono">black</p>
          </div>
        </div>
        {result.stats.unknown_pieces > 0 && (
          <p className="text-purple-400 text-xs font-mono mt-2 text-center">
            {result.stats.unknown_pieces} unknown piece{result.stats.unknown_pieces > 1 ? "s" : ""}
          </p>
        )}
      </div>

      {showDebugImages && (
        <DebugImages
          panels={DEBUG_PANELS.map(({ key, label: l }) => ({
            key,
            label: l,
            b64: result[key as keyof PipelineResult] as string | undefined,
          }))}
          gridClassName="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3"
          imageMaxHeight={180}
        />
      )}

      {showFinalDetected && (
        <div className="card p-5 w-fit mx-auto text-center">
          <h2 className="text-sm font-mono font-semibold text-text-bright mb-4">Final Detected</h2>
          <ChessBoard
            colorLabels={result.color_labels}
            occupancyScores={result.occupancy_scores}
            brightnessScores={result.brightness_scores}
            highlightUnknown
            annotationLabels={supervisedLabels ? toBoardLabels(supervisedLabels) : undefined}
            labeledCells={supervisedLabels ? toLabeledMask(supervisedLabels) : undefined}
            onCellAnnotate={onCellAnnotate}
          />
          {onCellAnnotate && (
            <p className="mt-3 text-xs font-mono text-text-muted">
              Left click marks black. Right click marks white. Shift/alt click clears a label.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function FinalDetectedPanel({
  result,
  supervisedLabels,
  onCellAnnotate,
}: {
  result: PipelineResult;
  supervisedLabels: SupervisedLabel[][];
  onCellAnnotate: (row: number, col: number, color: "black" | "white" | "clear") => void;
}) {
  return (
    <div className="card p-4 text-center">
      <h2 className="mb-3 text-sm font-mono font-semibold text-text-bright">
        Final Detected
      </h2>
      <div className="flex justify-center">
        <ChessBoard
          colorLabels={result.color_labels}
          occupancyScores={result.occupancy_scores}
          brightnessScores={result.brightness_scores}
          highlightUnknown
          annotationLabels={toBoardLabels(supervisedLabels)}
          labeledCells={toLabeledMask(supervisedLabels)}
          onCellAnnotate={onCellAnnotate}
        />
      </div>
      <p className="mt-2 text-xs font-mono text-text-muted">
        Left click black. Right click white. Shift/alt click clears.
      </p>
    </div>
  );
}

function LivePhotosPanel({ result }: { result: PipelineResult | null }) {
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-mono font-semibold text-text-bright">Live Images</h2>
        {result && (
          <span className="text-xs font-mono text-cyan-DEFAULT">
            {result.total_ms.toFixed(0)} ms
          </span>
        )}
      </div>
      {result ? (
        <DebugImages
          panels={DEBUG_PANELS.map(({ key, label: l }) => ({
            key,
            label: l,
            b64: result[key as keyof PipelineResult] as string | undefined,
          }))}
          gridClassName="grid grid-cols-2 gap-3"
          imageMaxHeight={210}
        />
      ) : (
        <div className="h-64 flex items-center justify-center text-text-muted font-mono text-sm">
          Run the pipeline to see preprocessing, grid, occupancy and piece color images.
        </div>
      )}
    </div>
  );
}

function ConfigColumn({
  label,
  params,
  setParams,
  result,
  loading,
  run,
  runDisabled,
  onOpenManualCalibration,
}: {
  label: string;
  params: PipelineParams;
  setParams: (params: PipelineParams) => void;
  result: PipelineResult | null;
  loading: boolean;
  run: () => void;
  runDisabled: boolean;
  onOpenManualCalibration?: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono font-semibold text-text-bright">Config {label}</h2>
        <button
          onClick={run}
          disabled={runDisabled}
          className="btn-cyan px-4 py-2 rounded-md text-sm font-mono flex items-center gap-2"
        >
          {loading ? (
            <span className="w-3 h-3 border-2 border-cyan-DEFAULT border-t-transparent rounded-full animate-spin" />
          ) : "▶"} Pipeline {label}
        </button>
      </div>
      <ParamControls params={params} onChange={setParams} onOpenManualCalibration={onOpenManualCalibration} />
      {result && <ResultPanel result={result} label={`Result ${label}`} />}
    </div>
  );
}

function ResultStatsPanel({ result }: { result: PipelineResult }) {
  return (
    <ResultPanel
      result={result}
      label="Result"
      showDebugImages={false}
      showFinalDetected={false}
    />
  );
}

export default function LabPage() {
  const [paramsA, setParamsA] = useState<PipelineParams>(() => ({ ...DEFAULT_PARAMS }));
  const [paramsB, setParamsB] = useState<PipelineParams>(() => ({ ...DEFAULT_PARAMS }));
  const [resultA, setResultA] = useState<PipelineResult | null>(null);
  const [resultB, setResultB] = useState<PipelineResult | null>(null);
  const [resultAParams, setResultAParams] = useState<PipelineParams>(() => ({ ...DEFAULT_PARAMS }));
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [cameraPipelineLoading, setCameraPipelineLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchPaused, setSearchPaused] = useState(false);
  const [savedStatus, setSavedStatus] = useState<string | null>(null);
  const [supervisedLabels, setSupervisedLabels] = useState<SupervisedLabel[][]>(createUnlabeledGrid);
  const [bestScore, setBestScore] = useState<SupervisionScore | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<"raw" | "upload">("raw");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [rawImages, setRawImages] = useState<{ name: string; path: string }[]>([]);
  const [selectedRawImage, setSelectedRawImage] = useState<string | null>(null);
  const [retraining, setRetraining] = useState(false);
  const [retrainResult, setRetrainResult] = useState<ClassifierTrainResult | null>(null);
  const [retrainError, setRetrainError] = useState<string | null>(null);
  const [annotationStats, setAnnotationStats] = useState<{
    count: number; n_white: number; n_black: number; n_scenes: number;
  } | null>(null);
  const [showManualCalibration, setShowManualCalibration] = useState(false);
  const [showArucoCalibration, setShowArucoCalibration] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const runASeq = useRef(0);
  const runBSeq = useRef(0);
  const skipAutoRunRef = useRef(false);
  const searchPausedRef = useRef(false);

  useEffect(() => {
    searchPausedRef.current = searchPaused;
  }, [searchPaused]);

  // Load annotation stats on mount
  useEffect(() => {
    api.getAnnotations()
      .then((r) => setAnnotationStats({ count: r.count, n_white: r.n_white, n_black: r.n_black, n_scenes: r.n_scenes }))
      .catch(() => null);
  }, []);

  // Load available raw images on mount
  useEffect(() => {
    api.listImages()
      .then((r) => {
        setRawImages(r.images);
        if (r.images.length > 0 && selectedRawImage === null) {
          setSelectedRawImage(r.images[0].path);
        }
      })
      .catch(() => null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runWithParams = useCallback(async (params: PipelineParams) => {
    if (source === "upload" && uploadedFile) {
      return api.uploadAndRun(uploadedFile, params);
    }
    const p = selectedRawImage ? { ...params, image_path: selectedRawImage } : params;
    return api.runPipeline(p);
  }, [source, uploadedFile, selectedRawImage]);

  const runA = useCallback(async () => {
    const requestId = runASeq.current + 1;
    runASeq.current = requestId;
    const activeParams = { ...paramsA };
    setLoadingA(true);
    setError(null);
    try {
      const r = await runWithParams(activeParams);
      if (runASeq.current === requestId) {
        setResultA(r);
        setResultAParams(activeParams);
      }
    } catch (e: unknown) {
      if (runASeq.current === requestId) {
        setError(e instanceof Error ? e.message : "Run A failed");
      }
    } finally {
      if (runASeq.current === requestId) {
        setLoadingA(false);
      }
    }
  }, [paramsA, runWithParams]);

  const runB = useCallback(async () => {
    const requestId = runBSeq.current + 1;
    runBSeq.current = requestId;
    const activeParams = { ...paramsB };
    setLoadingB(true);
    setError(null);
    try {
      const r = await runWithParams(activeParams);
      if (runBSeq.current === requestId) {
        setResultB(r);
      }
    } catch (e: unknown) {
      if (runBSeq.current === requestId) {
        setError(e instanceof Error ? e.message : "Run B failed");
      }
    } finally {
      if (runBSeq.current === requestId) {
        setLoadingB(false);
      }
    }
  }, [paramsB, runWithParams]);

  const runCameraPipeline = useCallback(async () => {
    if (cameraPipelineLoading || loadingA || loadingB || searching) return;

    const requestAId = runASeq.current + 1;
    const requestBId = runBSeq.current + 1;
    runASeq.current = requestAId;
    if (compareMode) {
      runBSeq.current = requestBId;
    }

    setCameraPipelineLoading(true);
    setLoadingA(true);
    if (compareMode) setLoadingB(true);
    setError(null);

    try {
      const capture = await api.captureFromCamera();
      setSource("raw");
      setUploadedFile(null);
      skipAutoRunRef.current = true;
      setSelectedRawImage(capture.path);
      setRawImages((current) => {
        if (current.some((img) => img.path === capture.path)) return current;
        return [{ name: capture.path.split("/").pop() ?? "latest capture", path: capture.path }, ...current];
      });

      const [resultAResponse, resultBResponse] = await Promise.all([
        api.runPipeline({ ...paramsA, image_path: capture.path }),
        compareMode ? api.runPipeline({ ...paramsB, image_path: capture.path }) : Promise.resolve(null),
      ]);

      if (runASeq.current === requestAId) {
        setResultA(resultAResponse);
        setResultAParams({ ...paramsA, image_path: capture.path });
      }
      if (compareMode && runBSeq.current === requestBId && resultBResponse) {
        setResultB(resultBResponse);
      }
    } catch (e: unknown) {
      if (runASeq.current === requestAId) {
        setError(e instanceof Error ? e.message : "Camera pipeline failed");
      }
    } finally {
      if (runASeq.current === requestAId) {
        setLoadingA(false);
      }
      if (compareMode && runBSeq.current === requestBId) {
        setLoadingB(false);
      }
      setCameraPipelineLoading(false);
    }
  }, [cameraPipelineLoading, compareMode, loadingA, loadingB, paramsA, paramsB, searching]);

  const setSupervisedLabel = useCallback((row: number, col: number, color: "black" | "white" | "clear") => {
    setSupervisedLabels((current) =>
      current.map((r, ri) =>
        r.map((label, ci) => {
          if (ri !== row || ci !== col) return label;
          return color === "clear" ? "unlabeled" : color;
        }),
      ),
    );
  }, []);

  const randomSearch = useCallback(async () => {
    const labelSnapshot = supervisedLabels.map((row) => [...row]);
    const initialScore = scoreResult(resultA, labelSnapshot);

    setSearching(true);
    setSearchPaused(false);
    setError(null);

    let best = {
      score: initialScore,
      params: resultAParams,
      result: resultA,
    };

    try {
      for (let trial = 0; trial < RANDOM_SEARCH_TRIALS; trial += 1) {
        await waitWhilePaused(() => searchPausedRef.current);

        const candidateParams = randomizeParams(paramsA);
        setParamsA(candidateParams);
        await wait(RANDOM_SEARCH_DELAY_MS);
        await waitWhilePaused(() => searchPausedRef.current);

        const candidateResult = await runWithParams(candidateParams);
        const candidateScore = scoreResult(candidateResult, labelSnapshot);
        setResultA(candidateResult);
        setResultAParams(candidateParams);
        setBestScore((current) =>
          !current || candidateScore.accuracy > current.accuracy ? candidateScore : current,
        );

        if (candidateScore.objective > best.score.objective) {
          best = {
            score: candidateScore,
            params: candidateParams,
            result: candidateResult,
          };
        }

        if (candidateScore.accuracy === 1) {
          best = {
            score: candidateScore,
            params: candidateParams,
            result: candidateResult,
          };
          break;
        }
      }

      setBestScore(best.score);
      setParamsA(best.params);
      setResultA(best.result);
      setResultAParams(best.params);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Random search failed");
    } finally {
      setSearching(false);
      setSearchPaused(false);
    }
  }, [paramsA, resultA, resultAParams, runWithParams, supervisedLabels]);

  const saveCurrentParams = useCallback(async () => {
    try {
      const score = scoreResult(resultA, supervisedLabels);
      const response = await api.saveParams({
        params: paramsA,
        score,
        labels: toBoardLabels(supervisedLabels),
        source_image: resultA?.image_path,
      });
      setSavedStatus(`Saved JSON: ${response.path} (${Math.round(score.accuracy * 100)}%, F1 ${score.macroF1.toFixed(2)})`);
      // Refresh annotation stats after saving (save_params may have added an annotation)
      api.getAnnotations()
        .then((r) => setAnnotationStats({ count: r.count, n_white: r.n_white, n_black: r.n_black, n_scenes: r.n_scenes }))
        .catch(() => null);
    } catch {
      setSavedStatus("Could not save params JSON");
    }
  }, [paramsA, resultA, supervisedLabels]);

  const saveCurrentSnapshot = useCallback(async () => {
    if (!resultA) return;
    try {
      const response = await api.savePipelineSnapshot({
        params: resultAParams,
        images: {
          original: resultA.original,
          board_edges_debug: resultA.board_edges_debug,
          first_warp: resultA.first_warp,
          refined_warp: resultA.refined_warp,
          preprocessed: resultA.preprocessed,
          grid_debug: resultA.grid_debug,
          occupancy_debug: resultA.occupancy_debug,
          piece_color_debug: resultA.piece_color_debug,
        },
        result: {
          board_detection_mode: resultA.board_detection_mode,
          warp_error: resultA.warp_error,
          occupancy_matrix: resultA.occupancy_matrix,
          white_bitmap: resultA.white_bitmap,
          black_bitmap: resultA.black_bitmap,
          brightness_scores: resultA.brightness_scores,
          color_labels: resultA.color_labels,
          stats: resultA.stats,
          timings: resultA.timings,
        },
        labels: toBoardLabels(supervisedLabels),
        source_image: resultA.image_path,
      });
      setSavedStatus(`Saved images: ${response.refined_warp_path ?? response.path}`);
    } catch {
      setSavedStatus("Could not save images");
    }
  }, [resultA, resultAParams, supervisedLabels]);

  const loadSavedParamsJson = useCallback(async () => {
    try {
      const response = await api.getSavedParams();
      if (!response.exists || !response.data?.params) {
        setSavedStatus("No saved JSON found");
        return;
      }
      const loaded = { ...DEFAULT_PARAMS, ...response.data.params };
      setParamsA(loaded);
      setResultAParams(loaded);
      if (response.data.labels) {
        setSupervisedLabels(
          response.data.labels.map((row) =>
            row.map((label) => (label === "black" || label === "white" ? label : "unlabeled")),
          ),
        );
      }
      setSavedStatus(`Loaded JSON: ${response.path}`);
    } catch {
      setSavedStatus("Could not load params JSON");
    }
  }, []);

  const handleRetrain = useCallback(async () => {
    setRetraining(true);
    setRetrainError(null);
    try {
      const result = await api.retrainClassifier();
      setRetrainResult(result);
    } catch (e: unknown) {
      setRetrainError(e instanceof Error ? e.message : "Retrain failed");
    } finally {
      setRetraining(false);
    }
  }, []);

  useEffect(() => {
    if (skipAutoRunRef.current) {
      skipAutoRunRef.current = false;
      return;
    }

    if (searching) {
      return;
    }

    if (source === "upload" && !uploadedFile) {
      return;
    }

    if (source === "raw" && selectedRawImage === null) {
      return;
    }

    const timeout = window.setTimeout(() => {
      void runA();
      if (compareMode) {
        void runB();
      }
    }, 350);

    return () => window.clearTimeout(timeout);
  }, [runA, runB, compareMode, source, uploadedFile, selectedRawImage, searching]);

  return (
    <div className="p-6 max-w-screen-2xl mx-auto">
      <div className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-mono font-semibold text-text-bright">Computer Vision</h1>
          <p className="text-text-muted text-sm mt-1">Fine-tune CV parameters and compare results</p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={runCameraPipeline}
            disabled={cameraPipelineLoading || loadingA || loadingB || searching}
            className="btn-cyan px-4 py-2 rounded-md text-sm font-mono font-semibold disabled:opacity-50"
          >
            {cameraPipelineLoading ? "Capturing..." : "▶"} Pipeline
          </button>
          <button
            type="button"
            onClick={() => setShowManualCalibration((current) => !current)}
            className="px-3 py-2 text-xs font-mono rounded-md border border-border text-text-muted hover:text-text hover:border-border-bright"
          >
            Do manual calibration on the 4 corners
          </button>
          <button
            type="button"
            onClick={() => setShowArucoCalibration((current) => !current)}
            className="px-3 py-2 text-xs font-mono rounded-md border border-border text-text-muted hover:text-text hover:border-border-bright"
          >
            ArUco calibration (auto, 4 markers)
          </button>
          <div className="flex rounded-md overflow-hidden border border-border">
            {(["raw", "upload"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSource(s)}
                className={`px-3 py-2 text-xs font-mono transition-colors ${
                  source === s ? "bg-cyan-glow text-cyan-DEFAULT" : "text-text-muted hover:text-text"
                }`}
              >
                {s === "raw" ? "Raw image" : "Upload"}
              </button>
            ))}
          </div>

          {source === "raw" && (
            rawImages.length > 0 ? (
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
            )
          )}

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
            onClick={() => setCompareMode(!compareMode)}
            className={`px-4 py-2 rounded-md text-sm font-mono border transition-all ${
              compareMode
                ? "border-amber-DEFAULT/40 text-amber-DEFAULT bg-amber-glow"
                : "border-border text-text-muted hover:border-border-bright hover:text-text"
            }`}
          >
            ⊞ A/B Compare
          </button>
        </div>
      </div>

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
        <div className="mb-4 px-4 py-3 bg-red-dim/20 border border-red-DEFAULT/30 rounded-md text-sm font-mono text-red-DEFAULT">
          {error}
        </div>
      )}

      {retrainError && (
        <div className="mb-4 px-4 py-3 bg-red-dim/20 border border-red-DEFAULT/30 rounded-md text-sm font-mono text-red-DEFAULT">
          Retrain: {retrainError}
        </div>
      )}

      {compareMode ? (
        <div className="grid grid-cols-2 gap-6">
          <ConfigColumn
            label="A"
            params={paramsA}
            setParams={setParamsA}
            result={resultA}
            loading={loadingA}
            run={runA}
            runDisabled={loadingA || (source === "upload" && !uploadedFile)}
          />
          <ConfigColumn
            label="B"
            params={paramsB}
            setParams={setParamsB}
            result={resultB}
            loading={loadingB}
            run={runB}
            runDisabled={loadingB || (source === "upload" && !uploadedFile)}
          />
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.15fr)_minmax(420px,0.85fr)] gap-6 items-start">
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-mono font-semibold text-text-bright">Parameters & Labels</h2>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setParamsA({ ...DEFAULT_PARAMS, image_path: paramsA.image_path })}
                    disabled={searching}
                    className="px-4 py-2 rounded-md border border-border text-sm font-mono font-semibold text-text-muted hover:text-text hover:border-border-bright disabled:opacity-50"
                  >
                    Reset defaults
                  </button>
                  <button
                    onClick={runA}
                    disabled={loadingA || (source === "upload" && !uploadedFile)}
                    className="btn-cyan px-4 py-2 rounded-md text-sm font-mono font-semibold flex items-center gap-2"
                  >
                    {loadingA ? (
                      <span className="w-3 h-3 border-2 border-cyan-DEFAULT border-t-transparent rounded-full animate-spin" />
                    ) : "▶"} Pipeline
                  </button>
                </div>
              </div>
              <ParamControls params={paramsA} onChange={setParamsA} onOpenManualCalibration={() => setShowManualCalibration(true)}>
                <SupervisionPanel
                  labels={supervisedLabels}
                  result={resultA}
                  bestScore={bestScore}
                  searching={searching}
                  paused={searchPaused}
                  savedStatus={savedStatus}
                  onClear={() => {
                    setSupervisedLabels(createUnlabeledGrid());
                    setBestScore(null);
                  }}
                  onSetDetected={() => {
                    if (!resultA) return;
                    setSupervisedLabels(resultToSupervisedLabels(resultA));
                    setBestScore(null);
                  }}
                  onPauseToggle={() => setSearchPaused((current) => !current)}
                  onSaveParams={saveCurrentParams}
                  onSaveSnapshot={saveCurrentSnapshot}
                  onLoadParams={loadSavedParamsJson}
                  onSearch={randomSearch}
                />
                <ClassifierPanel
                  retrainResult={retrainResult}
                  retraining={retraining}
                  annotationStats={annotationStats}
                  onRetrain={handleRetrain}
                />
              </ParamControls>
              {resultA ? (
                <FinalDetectedPanel
                  result={resultA}
                  supervisedLabels={supervisedLabels}
                  onCellAnnotate={setSupervisedLabel}
                />
              ) : (
                <div className="card p-10 text-center">
                  <p className="text-text-muted font-mono text-sm">
                    Final Detected will appear after the first live run.
                  </p>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <LivePhotosPanel result={resultA} />
              {resultA ? (
                <ResultStatsPanel result={resultA} />
              ) : (
                <div className="card p-10 text-center">
                  <p className="text-text-muted font-mono text-sm">
                    Result stats will appear after the first live run.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
