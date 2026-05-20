"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  LabelAccuracyReport,
  LabelDatasetMeta,
  LabelSettings,
} from "@/lib/api";
import { DEFAULT_PARAMS } from "@/lib/types";

// Force the on-board crop pipeline for every labeling capture: outer board
// warp + inner warp. The backend also enforces this, but we keep it explicit
// here so the request payload makes the contract visible.
const LABELING_PARAMS = { ...DEFAULT_PARAMS, apply_inner_warp: true };
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import ArucoCalibration from "@/components/ArucoCalibration";
import { imageSrc } from "@/lib/image";

// --- Step list (also drives the breadcrumb at the top) ---
const STEPS = [
  { id: 1, label: "Dataset configuration" },
  { id: 2, label: "Capture settings" },
  { id: 3, label: "Calibration check" },
  { id: 4, label: "Empty board capture" },
  { id: 5, label: "Empty board review" },
  { id: 6, label: "Place white source piece" },
  { id: 7, label: "White sweep" },
  { id: 8, label: "White sweep review" },
  { id: 9, label: "Switch to black piece" },
  { id: 10, label: "Black sweep" },
  { id: 11, label: "Black sweep review" },
  { id: 12, label: "Finalize & compute stats" },
] as const;
type StepId = (typeof STEPS)[number]["id"];

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

function rcKey(square: string): string {
  const file = square[0].toLowerCase();
  const rank = parseInt(square[1], 10);
  const col = file.charCodeAt(0) - "a".charCodeAt(0);
  const row = 8 - rank;
  return `${row},${col}`;
}

export default function LabelingWizardPage() {
  // ---------- global state ----------
  const [step, setStep] = useState<StepId>(1);
  const [datasets, setDatasets] = useState<LabelDatasetMeta[]>([]);
  const [activeName, setActiveName] = useState<string | null>(null);
  const [meta, setMeta] = useState<LabelDatasetMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // ---------- Step 1: dataset config (each field has its own Apply) ----------
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [newName, setNewName] = useState("");
  const [chosenExisting, setChosenExisting] = useState<string>("");
  const [datasetApplied, setDatasetApplied] = useState(false);

  const [draftSource, setDraftSource] = useState("h8");
  const [draftPiece, setDraftPiece] = useState("pawn");
  const [draftLighting, setDraftLighting] = useState("");
  const [appliedSource, setAppliedSource] = useState(false);
  const [appliedPiece, setAppliedPiece] = useState(false);
  const [appliedLighting, setAppliedLighting] = useState(false);

  // ---------- Step 2: capture settings ----------
  const [draftFrames, setDraftFrames] = useState(5);
  const [draftSettle, setDraftSettle] = useState(600);
  const [appliedFrames, setAppliedFrames] = useState(false);
  const [appliedSettle, setAppliedSettle] = useState(false);

  // ---------- Step 3: calibration confirmation ----------
  const [calibrationConfirmed, setCalibrationConfirmed] = useState(false);
  const [calibrationMode, setCalibrationMode] = useState<"manual" | "aruco">("manual");
  const [appliedCalibrationMode, setAppliedCalibrationMode] = useState(false);

  // ---------- Step 4/5: empty capture ----------
  const [emptyThumb, setEmptyThumb] = useState<string | null>(null);

  // ---------- Step 6: white piece placed confirm ----------
  const [whitePlaced, setWhitePlaced] = useState(false);

  // ---------- Step 7: white sweep ----------
  // sweepState: idle, running, paused, aborted, done
  type SweepPhase = "idle" | "moving" | "homing" | "waiting" | "capturing";
  const [whiteIdx, setWhiteIdx] = useState(0);
  const whiteIdxRef = useRef(0);
  const whiteRunRef = useRef<"idle" | "running" | "paused" | "aborted" | "done">("idle");
  const [whiteRunState, setWhiteRunState] = useState<typeof whiteRunRef.current>("idle");
  const [whiteCurrentSquare, setWhiteCurrentSquare] = useState<string>("");
  const [whitePhase, setWhitePhase] = useState<SweepPhase>("idle");
  const [whiteCapturedThumbs, setWhiteCapturedThumbs] = useState<
    { square: string; image: string | null }[]
  >([]);
  const whitePawnSquareRef = useRef<string | null>(null);

  // ---------- Step 9: black piece placed confirm ----------
  const [blackPlaced, setBlackPlaced] = useState(false);

  // ---------- Step 10: black sweep ----------
  const [blackIdx, setBlackIdx] = useState(0);
  const blackIdxRef = useRef(0);
  const blackRunRef = useRef<"idle" | "running" | "paused" | "aborted" | "done">("idle");
  const [blackRunState, setBlackRunState] = useState<typeof blackRunRef.current>("idle");
  const [blackCurrentSquare, setBlackCurrentSquare] = useState<string>("");
  const [blackPhase, setBlackPhase] = useState<SweepPhase>("idle");
  const [blackCapturedThumbs, setBlackCapturedThumbs] = useState<
    { square: string; image: string | null }[]
  >([]);
  const blackPawnSquareRef = useRef<string | null>(null);

  // ---------- Step 12: stats ----------
  const [accuracy, setAccuracy] = useState<LabelAccuracyReport | null>(null);
  const [computingStats, setComputingStats] = useState(false);
  const [activeClassifier, setActiveClassifier] = useState<string | null>(null);

  // ---------- effects ----------
  const refreshDatasets = useCallback(async () => {
    try {
      const res = await api.listLabelDatasets();
      setDatasets(res.datasets);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refreshDatasets();
  }, [refreshDatasets]);

  const refreshActive = useCallback(async () => {
    try {
      const r = await api.getActiveClassifier();
      setActiveClassifier(r.active ? r.name : null);
    } catch {
      setActiveClassifier(null);
    }
  }, []);

  useEffect(() => {
    refreshActive();
  }, [refreshActive]);

  const refreshMeta = useCallback(async (name: string) => {
    try {
      const res = await api.getLabelDataset(name);
      setMeta(res.metadata);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (activeName) refreshMeta(activeName);
  }, [activeName, refreshMeta]);

  useEffect(() => {
    if (!activeName) {
      setEmptyThumb(null);
      return;
    }
    api
      .getLabelThumb(activeName, "empty", "a1")
      .then((r) => setEmptyThumb(r.image))
      .catch(() => setEmptyThumb(null));
  }, [activeName, meta?.empty_frames]);

  // Seed the captured-thumb galleries from the dataset on initial load, so a
  // resumed (or reviewed) sweep shows the previously captured squares too.
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
        const squares = Object.keys(counts).filter((sq) => counts[sq] > 0);
        if (squares.length === 0) return;
        // Order by sweep order so newest-first matches the live gallery order
        squares.sort(
          (a, b) => ALL_SQUARES.indexOf(b) - ALL_SQUARES.indexOf(a),
        );
        const results = await Promise.all(
          squares.map((sq) =>
            api
              .getLabelThumb(activeName, color, sq)
              .then((r) => ({ square: sq, image: r.exists ? r.image : null }))
              .catch(() => ({ square: sq, image: null as string | null })),
          ),
        );
        if (cancelled) return;
        if (color === "white") setWhiteCapturedThumbs(results);
        else setBlackCapturedThumbs(results);
      } catch {
        /* best-effort seeding */
      }
    };
    seedColor("white");
    seedColor("black");
    return () => {
      cancelled = true;
    };
  }, [activeName]);

  // ---------- handlers: step 1 ----------
  const allStep1Applied = useMemo(
    () => datasetApplied && appliedSource && appliedPiece && appliedLighting,
    [datasetApplied, appliedSource, appliedPiece, appliedLighting],
  );

  const handleApplyDataset = async () => {
    setError(null);
    try {
      if (mode === "new") {
        const trimmed = newName.trim();
        if (!trimmed) throw new Error("Dataset name is required");
        const res = await api.createLabelDataset({
          name: trimmed,
          settings: { ...DEFAULT_SETTINGS },
        });
        setActiveName(res.metadata.name);
        setMeta(res.metadata);
      } else {
        if (!chosenExisting) throw new Error("Pick an existing dataset");
        setActiveName(chosenExisting);
        const res = await api.getLabelDataset(chosenExisting);
        setMeta(res.metadata);
        // seed drafts from existing settings
        setDraftSource(res.metadata.settings.source_square);
        setDraftPiece(res.metadata.settings.piece_type);
        setDraftLighting(res.metadata.settings.lighting_note);
        setDraftFrames(res.metadata.settings.frames_per_square);
        setDraftSettle(res.metadata.settings.settle_ms);
      }
      setDatasetApplied(true);
      await refreshDatasets();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // Generic helper: apply one settings field
  const applySettingsPatch = async (patch: Partial<LabelSettings>) => {
    if (!activeName || !meta) throw new Error("Apply dataset first");
    const merged: LabelSettings = { ...meta.settings, ...patch };
    const res = await api.updateLabelSettings(activeName, merged);
    setMeta(res.metadata);
  };

  const handleApplySource = async () => {
    setError(null);
    try {
      const sq = draftSource.trim().toLowerCase();
      if (!ALL_SQUARES.includes(sq)) throw new Error(`Invalid square: ${draftSource}`);
      await applySettingsPatch({ source_square: sq });
      setAppliedSource(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const handleApplyPiece = async () => {
    setError(null);
    try {
      await applySettingsPatch({ piece_type: draftPiece });
      setAppliedPiece(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const handleApplyLighting = async () => {
    setError(null);
    try {
      await applySettingsPatch({ lighting_note: draftLighting });
      setAppliedLighting(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // ---------- handlers: step 2 ----------
  const handleApplyFrames = async () => {
    setError(null);
    try {
      const n = Math.max(1, Math.min(20, Math.round(draftFrames)));
      await applySettingsPatch({ frames_per_square: n });
      setDraftFrames(n);
      setAppliedFrames(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const handleApplySettle = async () => {
    setError(null);
    try {
      const n = Math.max(0, Math.min(5000, Math.round(draftSettle)));
      await applySettingsPatch({ settle_ms: n });
      setDraftSettle(n);
      setAppliedSettle(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // ---------- handlers: step 4 ----------
  const captureEmpty = async () => {
    if (!activeName) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.captureLabelEmpty(activeName, {
        params: LABELING_PARAMS,
        capture: true,
      });
      setMeta(res.metadata);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // ---------- handlers: sweep core ----------
  type SweepColor = "white" | "black";

  const doSquare = useCallback(
    async (color: SweepColor, square: string, fromSquare: string) => {
      if (!activeName || !meta) return;
      const setPhase = color === "white" ? setWhitePhase : setBlackPhase;
      const setThumbs =
        color === "white" ? setWhiteCapturedThumbs : setBlackCapturedThumbs;

      // 1) pick from the previous square, put on the target square (no home yet)
      setPhase("moving");
      await api.labelingArm(activeName, {
        color,
        square,
        action: "pick_and_place",
        from_square: fromSquare,
      });

      // 2) send the arm home — the backend blocks until the arm reaches home
      //    so we can deterministically capture without the arm in frame.
      setPhase("homing");
      await api.labelingArm(activeName, {
        color,
        square,
        action: "home",
      });

      // 3) settle so any wobble dampens before grabbing frames
      setPhase("waiting");
      await new Promise((r) => setTimeout(r, Math.max(200, meta.settings.settle_ms)));

      // 4) capture frames for the target square
      setPhase("capturing");
      await api.captureLabelSquare(activeName, {
        color,
        square,
        params: LABELING_PARAMS,
        capture: true,
      });

      // 5) refresh metadata and add a thumbnail of the just-captured cell
      const fresh = await api.getLabelDataset(activeName);
      setMeta(fresh.metadata);
      try {
        const thumb = await api.getLabelThumb(activeName, color, square);
        setThumbs((prev) => [
          { square, image: thumb.exists ? thumb.image : null },
          ...prev.filter((t) => t.square !== square),
        ]);
      } catch {
        // thumbnail is best-effort; ignore failures
      }
    },
    [activeName, meta],
  );

  const runSweep = useCallback(
    async (color: SweepColor) => {
      if (!activeName || !meta) return;
      const idxRef = color === "white" ? whiteIdxRef : blackIdxRef;
      const runRef = color === "white" ? whiteRunRef : blackRunRef;
      const setRunState = color === "white" ? setWhiteRunState : setBlackRunState;
      const setIdx = color === "white" ? setWhiteIdx : setBlackIdx;
      const setCurrentSquare =
        color === "white" ? setWhiteCurrentSquare : setBlackCurrentSquare;
      const setPhase = color === "white" ? setWhitePhase : setBlackPhase;
      const pawnSquareRef = color === "white" ? whitePawnSquareRef : blackPawnSquareRef;

      // Don't start a second loop if one is already running (e.g. user
      // clicked Start twice). Re-entering runSweep while running would race
      // two for-loops against the same idxRef.
      if (runRef.current === "running") return;
      runRef.current = "running";
      setRunState("running");

      if (!pawnSquareRef.current || idxRef.current === 0) {
        pawnSquareRef.current = meta.settings.source_square;
      }

      try {
        for (let i = idxRef.current; i < ALL_SQUARES.length; i++) {
          // honor abort/pause between squares.
          // runRef is mutated by other handlers, so TS narrowing isn't useful here.
          // eslint-disable-next-line no-constant-condition
          while (true) {
            const state = runRef.current as string;
            if (state === "aborted") {
              setRunState("aborted");
              setPhase("idle");
              return;
            }
            if (state === "paused") {
              setPhase("idle");
              await new Promise((r) => setTimeout(r, 200));
              continue;
            }
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
    },
    [activeName, meta, doSquare],
  );

  const pauseSweep = (color: SweepColor) => {
    const runRef = color === "white" ? whiteRunRef : blackRunRef;
    const setRunState = color === "white" ? setWhiteRunState : setBlackRunState;
    // Don't clobber a finished sweep into "paused".
    if (runRef.current !== "running") return;
    runRef.current = "paused";
    setRunState("paused");
  };
  const resumeSweep = (color: SweepColor) => {
    const runRef = color === "white" ? whiteRunRef : blackRunRef;
    const setRunState = color === "white" ? setWhiteRunState : setBlackRunState;
    // If currently paused, the existing loop is polling runRef.current. Just
    // flip it back to "running" and let that loop continue — starting a new
    // runSweep here would race two loops against the same idxRef.
    if (runRef.current === "paused") {
      runRef.current = "running";
      setRunState("running");
      return;
    }
    // Otherwise (idle, done, aborted), start fresh from the current index.
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

  // ---------- handlers: retake one square ----------
  const retakeSquare = async (color: SweepColor, sq: string) => {
    if (!activeName) return;
    setBusy(true);
    setError(null);
    try {
      if (!meta) return;
      await doSquare(color, sq, meta.settings.source_square);
      await api.labelingArm(activeName, {
        color,
        square: meta.settings.source_square,
        action: "move_piece",
        from_square: sq,
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // ---------- handlers: step 12 ----------
  const handleComputeStats = async () => {
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
  };

  const handleActivate = async () => {
    if (!activeName) return;
    setError(null);
    try {
      await api.setActiveClassifier(activeName);
      await refreshActive();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleDeactivate = async () => {
    setError(null);
    try {
      await api.clearActiveClassifier();
      await refreshActive();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // ---------- derived ----------
  const whiteDoneCount = meta ? Object.keys(meta.white).length : 0;
  const blackDoneCount = meta ? Object.keys(meta.black).length : 0;

  // ---------- render ----------
  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <header>
        <h1 className="text-2xl font-jetbrains font-semibold">Labeled-data wizard</h1>
        <p className="text-sm text-muted-foreground font-jetbrains">
          Arm-driven capture for the per-square exemplar classifier. Every transition
          requires Apply / Confirm — the wizard never advances on its own.
        </p>
      </header>

      <div
        className="rounded-md border p-3 text-xs font-jetbrains flex items-center justify-between"
        style={{
          borderColor: "var(--charm-border)",
          background: activeClassifier
            ? "color-mix(in oklab, var(--charm-cyan) 8%, transparent)"
            : "transparent",
        }}
      >
        <span>
          Live pipeline classifier:{" "}
          {activeClassifier ? (
            <strong style={{ color: "var(--charm-cyan)" }}>
              exemplar — dataset “{activeClassifier}”
            </strong>
          ) : (
            <strong>threshold-based (no exemplar dataset active)</strong>
          )}
        </span>
        {activeClassifier && (
          <Button variant="outline" size="sm" onClick={handleDeactivate}>
            Deactivate
          </Button>
        )}
      </div>

      <StepIndicator current={step} />

      {error && (
        <div
          className="rounded-md border p-3 text-sm font-jetbrains"
          style={{
            borderColor: "var(--charm-red, #f87171)",
            color: "var(--charm-red, #f87171)",
            background: "color-mix(in oklab, var(--charm-red, #f87171) 8%, transparent)",
          }}
        >
          {error}
        </div>
      )}

      {/* STEP 1 */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">Step 1 / 12 — Dataset configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-3 items-center">
              <label className="flex items-center gap-2 font-jetbrains text-sm">
                <input
                  type="radio"
                  checked={mode === "new"}
                  onChange={() => {
                    setMode("new");
                    setDatasetApplied(false);
                  }}
                />
                New dataset
              </label>
              <label className="flex items-center gap-2 font-jetbrains text-sm">
                <input
                  type="radio"
                  checked={mode === "existing"}
                  onChange={() => {
                    setMode("existing");
                    setDatasetApplied(false);
                  }}
                />
                Existing dataset
              </label>
            </div>

            {mode === "new" ? (
              <div className="flex gap-2 items-center">
                <Input
                  placeholder="Dataset name (e.g. studio_2026-05-19)"
                  value={newName}
                  onChange={(e) => {
                    setNewName(e.target.value);
                    setDatasetApplied(false);
                  }}
                  className="max-w-md"
                />
                <Button onClick={handleApplyDataset} disabled={datasetApplied}>
                  {datasetApplied ? "Applied ✓" : "Apply"}
                </Button>
              </div>
            ) : (
              <div className="flex gap-2 items-center">
                <Select
                  value={chosenExisting}
                  onValueChange={(v) => {
                    setChosenExisting(v ?? "");
                    setDatasetApplied(false);
                  }}
                >
                  <SelectTrigger className="w-72">
                    <SelectValue placeholder="Pick dataset" />
                  </SelectTrigger>
                  <SelectContent>
                    {datasets.map((d) => (
                      <SelectItem key={d.name} value={d.name}>
                        {d.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button onClick={handleApplyDataset} disabled={datasetApplied}>
                  {datasetApplied ? "Applied ✓" : "Apply"}
                </Button>
              </div>
            )}

            <Separator />

            <SettingRow
              label="Source square"
              hint="Square the arm picks the piece from each step (default H8)."
              applied={appliedSource}
              onApply={handleApplySource}
              disabled={!datasetApplied}
            >
              <Input
                value={draftSource}
                onChange={(e) => {
                  setDraftSource(e.target.value);
                  setAppliedSource(false);
                }}
                className="w-24"
              />
            </SettingRow>

            <SettingRow
              label="Piece type"
              hint="Arm uses this to look up its pick/place Z height."
              applied={appliedPiece}
              onApply={handleApplyPiece}
              disabled={!datasetApplied}
            >
              <Select
                value={draftPiece}
                onValueChange={(v) => {
                  setDraftPiece(v ?? "pawn");
                  setAppliedPiece(false);
                }}
              >
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PIECE_TYPES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </SettingRow>

            <SettingRow
              label="Lighting / setup note"
              hint="Free-text describing this session (saved in metadata)."
              applied={appliedLighting}
              onApply={handleApplyLighting}
              disabled={!datasetApplied}
            >
              <Input
                value={draftLighting}
                onChange={(e) => {
                  setDraftLighting(e.target.value);
                  setAppliedLighting(false);
                }}
                className="max-w-md"
              />
            </SettingRow>

            <NavRow
              backDisabled
              forwardDisabled={!allStep1Applied}
              forwardLabel="Confirm and continue → Step 2"
              onForward={() => setStep(2)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 2 */}
      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">Step 2 / 12 — Capture settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <SettingRow
              label="Frames per square"
              hint="More frames = better noise model. 5 is a good default."
              applied={appliedFrames}
              onApply={handleApplyFrames}
              disabled={!activeName}
            >
              <Input
                type="number"
                min={1}
                max={20}
                value={draftFrames}
                onChange={(e) => {
                  setDraftFrames(parseInt(e.target.value || "0", 10));
                  setAppliedFrames(false);
                }}
                className="w-24"
              />
            </SettingRow>

            <SettingRow
              label="Settle delay (ms)"
              hint="Pause after arm leaves the frame before capturing."
              applied={appliedSettle}
              onApply={handleApplySettle}
              disabled={!activeName}
            >
              <Input
                type="number"
                min={0}
                max={5000}
                step={50}
                value={draftSettle}
                onChange={(e) => {
                  setDraftSettle(parseInt(e.target.value || "0", 10));
                  setAppliedSettle(false);
                }}
                className="w-32"
              />
            </SettingRow>

            <NavRow
              forwardDisabled={!(appliedFrames && appliedSettle)}
              forwardLabel="Confirm and continue → Step 3"
              onBack={() => setStep(1)}
              onForward={() => setStep(3)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 3 */}
      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">Step 3 / 12 — Calibration check</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm font-jetbrains">
              Confirm or re-run board calibration. Robot calibration (a1/h1/h8) is
              separate — set it up on the{" "}
              <a href="/robot" className="underline">Scara Calibration</a> page if needed.
            </p>
            <div
              className="rounded-md border p-3 text-xs font-jetbrains space-y-1"
              style={{
                borderColor: "var(--charm-border)",
                background: "color-mix(in oklab, var(--charm-cyan) 6%, transparent)",
              }}
            >
              <div>
                <strong>Capture cropping</strong> — every frame is run through:
              </div>
              <ol className="list-decimal pl-5">
                <li>Outer board four-point warp (using saved corner calibration)</li>
                <li>Inner-corner refinement warp</li>
              </ol>
              <div>
                Saved JPEGs are 800×800 board-only. Anything outside the board
                is cropped before disk — no off-board noise enters the dataset.
              </div>
            </div>

            {/* Calibration source selector with its own Apply */}
            <div className="space-y-2">
              <p className="font-jetbrains text-sm font-semibold">Board calibration source</p>
              <div className="flex gap-3 items-center">
                <label className="flex items-center gap-2 font-jetbrains text-sm">
                  <input
                    type="radio"
                    checked={calibrationMode === "manual"}
                    onChange={() => {
                      setCalibrationMode("manual");
                      setAppliedCalibrationMode(false);
                    }}
                  />
                  Manual (existing saved corners)
                </label>
                <label className="flex items-center gap-2 font-jetbrains text-sm">
                  <input
                    type="radio"
                    checked={calibrationMode === "aruco"}
                    onChange={() => {
                      setCalibrationMode("aruco");
                      setAppliedCalibrationMode(false);
                    }}
                  />
                  ArUco markers (auto-detect)
                </label>
                <Button
                  size="sm"
                  variant={appliedCalibrationMode ? "secondary" : "default"}
                  onClick={() => setAppliedCalibrationMode(true)}
                >
                  {appliedCalibrationMode ? "Applied ✓" : "Apply"}
                </Button>
              </div>
              {appliedCalibrationMode && calibrationMode === "aruco" && (
                <div className="rounded-md border p-3">
                  <ArucoCalibration
                    embedded
                    onApplied={() => setCalibrationConfirmed(true)}
                  />
                </div>
              )}
              {appliedCalibrationMode && calibrationMode === "manual" && (
                <p className="text-xs text-muted-foreground font-jetbrains">
                  Using the manually-set corners from the{" "}
                  <a href="/lab" className="underline">Computer Vision</a> page. Make
                  sure they're current before continuing.
                </p>
              )}
            </div>

            <label className="flex items-center gap-2 font-jetbrains text-sm">
              <input
                type="checkbox"
                checked={calibrationConfirmed}
                onChange={(e) => setCalibrationConfirmed(e.target.checked)}
              />
              I confirm board + robot calibration are good.
            </label>
            <NavRow
              forwardDisabled={!calibrationConfirmed || !appliedCalibrationMode}
              forwardLabel="Confirm and continue → Step 4"
              onBack={() => setStep(2)}
              onForward={() => setStep(4)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 4 */}
      {step === 4 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 4 / 12 — Empty board capture
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm font-jetbrains">
              Remove all pieces from the board, then press the button. The wizard will
              capture {meta?.settings.frames_per_square ?? "?"} frames of the empty board.
            </p>
            <Button onClick={captureEmpty} disabled={busy || !activeName}>
              {busy ? "Capturing…" : "Capture empty board"}
            </Button>
            <NavRow
              forwardDisabled={!meta?.empty_frames}
              forwardLabel="Continue → Step 5"
              onBack={() => setStep(3)}
              onForward={() => setStep(5)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 5 */}
      {step === 5 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 5 / 12 — Empty board review
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm font-jetbrains">
              Frames captured: <strong>{meta?.empty_frames ?? 0}</strong>
            </p>
            {emptyThumb && (
              <img
                src={`data:image/jpeg;base64,${emptyThumb}`}
                alt="empty board frame"
                className="max-w-md rounded-md border"
              />
            )}
            <div className="flex gap-2">
              <Button onClick={captureEmpty} variant="outline" disabled={busy}>
                Recapture
              </Button>
            </div>
            <NavRow
              forwardDisabled={!meta?.empty_frames}
              forwardLabel="Confirm and continue → Step 6"
              onBack={() => setStep(4)}
              onForward={() => setStep(6)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 6 */}
      {step === 6 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 6 / 12 — Place white source piece
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm font-jetbrains">
              Place a <strong>white {meta?.settings.piece_type}</strong> on{" "}
              <strong>{meta?.settings.source_square.toUpperCase()}</strong>. Leave the rest
              of the board empty.
            </p>
            <label className="flex items-center gap-2 font-jetbrains text-sm">
              <input
                type="checkbox"
                checked={whitePlaced}
                onChange={(e) => setWhitePlaced(e.target.checked)}
              />
              Piece is placed correctly.
            </label>
            <NavRow
              forwardDisabled={!whitePlaced}
              forwardLabel="Confirm and continue → Step 7"
              onBack={() => setStep(5)}
              onForward={() => setStep(7)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 7 */}
      {step === 7 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 7 / 12 — White sweep
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {meta && (
              <CaptureTuner
                meta={meta}
                draftFrames={draftFrames}
                draftSettle={draftSettle}
                appliedFrames={appliedFrames}
                appliedSettle={appliedSettle}
                onDraftFrames={(n) => {
                  setDraftFrames(n);
                  setAppliedFrames(false);
                }}
                onDraftSettle={(n) => {
                  setDraftSettle(n);
                  setAppliedSettle(false);
                }}
                onApplyFrames={handleApplyFrames}
                onApplySettle={handleApplySettle}
                disabled={whiteRunState === "running"}
              />
            )}
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
            <CapturedGallery thumbs={whiteCapturedThumbs} color="white" />
            <NavRow
              forwardDisabled={whiteRunState !== "done" && whiteDoneCount < 64}
              forwardLabel="Continue → Step 8"
              onBack={() => setStep(6)}
              onForward={() => setStep(8)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 8 */}
      {step === 8 && meta && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 8 / 12 — White sweep review
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <RetakeGrid
              datasetName={activeName ?? ""}
              color="white"
              meta={meta}
              onRetake={(sq) => retakeSquare("white", sq)}
              busy={busy}
            />
            <NavRow
              forwardDisabled={whiteDoneCount < 64}
              forwardLabel="Confirm and continue → Step 9"
              onBack={() => setStep(7)}
              onForward={() => setStep(9)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 9 */}
      {step === 9 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 9 / 12 — Switch to black piece
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm font-jetbrains">
              Return the white piece off the board. Place a{" "}
              <strong>black {meta?.settings.piece_type}</strong> on{" "}
              <strong>{meta?.settings.source_square.toUpperCase()}</strong>.
            </p>
            <label className="flex items-center gap-2 font-jetbrains text-sm">
              <input
                type="checkbox"
                checked={blackPlaced}
                onChange={(e) => setBlackPlaced(e.target.checked)}
              />
              Black piece is placed correctly.
            </label>
            <NavRow
              forwardDisabled={!blackPlaced}
              forwardLabel="Confirm and continue → Step 10"
              onBack={() => setStep(8)}
              onForward={() => setStep(10)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 10 */}
      {step === 10 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 10 / 12 — Black sweep
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {meta && (
              <CaptureTuner
                meta={meta}
                draftFrames={draftFrames}
                draftSettle={draftSettle}
                appliedFrames={appliedFrames}
                appliedSettle={appliedSettle}
                onDraftFrames={(n) => {
                  setDraftFrames(n);
                  setAppliedFrames(false);
                }}
                onDraftSettle={(n) => {
                  setDraftSettle(n);
                  setAppliedSettle(false);
                }}
                onApplyFrames={handleApplyFrames}
                onApplySettle={handleApplySettle}
                disabled={blackRunState === "running"}
              />
            )}
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
            <CapturedGallery thumbs={blackCapturedThumbs} color="black" />
            <NavRow
              forwardDisabled={blackRunState !== "done" && blackDoneCount < 64}
              forwardLabel="Continue → Step 11"
              onBack={() => setStep(9)}
              onForward={() => setStep(11)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 11 */}
      {step === 11 && meta && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 11 / 12 — Black sweep review
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <RetakeGrid
              datasetName={activeName ?? ""}
              color="black"
              meta={meta}
              onRetake={(sq) => retakeSquare("black", sq)}
              busy={busy}
            />
            <NavRow
              forwardDisabled={blackDoneCount < 64}
              forwardLabel="Confirm and continue → Step 12"
              onBack={() => setStep(10)}
              onForward={() => setStep(12)}
            />
          </CardContent>
        </Card>
      )}

      {/* STEP 12 */}
      {step === 12 && (
        <Card>
          <CardHeader>
            <CardTitle className="font-jetbrains">
              Step 12 / 12 — Finalize & compute stats
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm font-jetbrains">
              Computes per-square exemplars and a leave-one-frame-out accuracy report.
              Writes <code>exemplar_config.json</code> + <code>accuracy.json</code> into
              the dataset directory so the runtime classifier can load it.
            </p>
            <Button onClick={handleComputeStats} disabled={computingStats || !activeName}>
              {computingStats ? "Computing…" : "Compute & save"}
            </Button>
            {accuracy && (
              <>
                <AccuracyReport accuracy={accuracy} />
                <Separator />
                <div className="space-y-2">
                  <p className="text-sm font-jetbrains">
                    Activate this dataset to make the live pipeline (Computer Vision page,
                    Game flow) classify with these per-square exemplars instead of the
                    threshold path. You can always deactivate from the banner above.
                  </p>
                  <div className="flex gap-2 items-center">
                    <Button
                      onClick={handleActivate}
                      disabled={!activeName}
                      variant={activeClassifier === activeName ? "secondary" : "default"}
                    >
                      {activeClassifier === activeName
                        ? "Active ✓"
                        : "Activate as live classifier"}
                    </Button>
                    {activeClassifier && activeClassifier !== activeName && (
                      <span className="text-xs font-jetbrains text-muted-foreground">
                        Currently active: {activeClassifier} (will be replaced)
                      </span>
                    )}
                  </div>
                </div>
              </>
            )}
            <NavRow
              forwardDisabled
              forwardLabel="Done"
              onBack={() => setStep(11)}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function StepIndicator({ current }: { current: StepId }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-xs font-jetbrains">
      {STEPS.map((s) => {
        const active = s.id === current;
        const done = s.id < current;
        return (
          <div
            key={s.id}
            className="rounded-md px-2 py-1 border"
            style={{
              borderColor: active
                ? "var(--charm-cyan)"
                : done
                  ? "color-mix(in oklab, var(--charm-cyan) 30%, transparent)"
                  : "var(--charm-border)",
              color: active ? "var(--charm-cyan)" : "var(--charm-muted)",
              background: active
                ? "color-mix(in oklab, var(--charm-cyan) 10%, transparent)"
                : "transparent",
              fontWeight: active ? 600 : 400,
            }}
            title={s.label}
          >
            {s.id}. {s.label}
          </div>
        );
      })}
    </div>
  );
}

function SettingRow({
  label,
  hint,
  applied,
  onApply,
  disabled,
  children,
}: {
  label: string;
  hint?: string;
  applied: boolean;
  onApply: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <label className="font-jetbrains text-sm min-w-[180px]">{label}</label>
        {children}
        <Button
          size="sm"
          variant={applied ? "secondary" : "default"}
          onClick={onApply}
          disabled={disabled}
        >
          {applied ? "Applied ✓" : "Apply"}
        </Button>
      </div>
      {hint && (
        <p className="text-xs text-muted-foreground font-jetbrains pl-[180px]">{hint}</p>
      )}
    </div>
  );
}

function NavRow({
  onBack,
  onForward,
  backDisabled,
  forwardDisabled,
  forwardLabel,
}: {
  onBack?: () => void;
  onForward?: () => void;
  backDisabled?: boolean;
  forwardDisabled?: boolean;
  forwardLabel: string;
}) {
  return (
    <div className="flex justify-between pt-2">
      <Button variant="outline" onClick={onBack} disabled={backDisabled || !onBack}>
        ← Back
      </Button>
      <Button onClick={onForward} disabled={forwardDisabled || !onForward}>
        {forwardLabel}
      </Button>
    </div>
  );
}

function CaptureTuner({
  meta,
  draftFrames,
  draftSettle,
  appliedFrames,
  appliedSettle,
  onDraftFrames,
  onDraftSettle,
  onApplyFrames,
  onApplySettle,
  disabled,
}: {
  meta: LabelDatasetMeta;
  draftFrames: number;
  draftSettle: number;
  appliedFrames: boolean;
  appliedSettle: boolean;
  onDraftFrames: (n: number) => void;
  onDraftSettle: (n: number) => void;
  onApplyFrames: () => void;
  onApplySettle: () => void;
  disabled?: boolean;
}) {
  // Estimator uses the *applied* settings (what the sweep will actually use),
  // not the draft, so the number doesn't lie before Apply is pressed.
  const frames = meta.settings.frames_per_square;
  const settleSec = meta.settings.settle_ms / 1000;
  // Rough heuristic per square: ~10s arm overhead (pickup + place + home)
  // + frames × (delay + ~0.8s for camera grab and warp).
  const perSquareSec = 10 + frames * (settleSec + 0.8);
  const totalMin = (perSquareSec * 64) / 60;
  return (
    <div
      className="rounded-md border p-3 space-y-2 font-jetbrains text-xs"
      style={{
        borderColor: "var(--charm-border)",
        background: "color-mix(in oklab, var(--charm-cyan) 5%, transparent)",
      }}
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <span style={{ color: "var(--charm-muted)" }}>Pictures per square</span>
          <Input
            type="number"
            min={1}
            max={20}
            value={draftFrames}
            disabled={disabled}
            onChange={(e) => onDraftFrames(parseInt(e.target.value || "0", 10))}
            className="w-20"
          />
        </div>
        <Button
          size="sm"
          variant={appliedFrames ? "outline" : "default"}
          disabled={disabled}
          onClick={onApplyFrames}
        >
          {appliedFrames ? "Applied" : "Apply"}
        </Button>
        <div className="flex flex-col gap-1">
          <span style={{ color: "var(--charm-muted)" }}>Delay between pictures (ms)</span>
          <Input
            type="number"
            min={0}
            max={5000}
            step={50}
            value={draftSettle}
            disabled={disabled}
            onChange={(e) => onDraftSettle(parseInt(e.target.value || "0", 10))}
            className="w-28"
          />
        </div>
        <Button
          size="sm"
          variant={appliedSettle ? "outline" : "default"}
          disabled={disabled}
          onClick={onApplySettle}
        >
          {appliedSettle ? "Applied" : "Apply"}
        </Button>
      </div>
      <p style={{ color: "var(--charm-muted)" }}>
        Active: {frames} pictures × {settleSec.toFixed(2)}s delay → ~
        {perSquareSec.toFixed(0)}s per square × 64 ≈ {totalMin.toFixed(1)} min
        per color sweep. (Rough estimate — arm motion adds variance.)
      </p>
    </div>
  );
}

const PHASE_LABEL: Record<"idle" | "moving" | "homing" | "waiting" | "capturing", string> = {
  idle: "—",
  moving: "pick + put",
  homing: "homing",
  waiting: "settling",
  capturing: "capturing frames",
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
  state: "idle" | "running" | "paused" | "aborted" | "done";
  phase: "idle" | "moving" | "homing" | "waiting" | "capturing";
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onAbort: () => void;
  done: number;
}) {
  const total = ALL_SQUARES.length;
  const progress = Math.min(idx, total);
  const phaseLabel = state === "running" ? PHASE_LABEL[phase] : PHASE_LABEL.idle;
  return (
    <div className="space-y-3">
      <p className="text-sm font-jetbrains">
        Sweeping <strong>{color}</strong> —{" "}
        {state === "running" || state === "paused"
          ? `square ${progress + 1}/${total} (${currentSquare || ALL_SQUARES[progress]})`
          : state === "done"
            ? `complete (${done}/${total} squares captured)`
            : state === "aborted"
              ? `aborted at square ${progress + 1}/${total}`
              : "idle"}
        {state === "running" && (
          <span style={{ color: "var(--charm-cyan)" }}> · {phaseLabel}</span>
        )}
      </p>
      <div className="w-full bg-muted rounded h-2 overflow-hidden">
        <div
          className="h-full"
          style={{
            width: `${(progress / total) * 100}%`,
            background: "var(--charm-cyan)",
          }}
        />
      </div>
      <div className="flex gap-2">
        {(state === "idle" || state === "done" || state === "aborted") && (
          <Button onClick={onStart}>
            {state === "idle" ? "Start sweep" : "Restart from current square"}
          </Button>
        )}
        {state === "running" && (
          <>
            <Button variant="outline" onClick={onPause}>
              Pause
            </Button>
            <Button variant="destructive" onClick={onAbort}>
              Abort
            </Button>
          </>
        )}
        {state === "paused" && (
          <>
            <Button onClick={onResume}>Resume</Button>
            <Button variant="destructive" onClick={onAbort}>
              Abort
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function CapturedGallery({
  thumbs,
  color,
}: {
  thumbs: { square: string; image: string | null }[];
  color: "white" | "black";
}) {
  if (thumbs.length === 0) return null;
  return (
    <div
      className="rounded-md border p-3 space-y-2"
      style={{ borderColor: "var(--charm-border)" }}
    >
      <p className="text-xs font-jetbrains uppercase tracking-widest" style={{ color: "var(--charm-muted)" }}>
        Captured so far ({thumbs.length}) — newest first
      </p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {thumbs.map((t) => (
          <div
            key={t.square}
            className="flex flex-col items-center gap-1 shrink-0"
            style={{ width: 56 }}
          >
            <div
              className="rounded border overflow-hidden flex items-center justify-center"
              style={{
                width: 56,
                height: 56,
                borderColor:
                  color === "white"
                    ? "color-mix(in oklab, var(--charm-cyan) 40%, transparent)"
                    : "color-mix(in oklab, var(--charm-amber, #fbbf24) 40%, transparent)",
                background: "color-mix(in oklab, var(--charm-cyan) 4%, transparent)",
              }}
            >
              {t.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={imageSrc(t.image)}
                  alt={`${color} ${t.square}`}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <span className="text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                  no img
                </span>
              )}
            </div>
            <span className="text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>
              {t.square}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RetakeGrid({
  datasetName,
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
  return (
    <div>
      <p className="text-sm font-jetbrains mb-2">
        {Object.keys(counts).length}/64 squares captured. Hover any cell to retake.
      </p>
      <div className="grid grid-cols-8 gap-1 w-fit">
        {Array.from({ length: 8 }).map((_, row) =>
          Array.from({ length: 8 }).map((_, col) => {
            const file = "abcdefgh"[col];
            const rank = 8 - row;
            const sq = `${file}${rank}`;
            const captured = counts[sq] ?? 0;
            return (
              <button
                key={sq}
                type="button"
                disabled={busy}
                onClick={() => onRetake(sq)}
                className="rounded text-[10px] font-jetbrains border h-10 w-10 flex flex-col items-center justify-center hover:border-cyan-400 disabled:opacity-40"
                style={{
                  background:
                    captured > 0
                      ? "color-mix(in oklab, var(--charm-cyan) 12%, transparent)"
                      : "color-mix(in oklab, var(--charm-red, #f87171) 12%, transparent)",
                  borderColor: "var(--charm-border)",
                }}
                title={`${sq}: ${captured} frames — click to retake`}
              >
                <span>{sq}</span>
                <span style={{ opacity: 0.7 }}>{captured}</span>
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
  return (
    <div className="space-y-2">
      <p className="text-sm font-jetbrains">
        Overall LOO accuracy:{" "}
        <strong>
          {(overall.accuracy * 100).toFixed(1)}% ({overall.correct}/{overall.total})
        </strong>
      </p>
      <div className="grid grid-cols-8 gap-1 w-fit">
        {Array.from({ length: 8 }).map((_, row) =>
          Array.from({ length: 8 }).map((_, col) => {
            const file = "abcdefgh"[col];
            const rank = 8 - row;
            const sq = `${file}${rank}`;
            const entry = accuracy.squares[`${row},${col}`];
            const acc = entry?.accuracy ?? 0;
            const hue = Math.round(acc * 120); // 0=red, 120=green
            return (
              <div
                key={sq}
                title={`${sq}: ${(acc * 100).toFixed(1)}% (${entry?.correct ?? 0}/${entry?.total ?? 0})`}
                className="rounded text-[10px] font-jetbrains border h-10 w-10 flex flex-col items-center justify-center"
                style={{
                  background: `hsl(${hue} 50% 25%)`,
                  borderColor: "var(--charm-border)",
                  color: "white",
                }}
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
