"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  CalibrationStatus,
  CnnActiveModel,
  CnnBuildStatus,
  CnnModelMeta,
  CnnSourceDatasetMeta,
  CnnTrainArtifacts,
  CnnTrainStatus,
} from "@/lib/api";
import { imageSrc } from "@/lib/image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import ArucoCalibration from "@/components/ArucoCalibration";
import CnnScanPanel from "@/components/CnnScanPanel";

const STEPS = [
  {
    id: 1,
    label: "Preflight check",
    blurb:
      "Make sure the camera is reachable and the chessboard has been calibrated. Everything else needs these in place.",
  },
  {
    id: 2,
    label: "Pick source captures",
    blurb:
      "Pick the labeling dataset that already has photos of the empty board and one piece on each square. We'll reuse them to teach the model.",
  },
  {
    id: 3,
    label: "Build CNN dataset",
    blurb:
      "We cut each photo into 64 little squares and label every one. The result is the training set the model will learn from.",
  },
  {
    id: 4,
    label: "Train model",
    blurb:
      "We're teaching the computer to recognize whether each square is empty, has a white piece, or a black piece.",
  },
  {
    id: 5,
    label: "Activate model",
    blurb:
      "Pick which trained model the live system should use. You can train more later and switch back any time.",
  },
  {
    id: 6,
    label: "Live test & debug",
    blurb:
      "Try the model on a fresh capture and inspect every square. If the model gets one wrong, mark it — that gets folded into the next training run.",
  },
] as const;

type StepId = (typeof STEPS)[number]["id"];

const STORAGE_KEY = "charm.cnn.wizard.v1";

interface WizardState {
  step: StepId;
  buildId: string | null;
  builtOutput: string | null;
  trainJobId: string | null;
  trainRunId: string | null;
  pickedSource: string | null;
  outputName: string;
}

function loadState(): WizardState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as WizardState;
  } catch {
    return null;
  }
}

function saveState(s: WizardState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // localStorage may be unavailable; non-fatal.
  }
}

function Badge({
  ok,
  label,
}: {
  ok: boolean | "loading";
  label: string;
}) {
  const color =
    ok === true
      ? "var(--charm-cyan)"
      : ok === false
      ? "var(--charm-amber)"
      : "var(--charm-muted)";
  const dot =
    ok === true
      ? "oklch(0.65 0.18 175)"
      : ok === false
      ? "oklch(0.7 0.18 60)"
      : "oklch(0.65 0 0)";
  return (
    <span className="inline-flex items-center gap-1.5 font-jetbrains text-xs" style={{ color }}>
      <span className="inline-block w-2 h-2 rounded-full" style={{ background: dot }} />
      {label}
    </span>
  );
}

function StepHeader({ step, blurb }: { step: number; blurb: string }) {
  const meta = STEPS.find((s) => s.id === step);
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2">
        <h2
          className="font-jetbrains text-base"
          style={{ color: "var(--charm-text)" }}
        >
          step {step} · {meta?.label}
        </h2>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  className="text-xs font-jetbrains rounded-full px-1.5"
                  style={{
                    color: "var(--charm-muted)",
                    border: "1px solid var(--charm-border)",
                  }}
                >
                  ?
                </button>
              }
            />
            <TooltipContent className="max-w-xs">{blurb}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  );
}

function Breadcrumb({
  step,
  setStep,
  canGoTo,
}: {
  step: StepId;
  setStep: (s: StepId) => void;
  canGoTo: (s: StepId) => boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-6">
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
              opacity: enabled ? 1 : 0.5,
              cursor: enabled ? "pointer" : "not-allowed",
            }}
          >
            {s.id}. {s.label}
          </button>
        );
      })}
    </div>
  );
}

// ---------- Step components ----------

function Step1Preflight({
  status,
  refresh,
  onContinue,
}: {
  status: CalibrationStatus | null;
  refresh: () => void;
  onContinue: () => void;
}) {
  return (
    <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
      <CardContent className="p-5 flex flex-col gap-4">
        <div className="flex flex-wrap gap-4">
          <Badge
            ok={status?.board_calibration_present ?? "loading"}
            label={
              status?.board_calibration_present
                ? `board calibration saved${
                    status.board_calibration_age_seconds != null
                      ? ` (${Math.round(status.board_calibration_age_seconds / 60)} min ago)`
                      : ""
                  }`
                : "board calibration missing"
            }
          />
          <Badge
            ok={status?.inner_warp_present ?? "loading"}
            label={
              status?.inner_warp_present
                ? "inner-warp calibration saved"
                : "inner-warp calibration missing"
            }
          />
          <Badge
            ok={status?.camera_reachable ?? "loading"}
            label={status?.camera_reachable ? "camera reachable" : "camera offline"}
          />
        </div>

        <div className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
          If a badge is amber, fix it before continuing. Open the calibration tools below if needed.
        </div>

        <ArucoCalibration embedded />

        <div className="flex gap-2 pt-2">
          <Button size="sm" variant="outline" onClick={refresh}>
            re-check
          </Button>
          <Button
            size="sm"
            disabled={
              !status?.board_calibration_present ||
              !status?.inner_warp_present ||
              !status?.camera_reachable
            }
            onClick={onContinue}
          >
            continue
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Step2PickSource({
  sources,
  refresh,
  picked,
  setPicked,
  outputName,
  setOutputName,
  onContinue,
}: {
  sources: CnnSourceDatasetMeta[];
  refresh: () => void;
  picked: string | null;
  setPicked: (n: string | null) => void;
  outputName: string;
  setOutputName: (n: string) => void;
  onContinue: () => void;
}) {
  return (
    <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
      <CardContent className="p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
            {sources.length} dataset{sources.length === 1 ? "" : "s"} found in labeled_datasets/
          </span>
          <Button size="sm" variant="outline" onClick={refresh}>
            refresh
          </Button>
        </div>

        <div className="flex flex-col gap-2">
          {sources.length === 0 && (
            <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
              No source datasets yet — run the Labeling Wizard first.
            </span>
          )}
          {sources.map((s) => {
            const active = picked === s.name;
            return (
              <button
                key={s.name}
                onClick={() => setPicked(s.name)}
                className="text-left px-3 py-2 rounded-md text-xs font-jetbrains"
                style={{
                  background: active ? "oklch(from var(--charm-cyan) l c h / 0.1)" : "var(--charm-card)",
                  border: active ? "1px solid var(--charm-cyan)" : "1px solid var(--charm-border)",
                  color: "var(--charm-text)",
                }}
              >
                <div className="flex justify-between">
                  <span style={{ color: active ? "var(--charm-cyan)" : "var(--charm-text)" }}>{s.name}</span>
                  <span style={{ color: "var(--charm-muted)" }}>{s.total_frames} frames</span>
                </div>
                <div className="mt-1" style={{ color: "var(--charm-muted)" }}>
                  empty: {s.empty_frames} · white: {s.white_frames} on {s.white_squares} sq · black: {s.black_frames} on {s.black_squares} sq
                </div>
              </button>
            );
          })}
        </div>

        <Separator />

        <div className="flex items-center gap-3">
          <span className="text-xs font-jetbrains shrink-0" style={{ color: "var(--charm-muted)" }}>
            output name:
          </span>
          <Input
            value={outputName}
            onChange={(e) => setOutputName(e.target.value)}
            placeholder="e.g. v1"
            className="max-w-xs"
          />
          <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
            (saved as cnn_{outputName || "<name>"})
          </span>
        </div>

        <Button size="sm" disabled={!picked || !outputName.trim()} onClick={onContinue}>
          continue
        </Button>
      </CardContent>
    </Card>
  );
}

function Step3Build({
  source,
  outputName,
  buildId,
  startBuild,
  buildStatus,
  preview,
  loadPreview,
  onContinue,
}: {
  source: string | null;
  outputName: string;
  buildId: string | null;
  startBuild: () => void;
  buildStatus: CnnBuildStatus | null;
  preview: Record<string, string[]> | null;
  loadPreview: () => void;
  onContinue: () => void;
}) {
  const pct =
    buildStatus && buildStatus.frames_total > 0
      ? Math.round((buildStatus.frames_done / buildStatus.frames_total) * 100)
      : 0;
  const finished = buildStatus?.finished === true && !buildStatus?.error;

  return (
    <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
      <CardContent className="p-5 flex flex-col gap-4">
        <div className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
          source: <span style={{ color: "var(--charm-text)" }}>{source ?? "(none)"}</span> · output:{" "}
          <span style={{ color: "var(--charm-text)" }}>cnn_{outputName}</span>
        </div>

        {!buildId && (
          <Button size="sm" onClick={startBuild} disabled={!source || !outputName.trim()}>
            start build
          </Button>
        )}

        {buildStatus && (
          <div>
            <div className="flex justify-between text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
              <span>
                {buildStatus.frames_done} / {buildStatus.frames_total} frames
              </span>
              <span>{pct}%</span>
            </div>
            <div className="h-2 rounded-sm mt-1" style={{ background: "oklch(0.3 0 0)" }}>
              <div
                className="h-2 rounded-sm transition-all"
                style={{ width: `${pct}%`, background: "var(--charm-cyan)" }}
              />
            </div>
            <div className="text-xs font-jetbrains mt-2" style={{ color: "var(--charm-muted)" }}>
              {buildStatus.current_file && `current: ${buildStatus.current_file}`}
            </div>
            <div className="text-xs font-jetbrains mt-1" style={{ color: "var(--charm-muted)" }}>
              cells:{" "}
              {Object.entries(buildStatus.cells_written_by_class)
                .map(([k, v]) => `${k}=${v}`)
                .join(" · ")}
            </div>
            {buildStatus.error && (
              <div className="mt-2 text-xs font-jetbrains" style={{ color: "var(--charm-amber)" }}>
                build failed: {buildStatus.error}
              </div>
            )}
          </div>
        )}

        {finished && (
          <>
            <Button size="sm" variant="outline" onClick={loadPreview}>
              show preview crops
            </Button>
            {preview && (
              <div className="flex flex-col gap-3">
                {Object.entries(preview).map(([key, crops]) => (
                  <div key={key}>
                    <div className="text-xs font-jetbrains mb-1" style={{ color: "var(--charm-muted)" }}>
                      {key} ({crops.length})
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {crops.map((b64, i) => (
                        <img
                          key={i}
                          src={imageSrc(b64)}
                          alt={`${key}-${i}`}
                          className="rounded border"
                          style={{
                            width: 56,
                            height: 56,
                            borderColor: "var(--charm-border)",
                            imageRendering: "pixelated",
                          }}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <Button size="sm" onClick={onContinue}>
              continue
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function LiveChart({ history }: { history: { epoch: number; train_acc: number; val_acc: number; train_loss: number; val_loss: number }[] }) {
  // Plain SVG so we don't pull a chart library; package.json has no chart dep.
  const W = 480;
  const H = 160;
  const padL = 36;
  const padB = 22;
  const padT = 10;
  const padR = 10;

  if (history.length === 0) {
    return <div className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>waiting for epoch 1…</div>;
  }
  const xMax = Math.max(1, history[history.length - 1].epoch);
  const yMax = 1.0;
  const xy = (epoch: number, val: number) => {
    const x = padL + ((W - padL - padR) * (epoch - 1)) / Math.max(1, xMax - 1 || 1);
    const y = padT + (H - padT - padB) * (1 - val / yMax);
    return [x, y];
  };
  const path = (key: "train_acc" | "val_acc") =>
    history
      .map((h, i) => {
        const [x, y] = xy(h.epoch, Math.max(0, Math.min(1, h[key])));
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  return (
    <svg width={W} height={H} className="rounded" style={{ background: "oklch(0.18 0 0)" }}>
      {[0.25, 0.5, 0.75, 1.0].map((g) => {
        const [_, y] = xy(1, g);
        return (
          <g key={g}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="oklch(0.3 0 0)" strokeWidth="1" />
            <text x={2} y={y + 3} fill="oklch(0.6 0 0)" fontSize="9" fontFamily="monospace">
              {g.toFixed(2)}
            </text>
          </g>
        );
      })}
      <path d={path("train_acc")} stroke="oklch(0.7 0.18 220)" strokeWidth="1.8" fill="none" />
      <path d={path("val_acc")} stroke="oklch(0.75 0.18 175)" strokeWidth="1.8" fill="none" />
      <text x={padL + 6} y={padT + 12} fontSize="9" fontFamily="monospace" fill="oklch(0.7 0.18 220)">
        train_acc {history[history.length - 1].train_acc.toFixed(3)}
      </text>
      <text x={padL + 130} y={padT + 12} fontSize="9" fontFamily="monospace" fill="oklch(0.75 0.18 175)">
        val_acc {history[history.length - 1].val_acc.toFixed(3)}
      </text>
      <text x={W - padR - 60} y={H - 6} fontSize="9" fontFamily="monospace" fill="oklch(0.55 0 0)">
        epoch {history[history.length - 1].epoch}/{Math.max(...history.map((h) => h.epoch))}
      </text>
    </svg>
  );
}

function Step4Train({
  dataset,
  trainJobId,
  trainStatus,
  startTrain,
  artifacts,
  loadArtifacts,
  onContinue,
}: {
  dataset: string | null;
  trainJobId: string | null;
  trainStatus: CnnTrainStatus | null;
  startTrain: (epochs: number) => void;
  artifacts: CnnTrainArtifacts | null;
  loadArtifacts: () => void;
  onContinue: () => void;
}) {
  const [epochs, setEpochs] = useState(20);
  const [history, setHistory] = useState<{ epoch: number; train_acc: number; val_acc: number; train_loss: number; val_loss: number }[]>([]);

  useEffect(() => {
    if (
      trainStatus &&
      trainStatus.epoch > 0 &&
      trainStatus.train_acc != null &&
      trainStatus.val_acc != null &&
      trainStatus.train_loss != null &&
      trainStatus.val_loss != null
    ) {
      setHistory((prev) => {
        if (prev.length > 0 && prev[prev.length - 1].epoch === trainStatus.epoch) return prev;
        return [
          ...prev,
          {
            epoch: trainStatus.epoch,
            train_acc: trainStatus.train_acc!,
            val_acc: trainStatus.val_acc!,
            train_loss: trainStatus.train_loss!,
            val_loss: trainStatus.val_loss!,
          },
        ];
      });
    }
  }, [trainStatus?.epoch, trainStatus?.train_acc, trainStatus?.val_acc, trainStatus?.train_loss, trainStatus?.val_loss]);

  useEffect(() => {
    if (trainStatus?.finished && !trainStatus.error && trainStatus.run_id) {
      loadArtifacts();
    }
  }, [trainStatus?.finished, trainStatus?.error, trainStatus?.run_id, loadArtifacts]);

  return (
    <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
      <CardContent className="p-5 flex flex-col gap-4">
        <div className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
          training dataset:{" "}
          <span style={{ color: "var(--charm-text)" }}>{dataset ?? "(none)"}</span>
        </div>

        {!trainJobId && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
              epochs:
            </span>
            <Input
              type="number"
              min={1}
              max={100}
              value={epochs}
              onChange={(e) => setEpochs(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
              className="max-w-24"
            />
            <Button size="sm" onClick={() => startTrain(epochs)} disabled={!dataset}>
              start training
            </Button>
          </div>
        )}

        {trainStatus && (
          <>
            <div className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
              run: <span style={{ color: "var(--charm-text)" }}>{trainStatus.run_id}</span> · epoch{" "}
              {trainStatus.epoch}/{trainStatus.total_epochs}
              {trainStatus.error && (
                <span style={{ color: "var(--charm-amber)" }}> — error: {trainStatus.error}</span>
              )}
            </div>
            <LiveChart history={history} />
          </>
        )}

        {artifacts && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {artifacts.training_curves_png && (
                <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
                  <CardHeader className="px-3 py-2">
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                      Training curves
                    </span>
                  </CardHeader>
                  <CardContent className="p-0">
                    <img
                      src={`data:image/png;base64,${artifacts.training_curves_png}`}
                      alt="training curves"
                      className="w-full object-contain"
                      style={{ background: "white" }}
                    />
                  </CardContent>
                </Card>
              )}
              {artifacts.confusion_matrix_png && (
                <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
                  <CardHeader className="px-3 py-2">
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                      Confusion matrix (val)
                    </span>
                  </CardHeader>
                  <CardContent className="p-0">
                    <img
                      src={`data:image/png;base64,${artifacts.confusion_matrix_png}`}
                      alt="confusion matrix"
                      className="w-full object-contain"
                      style={{ background: "white" }}
                    />
                  </CardContent>
                </Card>
              )}
            </div>
            {artifacts.metrics?.per_class && (
              <div>
                <p className="text-xs font-jetbrains mb-1" style={{ color: "var(--charm-muted)" }}>
                  Per-class F1
                </p>
                <table className="text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                  <thead>
                    <tr style={{ color: "var(--charm-muted)" }}>
                      <th className="text-left pr-3">class</th>
                      <th className="text-right px-3">precision</th>
                      <th className="text-right px-3">recall</th>
                      <th className="text-right px-3">F1</th>
                      <th className="text-right pl-3">support</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(artifacts.metrics.per_class).map(([cls, m]) => (
                      <tr key={cls}>
                        <td className="pr-3">{cls}</td>
                        <td className="text-right px-3">{(m.precision * 100).toFixed(1)}%</td>
                        <td className="text-right px-3">{(m.recall * 100).toFixed(1)}%</td>
                        <td className="text-right px-3">{(m.f1 * 100).toFixed(1)}%</td>
                        <td className="text-right pl-3">{m.support}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Button size="sm" onClick={onContinue}>
              continue
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Step5Activate({
  models,
  active,
  refresh,
  onActivate,
  onContinue,
}: {
  models: CnnModelMeta[];
  active: CnnActiveModel | null;
  refresh: () => void;
  onActivate: (run_id: string) => void;
  onContinue: () => void;
}) {
  return (
    <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
      <CardContent className="p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
            {models.length} trained model{models.length === 1 ? "" : "s"}
          </span>
          <Button size="sm" variant="outline" onClick={refresh}>
            refresh
          </Button>
        </div>

        <div className="flex flex-col gap-2">
          {models.length === 0 && (
            <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
              No trained models yet. Go back to step 4.
            </span>
          )}
          {models.map((m) => {
            const isActive = active?.run_id === m.run_id;
            return (
              <div
                key={m.run_id}
                className="flex items-center justify-between px-3 py-2 rounded-md"
                style={{
                  background: isActive ? "oklch(from var(--charm-cyan) l c h / 0.1)" : "var(--charm-card)",
                  border: isActive ? "1px solid var(--charm-cyan)" : "1px solid var(--charm-border)",
                }}
              >
                <div className="text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                  <div style={{ color: isActive ? "var(--charm-cyan)" : "var(--charm-text)" }}>{m.run_id}</div>
                  <div style={{ color: "var(--charm-muted)" }}>
                    dataset: {m.dataset ?? "?"} · val{" "}
                    {m.val_acc != null ? `${(m.val_acc * 100).toFixed(1)}%` : "?"}
                  </div>
                </div>
                <Button size="sm" variant={isActive ? "outline" : "default"} onClick={() => onActivate(m.run_id)}>
                  {isActive ? "active" : "activate"}
                </Button>
              </div>
            );
          })}
        </div>

        <Button size="sm" disabled={!active?.run_id} onClick={onContinue}>
          continue
        </Button>
      </CardContent>
    </Card>
  );
}

// ---------- Page ----------

export default function CnnWizardPage() {
  const initial = typeof window === "undefined" ? null : loadState();
  const [step, setStepRaw] = useState<StepId>(initial?.step ?? 1);
  const [pickedSource, setPickedSource] = useState<string | null>(initial?.pickedSource ?? null);
  const [outputName, setOutputName] = useState<string>(initial?.outputName ?? "v1");
  const [buildId, setBuildId] = useState<string | null>(initial?.buildId ?? null);
  const [builtOutput, setBuiltOutput] = useState<string | null>(initial?.builtOutput ?? null);
  const [trainJobId, setTrainJobId] = useState<string | null>(initial?.trainJobId ?? null);
  const [trainRunId, setTrainRunId] = useState<string | null>(initial?.trainRunId ?? null);

  const setStep = useCallback((s: StepId) => {
    setStepRaw(s);
  }, []);

  // persist on every change
  useEffect(() => {
    saveState({ step, buildId, builtOutput, trainJobId, trainRunId, pickedSource, outputName });
  }, [step, buildId, builtOutput, trainJobId, trainRunId, pickedSource, outputName]);

  // ---- step 1 ----
  const [calStatus, setCalStatus] = useState<CalibrationStatus | null>(null);
  const refreshStatus = useCallback(async () => {
    try {
      setCalStatus(await api.getCalibrationStatus());
    } catch {
      setCalStatus(null);
    }
  }, []);
  useEffect(() => {
    refreshStatus();
    const t = setInterval(refreshStatus, 5000);
    return () => clearInterval(t);
  }, [refreshStatus]);

  // ---- step 2 ----
  const [sources, setSources] = useState<CnnSourceDatasetMeta[]>([]);
  const refreshSources = useCallback(async () => {
    try {
      const r = await api.cnnListSourceDatasets();
      setSources(r.datasets);
    } catch {
      setSources([]);
    }
  }, []);
  useEffect(() => {
    if (step === 2) refreshSources();
  }, [step, refreshSources]);

  // ---- step 3 ----
  const [buildStatus, setBuildStatus] = useState<CnnBuildStatus | null>(null);
  const [preview, setPreview] = useState<Record<string, string[]> | null>(null);
  const buildPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!buildId) {
      setBuildStatus(null);
      return;
    }
    const tick = async () => {
      try {
        const s = await api.cnnBuildStatus(buildId);
        setBuildStatus(s);
        if (s.finished && buildPollRef.current) {
          clearInterval(buildPollRef.current);
          buildPollRef.current = null;
        }
      } catch {
        // keep polling
      }
    };
    tick();
    buildPollRef.current = setInterval(tick, 500);
    return () => {
      if (buildPollRef.current) clearInterval(buildPollRef.current);
      buildPollRef.current = null;
    };
  }, [buildId]);

  const startBuild = useCallback(async () => {
    if (!pickedSource || !outputName.trim()) return;
    setPreview(null);
    try {
      const r = await api.cnnBuildDataset({ source: pickedSource, output: outputName.trim() });
      setBuildId(r.build_id);
      setBuiltOutput(`cnn_${outputName.trim()}`);
    } catch (e) {
      setBuildStatus({
        frames_done: 0,
        frames_total: 0,
        current_file: "",
        cells_written_by_class: { empty: 0, white: 0, black: 0 },
        finished: true,
        error: (e as Error).message,
        report: null,
        started_at: Date.now() / 1000,
      });
    }
  }, [pickedSource, outputName]);

  const loadPreview = useCallback(async () => {
    if (!builtOutput) return;
    try {
      const r = await api.cnnDatasetPreview(builtOutput);
      setPreview(r.preview);
    } catch {
      setPreview(null);
    }
  }, [builtOutput]);

  // ---- step 4 ----
  const [trainStatus, setTrainStatus] = useState<CnnTrainStatus | null>(null);
  const [artifacts, setArtifacts] = useState<CnnTrainArtifacts | null>(null);
  const trainPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!trainJobId) {
      setTrainStatus(null);
      return;
    }
    const tick = async () => {
      try {
        const s = await api.cnnTrainStatus(trainJobId);
        setTrainStatus(s);
        if (s.finished && trainPollRef.current) {
          clearInterval(trainPollRef.current);
          trainPollRef.current = null;
        }
      } catch {
        // keep polling
      }
    };
    tick();
    trainPollRef.current = setInterval(tick, 1500);
    return () => {
      if (trainPollRef.current) clearInterval(trainPollRef.current);
      trainPollRef.current = null;
    };
  }, [trainJobId]);

  const startTrain = useCallback(
    async (epochs: number) => {
      if (!builtOutput) return;
      try {
        const r = await api.cnnTrain({ dataset: builtOutput, epochs });
        setTrainJobId(r.job_id);
        setTrainRunId(r.run_id);
        setArtifacts(null);
      } catch (e) {
        setTrainStatus({
          run_id: "",
          dataset: builtOutput,
          epoch: 0,
          total_epochs: epochs,
          train_loss: null,
          train_acc: null,
          val_loss: null,
          val_acc: null,
          finished: true,
          error: (e as Error).message,
          started_at: Date.now() / 1000,
        });
      }
    },
    [builtOutput],
  );

  const loadArtifacts = useCallback(async () => {
    if (!trainRunId) return;
    try {
      setArtifacts(await api.cnnTrainArtifacts(trainRunId));
    } catch {
      setArtifacts(null);
    }
  }, [trainRunId]);

  // ---- step 5 ----
  const [models, setModels] = useState<CnnModelMeta[]>([]);
  const [active, setActive] = useState<CnnActiveModel | null>(null);
  const refreshModels = useCallback(async () => {
    try {
      const r = await api.cnnListModels();
      setModels(r.models);
    } catch {
      setModels([]);
    }
    try {
      setActive(await api.cnnActiveModel());
    } catch {
      setActive(null);
    }
  }, []);
  useEffect(() => {
    if (step === 5 || step === 6) refreshModels();
  }, [step, refreshModels]);

  const activateModel = useCallback(async (run_id: string) => {
    try {
      await api.cnnActivateModel(run_id);
      await refreshModels();
    } catch {
      // refreshModels still shows the failure context
    }
  }, [refreshModels]);

  // ---- gating ----
  const calOk = !!(calStatus?.board_calibration_present && calStatus?.inner_warp_present && calStatus?.camera_reachable);
  const sourceOk = !!pickedSource && !!outputName.trim();
  const buildOk = !!buildStatus?.finished && !buildStatus?.error;
  const trainOk = !!trainStatus?.finished && !trainStatus?.error;
  const activateOk = !!active?.run_id;

  const canGoTo = useCallback(
    (s: StepId): boolean => {
      if (s <= 1) return true;
      if (s === 2) return calOk;
      if (s === 3) return calOk && sourceOk;
      if (s === 4) return calOk && sourceOk && buildOk;
      if (s === 5) return calOk && sourceOk && buildOk && trainOk;
      if (s === 6) return calOk && sourceOk && buildOk && trainOk && activateOk;
      return false;
    },
    [calOk, sourceOk, buildOk, trainOk, activateOk],
  );

  const blurb = useMemo(() => STEPS.find((s) => s.id === step)?.blurb ?? "", [step]);

  return (
    <div className="px-6 py-6 max-w-5xl mx-auto">
      <div className="mb-4">
        <h1 className="font-jetbrains text-lg" style={{ color: "var(--charm-text)" }}>
          CNN training & deployment wizard
        </h1>
        <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
          Walks you through training a per-cell piece classifier and using it live. Resumes after a tab close.
        </p>
      </div>

      <Breadcrumb step={step} setStep={setStep} canGoTo={canGoTo} />
      <StepHeader step={step} blurb={blurb} />

      {step === 1 && (
        <Step1Preflight status={calStatus} refresh={refreshStatus} onContinue={() => setStep(2)} />
      )}
      {step === 2 && (
        <Step2PickSource
          sources={sources}
          refresh={refreshSources}
          picked={pickedSource}
          setPicked={setPickedSource}
          outputName={outputName}
          setOutputName={setOutputName}
          onContinue={() => setStep(3)}
        />
      )}
      {step === 3 && (
        <Step3Build
          source={pickedSource}
          outputName={outputName}
          buildId={buildId}
          startBuild={startBuild}
          buildStatus={buildStatus}
          preview={preview}
          loadPreview={loadPreview}
          onContinue={() => setStep(4)}
        />
      )}
      {step === 4 && (
        <Step4Train
          dataset={builtOutput}
          trainJobId={trainJobId}
          trainStatus={trainStatus}
          startTrain={startTrain}
          artifacts={artifacts}
          loadArtifacts={loadArtifacts}
          onContinue={() => setStep(5)}
        />
      )}
      {step === 5 && (
        <Step5Activate
          models={models}
          active={active}
          refresh={refreshModels}
          onActivate={activateModel}
          onContinue={() => setStep(6)}
        />
      )}
      {step === 6 && (
        <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
          <CardContent className="p-5">
            {!active?.run_id ? (
              <div className="text-xs font-jetbrains" style={{ color: "var(--charm-amber)" }}>
                No active model — go back to step 5 to activate one.
              </div>
            ) : !calOk ? (
              <div className="text-xs font-jetbrains" style={{ color: "var(--charm-amber)" }}>
                Calibration missing — go back to step 1 to fix it.
              </div>
            ) : (
              <CnnScanPanel />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
