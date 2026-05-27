"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  LabelAccuracyReport,
  LabelDatasetMeta,
  LabelSettings,
} from "@/lib/api";
import { DEFAULT_PARAMS } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import ArucoCalibration from "@/components/ArucoCalibration";
import ManualCalibration from "@/components/ManualCalibration";
import BulkPaintBoard, { BulkLabel } from "@/components/BulkPaintBoard";
import { imageSrc } from "@/lib/image";

const LABELING_PARAMS = { ...DEFAULT_PARAMS, apply_inner_warp: true };

const STEPS = [
  { id: 1 as const, label: "Setup" },
  { id: 2 as const, label: "Calibration" },
  { id: 3 as const, label: "Empty board" },
  { id: 4 as const, label: "White pieces" },
  { id: 5 as const, label: "Black pieces" },
  { id: 6 as const, label: "Finish" },
];
type StepId = 1 | 2 | 3 | 4 | 5 | 6;

const ALL_SQUARES: string[] = (() => {
  const out: string[] = [];
  for (let rank = 1; rank <= 8; rank++)
    for (const file of "abcdefgh") out.push(`${file}${rank}`);
  return out;
})();

const PIECE_TYPES = ["pawn", "knight", "bishop", "rook", "queen", "king"] as const;

const DEFAULT_SETTINGS: LabelSettings = {
  frames_per_square: 5,
  settle_ms: 600,
  source_square: "h8",
  piece_type: "pawn",
  lighting_note: "",
};

type SweepMode = "arm" | "manual" | "bulk";
type SweepPhase = "idle" | "moving" | "homing" | "waiting" | "capturing";
type RunState = "idle" | "running" | "paused" | "aborted" | "done";

export default function LabelingWizardPage() {
  const [step, setStep] = useState<StepId>(1);
  const [datasets, setDatasets] = useState<LabelDatasetMeta[]>([]);
  const [activeName, setActiveName] = useState<string | null>(null);
  const [meta, setMeta] = useState<LabelDatasetMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // ── Step 1 fields ──────────────────────────────────────────────────────────
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [newName, setNewName] = useState("");
  const [chosenExisting, setChosenExisting] = useState<string>("");
  const [draftSource, setDraftSource] = useState("h8");
  const [draftPiece, setDraftPiece] = useState("pawn");
  const [draftLighting, setDraftLighting] = useState("");
  const [draftFrames, setDraftFrames] = useState(5);
  const [draftSettle, setDraftSettle] = useState(600);

  // ── Step 2: calibration ────────────────────────────────────────────────────
  const [calibrationConfirmed, setCalibrationConfirmed] = useState(false);
  const [calibrationMode, setCalibrationMode] = useState<"manual" | "aruco">("manual");
  const [showCalibrationTool, setShowCalibrationTool] = useState(false);

  // ── Step 3: empty capture ──────────────────────────────────────────────────
  const [emptyThumb, setEmptyThumb] = useState<string | null>(null);

  // ── Step 4: white sweep ────────────────────────────────────────────────────
  const [whiteMode, setWhiteMode] = useState<SweepMode>("arm");
  const [whiteIdx, setWhiteIdx] = useState(0);
  const whiteIdxRef = useRef(0);
  const whiteRunRef = useRef<RunState>("idle");
  const [whiteRunState, setWhiteRunState] = useState<RunState>("idle");
  const [whiteCurrentSquare, setWhiteCurrentSquare] = useState("");
  const [whitePhase, setWhitePhase] = useState<SweepPhase>("idle");
  const [whiteCapturedThumbs, setWhiteCapturedThumbs] = useState<{ square: string; image: string | null }[]>([]);
  const whitePawnSquareRef = useRef<string | null>(null);
  const [whiteManualTarget, setWhiteManualTarget] = useState("a1");
  const [whiteManualBusy, setWhiteManualBusy] = useState(false);
  const [whiteBulkLabels, setWhiteBulkLabels] = useState<Record<string, BulkLabel>>({});
  const [whiteBulkBusy, setWhiteBulkBusy] = useState(false);
  const [whiteBulkFrames, setWhiteBulkFrames] = useState(1);
  const [showWhiteCaptureEdit, setShowWhiteCaptureEdit] = useState(false);

  // ── Step 5: black sweep ────────────────────────────────────────────────────
  const [blackMode, setBlackMode] = useState<SweepMode>("arm");
  const [blackIdx, setBlackIdx] = useState(0);
  const blackIdxRef = useRef(0);
  const blackRunRef = useRef<RunState>("idle");
  const [blackRunState, setBlackRunState] = useState<RunState>("idle");
  const [blackCurrentSquare, setBlackCurrentSquare] = useState("");
  const [blackPhase, setBlackPhase] = useState<SweepPhase>("idle");
  const [blackCapturedThumbs, setBlackCapturedThumbs] = useState<{ square: string; image: string | null }[]>([]);
  const blackPawnSquareRef = useRef<string | null>(null);
  const [blackManualTarget, setBlackManualTarget] = useState("a1");
  const [blackManualBusy, setBlackManualBusy] = useState(false);
  const [blackBulkLabels, setBlackBulkLabels] = useState<Record<string, BulkLabel>>({});
  const [blackBulkBusy, setBlackBulkBusy] = useState(false);
  const [blackBulkFrames, setBlackBulkFrames] = useState(1);
  const [showBlackCaptureEdit, setShowBlackCaptureEdit] = useState(false);

  // ── Step 6: stats ──────────────────────────────────────────────────────────
  const [accuracy, setAccuracy] = useState<LabelAccuracyReport | null>(null);
  const [computingStats, setComputingStats] = useState(false);
  const [activeClassifier, setActiveClassifier] = useState<string | null>(null);
  const [rescanning, setRescanning] = useState(false);

  // ── Effects ────────────────────────────────────────────────────────────────
  const refreshDatasets = useCallback(async () => {
    try {
      const res = await api.listLabelDatasets();
      setDatasets(res.datasets);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const refreshActive = useCallback(async () => {
    try {
      const r = await api.getActiveClassifier();
      setActiveClassifier(r.active ? r.name : null);
    } catch {
      setActiveClassifier(null);
    }
  }, []);

  useEffect(() => { refreshDatasets(); }, [refreshDatasets]);
  useEffect(() => { refreshActive(); }, [refreshActive]);

  // When picking an existing dataset, pre-seed all form fields from its settings
  useEffect(() => {
    if (!chosenExisting) return;
    api.getLabelDataset(chosenExisting)
      .then((res) => {
        setDraftSource(res.metadata.settings.source_square);
        setDraftPiece(res.metadata.settings.piece_type);
        setDraftLighting(res.metadata.settings.lighting_note);
        setDraftFrames(res.metadata.settings.frames_per_square);
        setDraftSettle(res.metadata.settings.settle_ms);
      })
      .catch(() => null);
  }, [chosenExisting]);

  // Load empty board thumbnail
  useEffect(() => {
    if (!activeName) { setEmptyThumb(null); return; }
    api.getLabelThumb(activeName, "empty", "a1")
      .then((r) => setEmptyThumb(r.image))
      .catch(() => setEmptyThumb(null));
  }, [activeName, meta?.empty_frames]);

  // Seed captured-thumb galleries from saved dataset when loading an existing one
  useEffect(() => {
    if (!activeName) {
      setWhiteCapturedThumbs([]);
      setBlackCapturedThumbs([]);
      return;
    }
    let cancelled = false;
    const seedColor = async (color: "white" | "black") => {
      try {
        const ds = await api.getLabelDataset(activeName);
        const counts = color === "white" ? ds.metadata.white : ds.metadata.black;
        const bulkCounts = color === "white" ? ds.metadata.bulk_white : ds.metadata.bulk_black;
        const seen = new Set<string>();
        for (const [sq, n] of Object.entries(counts ?? {})) if (n > 0) seen.add(sq);
        for (const [sq, n] of Object.entries(bulkCounts ?? {})) if (n > 0) seen.add(sq);
        const squares = Array.from(seen).sort((a, b) => ALL_SQUARES.indexOf(b) - ALL_SQUARES.indexOf(a));
        if (squares.length === 0) return;
        const results = await Promise.all(
          squares.map((sq) =>
            api.getLabelThumb(activeName, color, sq)
              .then((r) => ({ square: sq, image: r.exists ? r.image : null }))
              .catch(() => ({ square: sq, image: null as string | null })),
          ),
        );
        if (cancelled) return;
        if (color === "white") setWhiteCapturedThumbs(results);
        else setBlackCapturedThumbs(results);
      } catch { /* best-effort */ }
    };
    seedColor("white");
    seedColor("black");
    return () => { cancelled = true; };
  }, [activeName]);

  // ── Helpers ────────────────────────────────────────────────────────────────
  const applySettingsPatch = useCallback(async (patch: Partial<LabelSettings>) => {
    if (!activeName || !meta) throw new Error("No active dataset");
    const merged: LabelSettings = { ...meta.settings, ...patch };
    const res = await api.updateLabelSettings(activeName, merged);
    setMeta(res.metadata);
  }, [activeName, meta]);

  const handleRescanAll = useCallback(async () => {
    setRescanning(true);
    try {
      const res = await api.rescanAllLabelDatasets();
      await refreshDatasets();
      setError(`Rescanned ${res.rescanned.length} folder${res.rescanned.length === 1 ? "" : "s"}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRescanning(false);
    }
  }, [refreshDatasets]);

  // ── Step 1: batch-save all settings on Continue ────────────────────────────
  const handleStep1Continue = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      let name: string;
      if (mode === "new") {
        const trimmed = newName.trim();
        if (!trimmed) throw new Error("Dataset name is required");
        const res = await api.createLabelDataset({ name: trimmed, settings: DEFAULT_SETTINGS });
        name = res.metadata.name;
        setActiveName(name);
        setMeta(res.metadata);
      } else {
        if (!chosenExisting) throw new Error("Pick an existing dataset first");
        name = chosenExisting;
        setActiveName(name);
        const res = await api.getLabelDataset(name);
        setMeta(res.metadata);
      }

      const sq = draftSource.trim().toLowerCase();
      if (!ALL_SQUARES.includes(sq))
        throw new Error(`"${draftSource}" is not a valid square — use format like h8`);

      const merged: LabelSettings = {
        source_square: sq,
        piece_type: draftPiece,
        lighting_note: draftLighting,
        frames_per_square: Math.max(1, Math.min(20, Math.round(draftFrames))),
        settle_ms: Math.max(0, Math.min(5000, Math.round(draftSettle))),
      };
      const updated = await api.updateLabelSettings(name, merged);
      setMeta(updated.metadata);
      await refreshDatasets();
      setStep(2);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [mode, newName, chosenExisting, draftSource, draftPiece, draftLighting, draftFrames, draftSettle, refreshDatasets]);

  // Inline save for frames/settle in sweep steps (on blur, no Apply button)
  const saveFrames = useCallback(async (n: number) => {
    const clamped = Math.max(1, Math.min(20, Math.round(n)));
    setDraftFrames(clamped);
    try { await applySettingsPatch({ frames_per_square: clamped }); }
    catch (e) { setError((e as Error).message); }
  }, [applySettingsPatch]);

  const saveSettle = useCallback(async (n: number) => {
    const clamped = Math.max(0, Math.min(5000, Math.round(n)));
    setDraftSettle(clamped);
    try { await applySettingsPatch({ settle_ms: clamped }); }
    catch (e) { setError((e as Error).message); }
  }, [applySettingsPatch]);

  // ── Step 3: empty capture ──────────────────────────────────────────────────
  const captureEmpty = useCallback(async () => {
    if (!activeName) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.captureLabelEmpty(activeName, { params: LABELING_PARAMS, capture: true });
      setMeta(res.metadata);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [activeName]);

  // ── Sweep core ─────────────────────────────────────────────────────────────
  type SweepColor = "white" | "black";

  const doSquare = useCallback(async (
    color: SweepColor,
    square: string,
    fromSquare: string,
    mode: "append" | "overwrite" = "append",
  ) => {
    if (!activeName || !meta) return;
    const setPhase = color === "white" ? setWhitePhase : setBlackPhase;
    const setThumbs = color === "white" ? setWhiteCapturedThumbs : setBlackCapturedThumbs;

    setPhase("moving");
    await api.labelingArm(activeName, { color, square, action: "pick_and_place", from_square: fromSquare });

    setPhase("homing");
    await api.labelingArm(activeName, { color, square, action: "home" });

    setPhase("waiting");
    await new Promise((r) => setTimeout(r, Math.max(200, meta.settings.settle_ms)));

    setPhase("capturing");
    await api.captureLabelSquare(activeName, { color, square, params: LABELING_PARAMS, capture: true, mode });

    const fresh = await api.getLabelDataset(activeName);
    setMeta(fresh.metadata);
    try {
      const thumb = await api.getLabelThumb(activeName, color, square);
      setThumbs((prev) => [
        { square, image: thumb.exists ? thumb.image : null },
        ...prev.filter((t) => t.square !== square),
      ]);
    } catch { /* thumbnail is best-effort */ }
  }, [activeName, meta]);

  const runSweep = useCallback(async (color: SweepColor) => {
    if (!activeName || !meta) return;
    const idxRef = color === "white" ? whiteIdxRef : blackIdxRef;
    const runRef = color === "white" ? whiteRunRef : blackRunRef;
    const setRunState = color === "white" ? setWhiteRunState : setBlackRunState;
    const setIdx = color === "white" ? setWhiteIdx : setBlackIdx;
    const setCurrentSquare = color === "white" ? setWhiteCurrentSquare : setBlackCurrentSquare;
    const setPhase = color === "white" ? setWhitePhase : setBlackPhase;
    const pawnSquareRef = color === "white" ? whitePawnSquareRef : blackPawnSquareRef;

    if (runRef.current === "running") return;
    runRef.current = "running";
    setRunState("running");
    if (!pawnSquareRef.current || idxRef.current === 0) pawnSquareRef.current = meta.settings.source_square;

    try {
      for (let i = idxRef.current; i < ALL_SQUARES.length; i++) {
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const state = runRef.current as string;
          if (state === "aborted") { setRunState("aborted"); setPhase("idle"); return; }
          if (state === "paused") { setPhase("idle"); await new Promise((r) => setTimeout(r, 200)); continue; }
          break;
        }
        const sq = ALL_SQUARES[i];
        idxRef.current = i;
        setIdx(i);
        setCurrentSquare(sq);
        try {
          const fromSquare = pawnSquareRef.current ?? meta.settings.source_square;
          await doSquare(color, sq, fromSquare);
          pawnSquareRef.current = sq;
        } catch (e) {
          setError(`square ${sq}: ${(e as Error).message}`);
          runRef.current = "paused";
          setRunState("paused");
          setPhase("idle");
          return;
        }
      }
      idxRef.current = ALL_SQUARES.length;
      setIdx(ALL_SQUARES.length);
      runRef.current = "done";
      setRunState("done");
    } finally {
      setPhase("idle");
    }
  }, [activeName, meta, doSquare]);

  const pauseSweep = (color: SweepColor) => {
    const runRef = color === "white" ? whiteRunRef : blackRunRef;
    const setRunState = color === "white" ? setWhiteRunState : setBlackRunState;
    if (runRef.current !== "running") return;
    runRef.current = "paused";
    setRunState("paused");
  };
  const resumeSweep = (color: SweepColor) => {
    const runRef = color === "white" ? whiteRunRef : blackRunRef;
    const setRunState = color === "white" ? setWhiteRunState : setBlackRunState;
    if (runRef.current === "paused") { runRef.current = "running"; setRunState("running"); return; }
    runSweep(color);
  };
  const abortSweep = (color: SweepColor) => {
    const runRef = color === "white" ? whiteRunRef : blackRunRef;
    const setRunState = color === "white" ? setWhiteRunState : setBlackRunState;
    const setPhase = color === "white" ? setWhitePhase : setBlackPhase;
    runRef.current = "aborted";
    setRunState("aborted");
    setPhase("idle");
  };

  const retakeSquare = useCallback(async (color: SweepColor, sq: string) => {
    if (!activeName || !meta) return;
    setBusy(true);
    setError(null);
    try {
      await doSquare(color, sq, meta.settings.source_square, "overwrite");
      await api.labelingArm(activeName, { color, square: meta.settings.source_square, action: "move_piece", from_square: sq });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [activeName, meta, doSquare]);

  const manualCaptureSquare = useCallback(async (color: SweepColor, square: string) => {
    if (!activeName || !meta) return;
    const setBusyForColor = color === "white" ? setWhiteManualBusy : setBlackManualBusy;
    const setThumbs = color === "white" ? setWhiteCapturedThumbs : setBlackCapturedThumbs;
    setBusyForColor(true);
    setError(null);
    try {
      await new Promise((r) => setTimeout(r, Math.max(200, meta.settings.settle_ms)));
      await api.captureLabelSquare(activeName, { color, square, params: LABELING_PARAMS, capture: true, skip_arm_home_check: true, mode: "append" });
      const fresh = await api.getLabelDataset(activeName);
      setMeta(fresh.metadata);
      try {
        const thumb = await api.getLabelThumb(activeName, color, square);
        setThumbs((prev) => [
          { square, image: thumb.exists ? thumb.image : null },
          ...prev.filter((t) => t.square !== square),
        ]);
      } catch { /* best-effort */ }
      const counts = color === "white" ? fresh.metadata.white : fresh.metadata.black;
      const startIdx = ALL_SQUARES.indexOf(square);
      let nextIdx = (startIdx + 1) % ALL_SQUARES.length;
      while (nextIdx !== startIdx && (counts[ALL_SQUARES[nextIdx]] ?? 0) > 0) nextIdx = (nextIdx + 1) % ALL_SQUARES.length;
      if (color === "white") setWhiteManualTarget(ALL_SQUARES[nextIdx]);
      else setBlackManualTarget(ALL_SQUARES[nextIdx]);
    } catch (e) {
      setError(`square ${square}: ${(e as Error).message}`);
    } finally {
      setBusyForColor(false);
    }
  }, [activeName, meta]);

  const bulkCapture = useCallback(async (color: SweepColor) => {
    if (!activeName || !meta) return;
    const labels = color === "white" ? whiteBulkLabels : blackBulkLabels;
    const setBulkBusy = color === "white" ? setWhiteBulkBusy : setBlackBulkBusy;
    const frames = color === "white" ? whiteBulkFrames : blackBulkFrames;
    if (Object.keys(labels).length === 0) { setError("Paint at least one square before capturing."); return; }
    setBulkBusy(true);
    setError(null);
    try {
      await api.captureLabelBulk(activeName, { labels, params: LABELING_PARAMS, capture: true, frames: Math.max(1, Math.min(20, frames)), settle_ms: meta.settings.settle_ms });
      const fresh = await api.getLabelDataset(activeName);
      setMeta(fresh.metadata);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  }, [activeName, meta, whiteBulkLabels, blackBulkLabels, whiteBulkFrames, blackBulkFrames]);

  const sendArmHomeForManual = useCallback(async (color: SweepColor) => {
    if (!activeName) return;
    try {
      await api.labelingArm(activeName, { color, square: "a1", action: "home" });
    } catch (e) {
      setError((e as Error).message);
    }
  }, [activeName]);

  // ── Step 6 ─────────────────────────────────────────────────────────────────
  const handleComputeStats = useCallback(async () => {
    if (!activeName) return;
    setComputingStats(true);
    setError(null);
    try {
      const res = await api.computeDatasetStats(activeName);
      setAccuracy(res.accuracy);
      setMeta(res.metadata);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setComputingStats(false);
    }
  }, [activeName]);

  const handleActivate = useCallback(async () => {
    if (!activeName) return;
    setError(null);
    try { await api.setActiveClassifier(activeName); await refreshActive(); }
    catch (e) { setError((e as Error).message); }
  }, [activeName, refreshActive]);

  const handleDeactivate = useCallback(async () => {
    setError(null);
    try { await api.clearActiveClassifier(); await refreshActive(); }
    catch (e) { setError((e as Error).message); }
  }, [refreshActive]);

  // ── Shortcuts for existing datasets ────────────────────────────────────────
  const handleAddMoreData = useCallback(async () => {
    if (!chosenExisting) { setError("Pick an existing dataset first"); return; }
    setError(null);
    try {
      const res = await api.getLabelDataset(chosenExisting);
      setActiveName(chosenExisting);
      setMeta(res.metadata);
      setDraftSource(res.metadata.settings.source_square);
      setDraftPiece(res.metadata.settings.piece_type);
      setDraftLighting(res.metadata.settings.lighting_note);
      setDraftFrames(res.metadata.settings.frames_per_square);
      setDraftSettle(res.metadata.settings.settle_ms);
      setCalibrationConfirmed(true);
      setWhiteMode("bulk");
      setBlackMode("bulk");
      setStep(4);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [chosenExisting]);

  const handleRecomputeExisting = useCallback(async () => {
    if (!chosenExisting) { setError("Pick an existing dataset first"); return; }
    setComputingStats(true);
    setError(null);
    try {
      setActiveName(chosenExisting);
      const res = await api.computeDatasetStats(chosenExisting);
      setAccuracy(res.accuracy);
      setMeta(res.metadata);
      setStep(6);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setComputingStats(false);
    }
  }, [chosenExisting]);

  // ── Derived ────────────────────────────────────────────────────────────────
  const countDone = (main: Record<string, number> | undefined, bulk: Record<string, number> | undefined) => {
    const all = new Set<string>();
    for (const [sq, n] of Object.entries(main ?? {})) if (n > 0) all.add(sq);
    for (const [sq, n] of Object.entries(bulk ?? {})) if (n > 0) all.add(sq);
    return all.size;
  };
  const whiteDoneCount = meta ? countDone(meta.white, meta.bulk_white) : 0;
  const blackDoneCount = meta ? countDone(meta.black, meta.bulk_black) : 0;

  const canGoTo = useCallback((s: StepId): boolean => {
    if (s === 1) return true;
    return !!activeName;
  }, [activeName]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-mono font-semibold text-text-bright">Labeling Wizard</h1>
        <p className="text-sm text-text-muted mt-1 font-jetbrains">
          Capture labeled photos so the classifier knows what each square looks like.
        </p>
      </div>

      {/* Active-classifier banner */}
      {(activeClassifier || true) && (
        <div
          className="rounded-md border px-4 py-3 text-xs font-jetbrains flex items-center justify-between gap-3"
          style={{
            borderColor: activeClassifier ? "oklch(from var(--charm-cyan) l c h / 0.4)" : "var(--charm-border)",
            background: activeClassifier ? "oklch(from var(--charm-cyan) l c h / 0.08)" : "transparent",
          }}
        >
          <span>
            Active classifier:{" "}
            {activeClassifier
              ? <strong style={{ color: "var(--charm-cyan)" }}>"{activeClassifier}"</strong>
              : <span style={{ color: "var(--charm-muted)" }}>none (threshold-based)</span>}
          </span>
          {activeClassifier && (
            <Button variant="outline" size="sm" onClick={handleDeactivate}>Deactivate</Button>
          )}
        </div>
      )}

      {/* Breadcrumb */}
      <Breadcrumb step={step} setStep={setStep} canGoTo={canGoTo} activeName={activeName} />

      {/* Error */}
      {error && (
        <div className="rounded-md border px-4 py-3 text-sm font-jetbrains"
          style={{ borderColor: "oklch(0.6 0.22 25 / 0.5)", color: "oklch(0.7 0.22 25)", background: "oklch(0.3 0.12 25 / 0.15)" }}>
          {error}
          <button className="ml-3 underline text-xs opacity-70" onClick={() => setError(null)}>dismiss</button>
        </div>
      )}

      {/* ── STEP 1: Setup ────────────────────────────────────────────────── */}
      {step === 1 && (
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardContent className="p-6 space-y-7">

            {/* Dataset choice */}
            <section className="space-y-3">
              <SectionTitle>1. Choose a dataset</SectionTitle>
              <div className="flex gap-2">
                {(["new", "existing"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className="px-4 py-1.5 rounded-md text-sm font-jetbrains border transition-colors"
                    style={{
                      background: mode === m ? "var(--charm-cyan)" : "transparent",
                      color: mode === m ? "oklch(0.16 0 0)" : "var(--charm-muted)",
                      borderColor: mode === m ? "var(--charm-cyan)" : "var(--charm-border)",
                    }}
                  >
                    {m === "new" ? "New dataset" : "Existing dataset"}
                  </button>
                ))}
              </div>

              {mode === "new" ? (
                <div className="flex gap-3 items-center">
                  <Input
                    placeholder="e.g. studio-2026-05-27"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="max-w-xs"
                  />
                  <button
                    onClick={handleRescanAll}
                    disabled={rescanning}
                    className="text-xs font-jetbrains underline"
                    style={{ color: "var(--charm-muted)" }}
                  >
                    {rescanning ? "Rescanning…" : "Rescan folders"}
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex gap-3 items-center flex-wrap">
                    <Select value={chosenExisting} onValueChange={(v) => { if (v) setChosenExisting(v); }}>
                      <SelectTrigger className="w-64">
                        <SelectValue placeholder="Pick a dataset" />
                      </SelectTrigger>
                      <SelectContent>
                        {datasets.map((d) => (
                          <SelectItem key={d.name} value={d.name}>{d.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <button
                      onClick={handleRescanAll}
                      disabled={rescanning}
                      className="text-xs font-jetbrains underline"
                      style={{ color: "var(--charm-muted)" }}
                    >
                      {rescanning ? "Rescanning…" : "Rescan folders"}
                    </button>
                  </div>
                  {chosenExisting && (
                    <div className="flex gap-2 flex-wrap">
                      <Button size="sm" variant="outline" onClick={handleAddMoreData}>
                        + Add more data (bulk paint)
                      </Button>
                      <Button size="sm" variant="outline" onClick={handleRecomputeExisting} disabled={computingStats}>
                        {computingStats ? "Computing…" : "View / recompute stats"}
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* Piece settings */}
            <section className="space-y-3">
              <SectionTitle>2. Piece settings</SectionTitle>
              <div className="grid grid-cols-2 gap-5 max-w-lg">
                <div className="space-y-1.5">
                  <label className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    Piece type
                  </label>
                  <Select value={draftPiece} onValueChange={(v) => { if (v) setDraftPiece(v); }}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PIECE_TYPES.map((p) => (
                        <SelectItem key={p} value={p}>{p}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    Starting square (arm picks piece from here)
                  </label>
                  <Input
                    value={draftSource}
                    onChange={(e) => setDraftSource(e.target.value)}
                    placeholder="h8"
                    className="w-28"
                  />
                </div>
              </div>
            </section>

            {/* Capture settings */}
            <section className="space-y-3">
              <SectionTitle>3. Capture settings</SectionTitle>
              <div className="grid grid-cols-2 gap-5 max-w-lg">
                <div className="space-y-1.5">
                  <label className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    Photos per square
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={20}
                    value={draftFrames}
                    onChange={(e) => setDraftFrames(parseInt(e.target.value || "1", 10))}
                    className="w-24"
                  />
                  <p className="text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    5 is a good default. More = better model.
                  </p>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    Wait between photos (ms)
                  </label>
                  <Input
                    type="number"
                    min={0}
                    max={5000}
                    step={50}
                    value={draftSettle}
                    onChange={(e) => setDraftSettle(parseInt(e.target.value || "0", 10))}
                    className="w-28"
                  />
                  <p className="text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    Pause after arm leaves so the board stops wobbling.
                  </p>
                </div>
              </div>
            </section>

            {/* Session note */}
            <section className="space-y-1.5">
              <label className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                Session note (optional — saved in metadata)
              </label>
              <Input
                value={draftLighting}
                onChange={(e) => setDraftLighting(e.target.value)}
                placeholder="e.g. studio lights, overcast"
                className="max-w-sm"
              />
            </section>

            {/* Continue */}
            <Button
              onClick={handleStep1Continue}
              disabled={busy || (mode === "new" ? !newName.trim() : !chosenExisting)}
            >
              {busy ? "Saving…" : "Continue →"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── STEP 2: Calibration ───────────────────────────────────────────── */}
      {step === 2 && (
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardContent className="p-6 space-y-5">
            <div>
              <SectionTitle>Board calibration</SectionTitle>
              <p className="text-sm font-jetbrains mt-1" style={{ color: "var(--charm-muted)" }}>
                The system needs to know where the board is in the camera view so it can crop each square correctly.
                Robot calibration (a1/h1/h8) is configured on the{" "}
                <a href="/robot" className="underline" style={{ color: "var(--charm-cyan)" }}>Scara Calibration</a> page.
              </p>
            </div>

            <label className="flex items-center gap-3 font-jetbrains text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={calibrationConfirmed}
                onChange={(e) => setCalibrationConfirmed(e.target.checked)}
                className="h-4 w-4 accent-cyan-DEFAULT"
              />
              <span>Board + warp calibration is good — I can see the full board in the camera.</span>
            </label>

            <div>
              <button
                onClick={() => setShowCalibrationTool((v) => !v)}
                className="text-xs font-jetbrains underline"
                style={{ color: "var(--charm-muted)" }}
              >
                {showCalibrationTool ? "Hide calibration tools ↑" : "Need to calibrate? Open calibration tools ↓"}
              </button>

              {showCalibrationTool && (
                <div className="mt-4 space-y-3">
                  <div className="flex gap-2">
                    {(["manual", "aruco"] as const).map((m) => (
                      <button
                        key={m}
                        onClick={() => setCalibrationMode(m)}
                        className="px-3 py-1.5 rounded-md text-xs font-jetbrains border transition-colors"
                        style={{
                          background: calibrationMode === m ? "oklch(from var(--charm-cyan) l c h / 0.15)" : "transparent",
                          color: calibrationMode === m ? "var(--charm-cyan)" : "var(--charm-muted)",
                          borderColor: calibrationMode === m ? "oklch(from var(--charm-cyan) l c h / 0.5)" : "var(--charm-border)",
                        }}
                      >
                        {m === "manual" ? "Manual (click corners)" : "ArUco markers (auto)"}
                      </button>
                    ))}
                  </div>
                  <div className="rounded-md border p-3" style={{ borderColor: "var(--charm-border)" }}>
                    {calibrationMode === "manual"
                      ? <ManualCalibration />
                      : <ArucoCalibration embedded onApplied={() => setCalibrationConfirmed(true)} />}
                  </div>
                </div>
              )}
            </div>

            <NavRow
              onBack={() => setStep(1)}
              onForward={() => setStep(3)}
              forwardDisabled={!calibrationConfirmed}
            />
          </CardContent>
        </Card>
      )}

      {/* ── STEP 3: Empty board ───────────────────────────────────────────── */}
      {step === 3 && (
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardContent className="p-6 space-y-5">
            <div>
              <SectionTitle>Capture empty board</SectionTitle>
              <p className="text-sm font-jetbrains mt-1" style={{ color: "var(--charm-muted)" }}>
                Remove <strong>all pieces</strong> from the board, then press capture. The system
                photographs the empty board as a reference for occupancy detection.
              </p>
            </div>

            <div className="flex items-start gap-6">
              <div className="space-y-3">
                <Button onClick={captureEmpty} disabled={busy || !activeName}>
                  {busy ? "Capturing…" : "📷 Capture empty board"}
                </Button>
                {meta && meta.empty_frames > 0 && (
                  <p className="text-sm font-jetbrains" style={{ color: "var(--charm-cyan)" }}>
                    ✓ {meta.empty_frames} frame{meta.empty_frames === 1 ? "" : "s"} captured
                  </p>
                )}
                {meta && meta.empty_frames > 0 && (
                  <button
                    onClick={captureEmpty}
                    disabled={busy}
                    className="text-xs font-jetbrains underline"
                    style={{ color: "var(--charm-muted)" }}
                  >
                    Recapture
                  </button>
                )}
              </div>

              {emptyThumb && (
                <img
                  src={imageSrc(emptyThumb)}
                  alt="empty board preview"
                  className="rounded-md border w-48 h-48 object-cover"
                  style={{ borderColor: "var(--charm-border)" }}
                />
              )}
            </div>

            <NavRow
              onBack={() => setStep(2)}
              onForward={() => setStep(4)}
              forwardDisabled={!meta?.empty_frames}
            />
          </CardContent>
        </Card>
      )}

      {/* ── STEP 4: White pieces ─────────────────────────────────────────── */}
      {step === 4 && meta && (
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardContent className="p-6 space-y-5">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <SectionTitle>White pieces — {whiteDoneCount}/64 squares captured</SectionTitle>
                <div
                  className="mt-2 px-3 py-2 rounded-md text-sm font-jetbrains inline-block"
                  style={{ background: "oklch(from var(--charm-cyan) l c h / 0.1)", border: "1px solid oklch(from var(--charm-cyan) l c h / 0.3)" }}
                >
                  Place a <strong style={{ color: "var(--charm-cyan)" }}>white {meta.settings.piece_type}</strong> on{" "}
                  <strong style={{ color: "var(--charm-cyan)" }}>{meta.settings.source_square.toUpperCase()}</strong>,
                  then start the sweep.
                </div>
              </div>
              {/* Inline settings */}
              <div className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                <button onClick={() => setShowWhiteCaptureEdit((v) => !v)} className="underline">
                  {meta.settings.frames_per_square} photos/sq · {meta.settings.settle_ms}ms wait
                  {showWhiteCaptureEdit ? " ↑" : " ✎"}
                </button>
                {showWhiteCaptureEdit && (
                  <div className="mt-2 flex gap-4 items-end">
                    <div>
                      <div className="mb-1">Photos/sq</div>
                      <Input
                        type="number" min={1} max={20}
                        value={draftFrames}
                        onChange={(e) => setDraftFrames(+e.target.value)}
                        onBlur={(e) => saveFrames(+e.target.value)}
                        className="w-20"
                      />
                    </div>
                    <div>
                      <div className="mb-1">Wait (ms)</div>
                      <Input
                        type="number" min={0} max={5000} step={50}
                        value={draftSettle}
                        onChange={(e) => setDraftSettle(+e.target.value)}
                        onBlur={(e) => saveSettle(+e.target.value)}
                        className="w-24"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            <ModeToggle
              mode={whiteMode}
              onChange={setWhiteMode}
              disabled={whiteRunState === "running" || whiteManualBusy || whiteBulkBusy}
            />

            {whiteMode === "arm" && (
              <SweepRunner
                color="white"
                currentSquare={whiteCurrentSquare}
                idx={whiteIdx}
                state={whiteRunState}
                phase={whitePhase}
                onStart={() => runSweep("white")}
                onPause={() => pauseSweep("white")}
                onResume={() => resumeSweep("white")}
                onAbort={() => abortSweep("white")}
                done={whiteDoneCount}
              />
            )}
            {whiteMode === "manual" && (
              <ManualSweepRunner
                color="white"
                meta={meta}
                target={whiteManualTarget}
                setTarget={setWhiteManualTarget}
                busy={whiteManualBusy}
                onValidate={() => manualCaptureSquare("white", whiteManualTarget)}
                onPark={() => sendArmHomeForManual("white")}
              />
            )}
            {whiteMode === "bulk" && (
              <BulkPaintRunner
                color="white"
                meta={meta}
                labels={whiteBulkLabels}
                setLabels={setWhiteBulkLabels}
                frames={whiteBulkFrames}
                setFrames={setWhiteBulkFrames}
                busy={whiteBulkBusy}
                onCapture={() => bulkCapture("white")}
              />
            )}

            <CapturedGallery thumbs={whiteCapturedThumbs} color="white" />

            {whiteDoneCount > 0 && (
              <RetakeGrid
                datasetName={activeName ?? ""}
                color="white"
                meta={meta}
                onRetake={(sq) => retakeSquare("white", sq)}
                busy={busy}
              />
            )}

            <NavRow
              onBack={() => setStep(3)}
              onForward={() => setStep(5)}
              forwardDisabled={whiteMode === "arm" && whiteRunState !== "done" && whiteDoneCount < 1}
              forwardLabel={whiteDoneCount < 64 ? `Continue with ${whiteDoneCount}/64 →` : "Continue →"}
            />
          </CardContent>
        </Card>
      )}

      {/* ── STEP 5: Black pieces ─────────────────────────────────────────── */}
      {step === 5 && meta && (
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardContent className="p-6 space-y-5">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <SectionTitle>Black pieces — {blackDoneCount}/64 squares captured</SectionTitle>
                <div
                  className="mt-2 px-3 py-2 rounded-md text-sm font-jetbrains inline-block"
                  style={{ background: "oklch(from var(--charm-amber) l c h / 0.1)", border: "1px solid oklch(from var(--charm-amber) l c h / 0.3)" }}
                >
                  Return the white piece. Place a <strong style={{ color: "var(--charm-amber)" }}>black {meta.settings.piece_type}</strong> on{" "}
                  <strong style={{ color: "var(--charm-amber)" }}>{meta.settings.source_square.toUpperCase()}</strong>.
                </div>
              </div>
              <div className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                <button onClick={() => setShowBlackCaptureEdit((v) => !v)} className="underline">
                  {meta.settings.frames_per_square} photos/sq · {meta.settings.settle_ms}ms wait
                  {showBlackCaptureEdit ? " ↑" : " ✎"}
                </button>
                {showBlackCaptureEdit && (
                  <div className="mt-2 flex gap-4 items-end">
                    <div>
                      <div className="mb-1">Photos/sq</div>
                      <Input
                        type="number" min={1} max={20}
                        value={draftFrames}
                        onChange={(e) => setDraftFrames(+e.target.value)}
                        onBlur={(e) => saveFrames(+e.target.value)}
                        className="w-20"
                      />
                    </div>
                    <div>
                      <div className="mb-1">Wait (ms)</div>
                      <Input
                        type="number" min={0} max={5000} step={50}
                        value={draftSettle}
                        onChange={(e) => setDraftSettle(+e.target.value)}
                        onBlur={(e) => saveSettle(+e.target.value)}
                        className="w-24"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            <ModeToggle
              mode={blackMode}
              onChange={setBlackMode}
              disabled={blackRunState === "running" || blackManualBusy || blackBulkBusy}
            />

            {blackMode === "arm" && (
              <SweepRunner
                color="black"
                currentSquare={blackCurrentSquare}
                idx={blackIdx}
                state={blackRunState}
                phase={blackPhase}
                onStart={() => runSweep("black")}
                onPause={() => pauseSweep("black")}
                onResume={() => resumeSweep("black")}
                onAbort={() => abortSweep("black")}
                done={blackDoneCount}
              />
            )}
            {blackMode === "manual" && (
              <ManualSweepRunner
                color="black"
                meta={meta}
                target={blackManualTarget}
                setTarget={setBlackManualTarget}
                busy={blackManualBusy}
                onValidate={() => manualCaptureSquare("black", blackManualTarget)}
                onPark={() => sendArmHomeForManual("black")}
              />
            )}
            {blackMode === "bulk" && (
              <BulkPaintRunner
                color="black"
                meta={meta}
                labels={blackBulkLabels}
                setLabels={setBlackBulkLabels}
                frames={blackBulkFrames}
                setFrames={setBlackBulkFrames}
                busy={blackBulkBusy}
                onCapture={() => bulkCapture("black")}
              />
            )}

            <CapturedGallery thumbs={blackCapturedThumbs} color="black" />

            {blackDoneCount > 0 && (
              <RetakeGrid
                datasetName={activeName ?? ""}
                color="black"
                meta={meta}
                onRetake={(sq) => retakeSquare("black", sq)}
                busy={busy}
              />
            )}

            <NavRow
              onBack={() => setStep(4)}
              onForward={() => setStep(6)}
              forwardDisabled={blackMode === "arm" && blackRunState !== "done" && blackDoneCount < 1}
              forwardLabel={blackDoneCount < 64 ? `Continue with ${blackDoneCount}/64 →` : "Continue →"}
            />
          </CardContent>
        </Card>
      )}

      {/* ── STEP 6: Finish ───────────────────────────────────────────────── */}
      {step === 6 && (
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardContent className="p-6 space-y-5">
            <div>
              <SectionTitle>Compute stats & activate</SectionTitle>
              <p className="text-sm font-jetbrains mt-1" style={{ color: "var(--charm-muted)" }}>
                Builds per-square exemplars and runs a leave-one-out accuracy check.
                Writes <code>exemplar_config.json</code> into the dataset folder.
              </p>
            </div>

            <Button onClick={handleComputeStats} disabled={computingStats || !activeName}>
              {computingStats ? "Computing…" : "Compute & save"}
            </Button>

            {accuracy && (
              <>
                <AccuracyReport accuracy={accuracy} />

                <div className="space-y-2 pt-2">
                  <p className="text-sm font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                    Activate this dataset to make the live pipeline classify with these per-square exemplars.
                  </p>
                  <div className="flex gap-3 items-center flex-wrap">
                    <Button
                      onClick={handleActivate}
                      disabled={!activeName}
                      variant={activeClassifier === activeName ? "secondary" : "default"}
                    >
                      {activeClassifier === activeName ? "Active ✓" : "Activate as live classifier"}
                    </Button>
                    {activeClassifier && activeClassifier !== activeName && (
                      <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                        Will replace: {activeClassifier}
                      </span>
                    )}
                  </div>
                </div>
              </>
            )}

            <NavRow onBack={() => setStep(5)} forwardDisabled forwardLabel="Done" />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
      {children}
    </h2>
  );
}

function Breadcrumb({
  step,
  setStep,
  canGoTo,
  activeName,
}: {
  step: StepId;
  setStep: (s: StepId) => void;
  canGoTo: (s: StepId) => boolean;
  activeName: string | null;
}) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-2">
        {STEPS.map((s) => {
          const active = s.id === step;
          const enabled = canGoTo(s.id);
          return (
            <button
              key={s.id}
              onClick={() => enabled && setStep(s.id)}
              disabled={!enabled}
              className="px-3 py-1.5 rounded-md text-xs font-jetbrains transition-all"
              style={{
                background: active ? "var(--charm-cyan)" : "var(--charm-card)",
                color: active ? "oklch(0.16 0 0)" : enabled ? "var(--charm-text)" : "var(--charm-muted)",
                border: "1px solid var(--charm-border)",
                opacity: enabled ? 1 : 0.45,
                cursor: enabled ? "pointer" : "not-allowed",
                fontWeight: active ? 600 : 400,
              }}
            >
              {s.id}. {s.label}
            </button>
          );
        })}
      </div>
      {activeName && (
        <p className="text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>
          Dataset: <strong style={{ color: "var(--charm-text)" }}>{activeName}</strong>
        </p>
      )}
    </div>
  );
}

function NavRow({
  onBack,
  onForward,
  forwardDisabled,
  forwardLabel = "Continue →",
}: {
  onBack?: () => void;
  onForward?: () => void;
  forwardDisabled?: boolean;
  forwardLabel?: string;
}) {
  return (
    <div className="flex justify-between pt-2 border-t border-border">
      <Button variant="outline" onClick={onBack} disabled={!onBack}>← Back</Button>
      <Button onClick={onForward} disabled={forwardDisabled || !onForward}>{forwardLabel}</Button>
    </div>
  );
}

const PHASE_LABEL: Record<SweepPhase, string> = {
  idle: "—",
  moving: "moving piece",
  homing: "arm going home",
  waiting: "settling",
  capturing: "capturing photos",
};

function SweepRunner({
  color,
  currentSquare,
  idx,
  state,
  phase,
  onStart,
  onPause,
  onResume,
  onAbort,
  done,
}: {
  color: "white" | "black";
  currentSquare: string;
  idx: number;
  state: RunState;
  phase: SweepPhase;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onAbort: () => void;
  done: number;
}) {
  const total = ALL_SQUARES.length;
  const progress = Math.min(idx, total);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <p className="text-sm font-jetbrains">
          {state === "running" || state === "paused"
            ? `Square ${progress + 1}/${total} — ${currentSquare || ALL_SQUARES[progress]}`
            : state === "done"
              ? `Complete (${done}/${total} squares)`
              : state === "aborted"
                ? `Stopped at square ${progress + 1}/${total}`
                : `${done}/${total} squares captured`}
          {state === "running" && (
            <span style={{ color: "var(--charm-cyan)" }}> · {PHASE_LABEL[phase]}</span>
          )}
        </p>
      </div>
      <div className="w-full rounded-sm overflow-hidden h-2" style={{ background: "oklch(0.3 0 0)" }}>
        <div className="h-full rounded-sm transition-all" style={{ width: `${(progress / total) * 100}%`, background: color === "white" ? "var(--charm-cyan)" : "var(--charm-amber)" }} />
      </div>
      <div className="flex gap-2">
        {(state === "idle" || state === "done" || state === "aborted") && (
          <Button onClick={onStart}>
            {state === "idle" ? "Start arm sweep" : "Resume from current square"}
          </Button>
        )}
        {state === "running" && (
          <>
            <Button variant="outline" onClick={onPause}>Pause</Button>
            <Button variant="destructive" onClick={onAbort}>Stop</Button>
          </>
        )}
        {state === "paused" && (
          <>
            <Button onClick={onResume}>Resume</Button>
            <Button variant="destructive" onClick={onAbort}>Abort</Button>
          </>
        )}
      </div>
    </div>
  );
}

function CapturedGallery({ thumbs, color }: { thumbs: { square: string; image: string | null }[]; color: "white" | "black" }) {
  if (thumbs.length === 0) return null;
  return (
    <div className="rounded-md border p-3 space-y-2" style={{ borderColor: "var(--charm-border)" }}>
      <p className="text-[10px] font-jetbrains uppercase tracking-widest" style={{ color: "var(--charm-muted)" }}>
        Captured ({thumbs.length}) — newest first
      </p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {thumbs.map((t) => (
          <div key={t.square} className="flex flex-col items-center gap-1 shrink-0" style={{ width: 56 }}>
            <div
              className="rounded border overflow-hidden flex items-center justify-center"
              style={{
                width: 56, height: 56,
                borderColor: color === "white" ? "oklch(from var(--charm-cyan) l c h / 0.4)" : "oklch(from var(--charm-amber) l c h / 0.4)",
                background: "oklch(from var(--charm-cyan) l c h / 0.04)",
              }}
            >
              {t.image
                // eslint-disable-next-line @next/next/no-img-element
                ? <img src={imageSrc(t.image)} alt={`${color} ${t.square}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                : <span className="text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>—</span>}
            </div>
            <span className="text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>{t.square}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RetakeGrid({
  color,
  meta,
  onRetake,
  busy,
}: {
  datasetName: string;
  color: "white" | "black";
  meta: LabelDatasetMeta;
  onRetake: (sq: string) => void;
  busy: boolean;
}) {
  const counts = color === "white" ? meta.white : meta.black;
  const bulkCounts = color === "white" ? meta.bulk_white : meta.bulk_black;
  const doneSquares = new Set<string>();
  for (const [sq, n] of Object.entries(counts ?? {})) if (n > 0) doneSquares.add(sq);
  for (const [sq, n] of Object.entries(bulkCounts ?? {})) if (n > 0) doneSquares.add(sq);

  return (
    <div className="space-y-2">
      <p className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
        Coverage: {doneSquares.size}/64 squares captured. Click any square to retake it.
      </p>
      <div className="grid grid-cols-8 gap-1 w-fit">
        {Array.from({ length: 8 }).map((_, row) =>
          Array.from({ length: 8 }).map((_, col) => {
            const file = "abcdefgh"[col];
            const rank = 8 - row;
            const sq = `${file}${rank}`;
            const sweep = counts?.[sq] ?? 0;
            const bulk = bulkCounts?.[sq] ?? 0;
            const total = sweep + bulk;
            return (
              <button
                key={sq}
                type="button"
                disabled={busy}
                onClick={() => onRetake(sq)}
                title={`${sq}: ${sweep} sweep + ${bulk} bulk — click to retake`}
                className="rounded text-[10px] font-jetbrains border h-10 w-10 flex flex-col items-center justify-center hover:border-cyan-400 disabled:opacity-40"
                style={{
                  background: total > 0
                    ? "oklch(from var(--charm-cyan) l c h / 0.12)"
                    : "oklch(0.4 0.12 25 / 0.2)",
                  borderColor: "var(--charm-border)",
                }}
              >
                <span>{sq}</span>
                <span style={{ opacity: 0.7 }}>{total || ""}</span>
              </button>
            );
          }),
        )}
      </div>
    </div>
  );
}

function ModeToggle({ mode, onChange, disabled }: { mode: SweepMode; onChange: (m: SweepMode) => void; disabled?: boolean }) {
  const modes: { id: SweepMode; label: string; desc: string }[] = [
    { id: "arm", label: "Arm sweep", desc: "Robot moves piece square to square automatically" },
    { id: "manual", label: "Manual", desc: "You place each piece; system captures on command" },
    { id: "bulk", label: "Bulk paint", desc: "Set up a whole board position and capture everything at once" },
  ];
  return (
    <div className="flex gap-2 flex-wrap">
      {modes.map((m) => (
        <button
          key={m.id}
          onClick={() => onChange(m.id)}
          disabled={disabled}
          title={m.desc}
          className="px-3 py-1.5 rounded-md text-xs font-jetbrains border transition-colors disabled:opacity-50"
          style={{
            background: mode === m.id ? "oklch(from var(--charm-cyan) l c h / 0.15)" : "transparent",
            color: mode === m.id ? "var(--charm-cyan)" : "var(--charm-muted)",
            borderColor: mode === m.id ? "oklch(from var(--charm-cyan) l c h / 0.5)" : "var(--charm-border)",
          }}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}

function BulkPaintRunner({
  color,
  meta,
  labels,
  setLabels,
  frames,
  setFrames,
  busy,
  onCapture,
}: {
  color: "white" | "black";
  meta: LabelDatasetMeta;
  labels: Record<string, BulkLabel>;
  setLabels: (next: Record<string, BulkLabel>) => void;
  frames: number;
  setFrames: (n: number) => void;
  busy: boolean;
  onCapture: () => void;
}) {
  const painted = Object.keys(labels).length;
  const bulkCounts = { empty: meta.bulk_empty ?? {}, white: meta.bulk_white ?? {}, black: meta.bulk_black ?? {} };
  return (
    <div className="space-y-3">
      <p className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
        Set up the board with any mix of pieces, paint each square with the matching color, then capture. Good for adding lots of data quickly.
      </p>
      <BulkPaintBoard labels={labels} onChange={setLabels} busy={busy} counts={bulkCounts} />
      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>Photos this round:</label>
        <Input
          type="number" min={1} max={20} value={frames}
          onChange={(e) => setFrames(Math.max(1, Math.min(20, parseInt(e.target.value || "1", 10))))}
          className="w-20" disabled={busy}
        />
        <Button onClick={onCapture} disabled={busy || painted === 0}>
          {busy ? "Capturing…" : `📷 Capture ${painted} square${painted === 1 ? "" : "s"}`}
        </Button>
      </div>
    </div>
  );
}

function ManualSweepRunner({
  color,
  meta,
  target,
  setTarget,
  busy,
  onValidate,
  onPark,
}: {
  color: "white" | "black";
  meta: LabelDatasetMeta;
  target: string;
  setTarget: (sq: string) => void;
  busy: boolean;
  onValidate: () => void;
  onPark: () => void;
}) {
  const counts = color === "white" ? meta.white : meta.black;
  const done = Object.keys(counts).filter((sq) => (counts[sq] ?? 0) > 0).length;
  const idx = ALL_SQUARES.indexOf(target);
  const prev = () => setTarget(ALL_SQUARES[(idx - 1 + ALL_SQUARES.length) % ALL_SQUARES.length]);
  const next = () => setTarget(ALL_SQUARES[(idx + 1) % ALL_SQUARES.length]);
  const targetCaptured = (counts[target] ?? 0) > 0;

  return (
    <div className="space-y-3">
      <div
        className="rounded-md border p-4 flex flex-wrap items-center gap-4 font-jetbrains"
        style={{ borderColor: "oklch(from var(--charm-cyan) l c h / 0.4)", background: "oklch(from var(--charm-cyan) l c h / 0.06)" }}
      >
        <div>
          <p className="text-xs" style={{ color: "var(--charm-muted)" }}>
            Place a {color} {meta.settings.piece_type} on
          </p>
          <p className="text-3xl font-semibold" style={{ color: "var(--charm-cyan)" }}>
            {target.toUpperCase()}
          </p>
          <p className="text-[11px]" style={{ color: "var(--charm-muted)" }}>
            {targetCaptured ? `already captured (${counts[target]} frames) — will add` : "not yet captured"}
          </p>
        </div>
        <div className="flex flex-col gap-2 ml-auto">
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={prev} disabled={busy}>← Prev</Button>
            <Button size="sm" variant="outline" onClick={next} disabled={busy}>Next →</Button>
            <Button size="sm" variant="outline" onClick={onPark} disabled={busy}>Park arm</Button>
          </div>
          <Button onClick={onValidate} disabled={busy}>
            {busy ? "Capturing…" : `📷 Capture ${target.toUpperCase()}`}
          </Button>
        </div>
      </div>
      <p className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>{done}/64 captured · click grid to jump</p>
      <div className="grid grid-cols-8 gap-1 w-fit">
        {Array.from({ length: 8 }).map((_, row) =>
          Array.from({ length: 8 }).map((_, col) => {
            const file = "abcdefgh"[col];
            const rank = 8 - row;
            const sq = `${file}${rank}`;
            const captured = counts[sq] ?? 0;
            const isTarget = sq === target;
            return (
              <button
                key={sq}
                type="button"
                disabled={busy}
                onClick={() => setTarget(sq)}
                className="rounded text-[10px] font-jetbrains border h-10 w-10 flex flex-col items-center justify-center hover:border-cyan-400 disabled:opacity-40"
                style={{
                  background: isTarget ? "oklch(from var(--charm-cyan) l c h / 0.35)" : captured > 0 ? "oklch(from var(--charm-cyan) l c h / 0.12)" : "oklch(0.4 0.12 25 / 0.15)",
                  borderColor: isTarget ? "var(--charm-cyan)" : "var(--charm-border)",
                  borderWidth: isTarget ? 2 : 1,
                }}
                title={`${sq}: ${captured} frames${isTarget ? " — current" : ""}`}
              >
                <span>{sq}</span>
                <span style={{ opacity: 0.7 }}>{captured || ""}</span>
              </button>
            );
          }),
        )}
      </div>
    </div>
  );
}

function AccuracyReport({ accuracy }: { accuracy: LabelAccuracyReport }) {
  const overall = accuracy.overall;
  const pct = (overall.accuracy * 100).toFixed(1);
  return (
    <div className="space-y-3">
      <p className="text-sm font-jetbrains">
        Leave-one-out accuracy:{" "}
        <strong style={{ color: overall.accuracy >= 0.95 ? "var(--charm-cyan)" : overall.accuracy >= 0.8 ? "var(--charm-amber)" : "oklch(0.7 0.22 25)" }}>
          {pct}%
        </strong>
        <span style={{ color: "var(--charm-muted)" }}> ({overall.correct}/{overall.total})</span>
      </p>
      <div className="grid grid-cols-8 gap-1 w-fit">
        {Array.from({ length: 8 }).map((_, row) =>
          Array.from({ length: 8 }).map((_, col) => {
            const file = "abcdefgh"[col];
            const rank = 8 - row;
            const sq = `${file}${rank}`;
            const entry = accuracy.squares[`${row},${col}`];
            const acc = entry?.accuracy ?? 0;
            const hue = Math.round(acc * 120);
            return (
              <div
                key={sq}
                title={`${sq}: ${(acc * 100).toFixed(1)}% (${entry?.correct ?? 0}/${entry?.total ?? 0})`}
                className="rounded text-[10px] font-jetbrains border h-10 w-10 flex flex-col items-center justify-center"
                style={{ background: `hsl(${hue} 50% 25%)`, borderColor: "var(--charm-border)", color: "white" }}
              >
                <span>{sq}</span>
                <span style={{ opacity: 0.85 }}>{(acc * 100).toFixed(0)}%</span>
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}
