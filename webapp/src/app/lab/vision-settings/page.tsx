"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, CnnActiveModel, CnnModelMeta, CvRouterConfig, ValidatedDatasetStats } from "@/lib/api";
import { DEFAULT_PARAMS } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { HelpCircle, Loader2, Zap } from "lucide-react";

const OCCUPANCY_STORAGE_KEY = "charm.occupancy-threshold";

function Help({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger render={
        <span className="cursor-help inline-flex items-center">
          <HelpCircle className="size-3" style={{ color: "var(--charm-muted)", opacity: 0.6 }} />
        </span>
      } />
      <TooltipContent className="max-w-xs font-jetbrains text-[11px]">{text}</TooltipContent>
    </Tooltip>
  );
}

function SectionLabel({
  label,
  color,
  description,
}: {
  label: string;
  color: string;
  description: string;
}) {
  return (
    <div className="mb-5">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="text-[10px] font-jetbrains font-semibold uppercase tracking-widest px-2 py-0.5 rounded"
          style={{
            color,
            border: `1px solid ${color}55`,
            background: `${color}11`,
          }}
        >
          {label}
        </span>
      </div>
      <p className="font-jetbrains text-[11px]" style={{ color: "var(--charm-muted)" }}>
        {description}
      </p>
    </div>
  );
}

export default function VisionSettingsPage() {
  const [cfg, setCfg] = useState<CvRouterConfig | null>(null);
  const [stats, setStats] = useState<ValidatedDatasetStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [datasetDraft, setDatasetDraft] = useState<string>("");
  const [showAdvancedVision, setShowAdvancedVision] = useState(false);
  const [occupancyThreshold, setOccupancyThreshold] = useState(DEFAULT_PARAMS.occupancy_threshold);
  const [cnnModels, setCnnModels] = useState<CnnModelMeta[]>([]);
  const [activeModel, setActiveModel] = useState<CnnActiveModel | null>(null);
  const [modelBusy, setModelBusy] = useState(false);

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

  const refreshModels = useCallback(async () => {
    try {
      const [models, active] = await Promise.all([api.cnnListModels(), api.cnnActiveModel()]);
      setCnnModels(models.models);
      setActiveModel(active);
    } catch {
      // non-fatal
    }
  }, []);

  const activateModel = useCallback(async (run_id: string) => {
    setModelBusy(true);
    try {
      await api.cnnActivateModel(run_id);
      await refreshModels();
      // Sync cnn_active status in cfg
      const updated = await api.getCvConfig();
      setCfg(updated);
    } catch {
      // non-fatal
    } finally {
      setModelBusy(false);
    }
  }, [refreshModels]);

  const refresh = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([api.getCvConfig(), api.validatedDatasetStats()]);
      setCfg(c);
      setStats(s);
      setDatasetDraft(c.dataset_name);
    } catch {
      // non-fatal
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { void refreshModels(); }, [refreshModels]);

  const patch = useCallback(async (p: Partial<CvRouterConfig>) => {
    setBusy(true);
    try {
      const updated = await api.setCvConfig(p);
      setCfg(updated);
      const s = await api.validatedDatasetStats();
      setStats(s);
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="mx-auto max-w-3xl p-6 space-y-8">
      <div>
        <Link href="/" className="font-jetbrains text-xs underline" style={{ color: "var(--charm-muted)" }}>
          ← dashboard
        </Link>
        <h1 className="mt-2 font-jetbrains text-xl font-semibold" style={{ color: "var(--charm-text)" }}>
          Vision Settings
        </h1>
        <p className="mt-1 font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
          Configure the CV router, classical vision pipeline, and CNN model behavior.
        </p>
      </div>

      {cfg && (
        <>
          {/* ── GENERAL CV ─────────────────────────────────────── */}
          <section>
            <SectionLabel
              label="GENERAL CV"
              color="var(--charm-muted)"
              description="Controls how the system routes between the classical vision pipeline and the CNN. These settings affect both."
            />

            <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
              <CardHeader className="px-5 pt-5 pb-2">
                <div className="flex items-center gap-2">
                  <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
                    Pipeline Router
                  </h2>
                  <Help text="Chooses which vision method runs first on each scan. The other method acts as automatic fallback if the primary fails after N attempts." />
                </div>
              </CardHeader>
              <CardContent className="p-5 space-y-5">
                {/* Primary pipeline */}
                <div>
                  <p className="font-jetbrains text-xs mb-2" style={{ color: "var(--charm-muted)" }}>
                    Primary pipeline — runs first; the other acts as fallback
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {(["vision", "cnn"] as const).map((m) => {
                      const active = cfg.primary === m;
                      const cnnUnavailable = m === "cnn" && !cfg.cnn_active;
                      return (
                        <button
                          key={m}
                          disabled={busy || cnnUnavailable}
                          onClick={() => { void patch({ primary: m }); }}
                          className="rounded border px-3 py-2 font-jetbrains text-xs"
                          style={{
                            borderColor: active ? "oklch(from var(--charm-cyan) l c h / 0.6)" : "var(--charm-border)",
                            color: active ? "var(--charm-cyan)" : "var(--charm-text)",
                            background: active ? "oklch(from var(--charm-cyan) l c h / 0.08)" : "transparent",
                            opacity: cnnUnavailable ? 0.5 : 1,
                            cursor: cnnUnavailable ? "not-allowed" : "pointer",
                          }}
                        >
                          <div className="font-semibold uppercase tracking-wider">
                            {m === "vision" ? "Vision" : "CNN"}
                          </div>
                          <div className="mt-0.5 text-[10px]" style={{ color: "var(--charm-muted)" }}>
                            {m === "vision" ? "classical pipeline" : cnnUnavailable ? "no model active" : "neural net"}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Attempts per pipeline */}
                <div>
                  <label className="font-jetbrains text-xs flex items-center justify-between" style={{ color: "var(--charm-text)" }}>
                    <span className="flex items-center gap-1.5">
                      Attempts per pipeline
                      <Help text="How many fresh-frame captures the primary pipeline gets before the fallback takes over. Higher = more retries but slower scans." />
                    </span>
                    <span style={{ color: "var(--charm-cyan)" }}>{cfg.attempts_each}</span>
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={10}
                    step={1}
                    value={cfg.attempts_each}
                    disabled={busy}
                    onChange={(e) => { void patch({ attempts_each: Number(e.target.value) }); }}
                    className="mt-2 w-full"
                  />
                  <p className="mt-1 font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                    Each scan grabs a fresh frame. The router tries primary up to {cfg.attempts_each}× then falls back.
                  </p>
                </div>
              </CardContent>
            </Card>
          </section>

          {/* ── VISION ─────────────────────────────────────────── */}
          <section>
            <SectionLabel
              label="VISION"
              color="var(--charm-cyan)"
              description="Settings specific to the classical computer vision pipeline (board detection, warp, occupancy scoring)."
            />

            <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
              <CardContent className="p-5 space-y-4">
                {/* Auto-save */}
                <div>
                  <label className="flex items-center gap-2 font-jetbrains text-xs" style={{ color: "var(--charm-text)" }}>
                    <input
                      type="checkbox"
                      checked={cfg.auto_save_validated}
                      disabled={busy}
                      onChange={(e) => { void patch({ auto_save_validated: e.target.checked }); }}
                    />
                    Auto-save validated frames to dataset
                  </label>
                  <p className="mt-1 font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                    When the vision pipeline produces a high-confidence board read, it saves the frame to the CNN
                    training dataset. Disable to curate captures manually.
                  </p>
                </div>

                {/* Advanced Vision Settings */}
                <div className="rounded-md border" style={{ borderColor: "var(--charm-border)" }}>
                  <button
                    type="button"
                    onClick={() => setShowAdvancedVision((v) => !v)}
                    className="flex w-full items-center justify-between px-4 py-3 font-jetbrains text-xs"
                    style={{ color: "var(--charm-text)" }}
                  >
                    <span className="font-semibold">Advanced Settings</span>
                    <span style={{ color: "var(--charm-muted)" }}>{showAdvancedVision ? "▲" : "▼"}</span>
                  </button>
                  {showAdvancedVision && (
                    <div className="space-y-5 border-t px-4 py-4" style={{ borderColor: "var(--charm-border)" }}>
                      {/* Occupancy threshold */}
                      <div>
                        <label className="flex items-center justify-between font-jetbrains text-xs mb-2" style={{ color: "var(--charm-text)" }}>
                          <span>Occupancy Threshold</span>
                          <span style={{ color: "var(--charm-cyan)" }}>{occupancyThreshold.toFixed(1)}</span>
                        </label>
                        <input
                          type="range"
                          min={0.5}
                          max={80}
                          step={0.5}
                          value={occupancyThreshold}
                          onChange={(e) => setOccupancyThreshold(Number(e.target.value))}
                          className="w-full"
                        />
                        <div className="mt-1 flex justify-between font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                          <span>0.5 — sensitive</span>
                          <span>default: {DEFAULT_PARAMS.occupancy_threshold}</span>
                          <span>80 — coarse</span>
                        </div>
                        <p className="mt-1 font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                          Minimum score for a square to count as occupied. Lower values detect fainter pieces.
                          Saved automatically and shared with the Vision Pipeline page.
                        </p>
                      </div>

                      {/* Warp calibration */}
                      <div
                        className="flex items-center justify-between gap-3 rounded-md border px-4 py-3"
                        style={{ borderColor: "var(--charm-border)" }}
                      >
                        <div>
                          <p className="font-jetbrains text-xs font-semibold" style={{ color: "var(--charm-text)" }}>
                            Set Image Warp
                          </p>
                          <p className="mt-0.5 font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                            Drag board corners to fix perspective. Opens the Vision Pipeline page.
                          </p>
                        </div>
                        <Link href="/lab">
                          <Button size="sm" variant="outline" className="font-jetbrains shrink-0">
                            Open →
                          </Button>
                        </Link>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </section>

          {/* ── CNN ────────────────────────────────────────────── */}
          <section>
            <SectionLabel
              label="CNN"
              color="var(--charm-amber)"
              description="Neural network model status and the dataset that grows during games for future training."
            />

            {/* Active model selector */}
            <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
              <CardHeader className="px-5 pt-5 pb-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
                      Active Model
                    </h2>
                    <Help text="The CNN model currently loaded for board recognition. Only one model can be active at a time. Activate a model to use it for game scans." />
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={refreshModels} disabled={modelBusy} className="font-jetbrains">
                      refresh
                    </Button>
                    <span
                      className="font-jetbrains text-[10px] px-2 py-0.5 rounded"
                      style={{
                        color: cfg.cnn_active ? "var(--charm-cyan)" : "var(--charm-amber)",
                        border: `1px solid ${cfg.cnn_active ? "oklch(from var(--charm-cyan) l c h / 0.4)" : "oklch(from var(--charm-amber) l c h / 0.4)"}`,
                        background: cfg.cnn_active
                          ? "oklch(from var(--charm-cyan) l c h / 0.08)"
                          : "oklch(from var(--charm-amber) l c h / 0.08)",
                      }}
                    >
                      {cfg.cnn_active ? "loaded" : "no model"}
                    </span>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="px-5 pb-5 space-y-2">
                {cnnModels.length === 0 ? (
                  <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                    No trained models found. Train one in the{" "}
                    <Link href="/lab/cnn" className="underline" style={{ color: "var(--charm-cyan)" }}>CNN Wizard</Link>.
                  </p>
                ) : (
                  cnnModels.map((m) => {
                    const isActive = activeModel?.run_id === m.run_id;
                    return (
                      <div
                        key={m.run_id}
                        className="flex items-center justify-between rounded-md border px-3 py-2"
                        style={{
                          borderColor: isActive ? "oklch(from var(--charm-cyan) l c h / 0.5)" : "var(--charm-border)",
                          background: isActive ? "oklch(from var(--charm-cyan) l c h / 0.07)" : "transparent",
                        }}
                      >
                        <div className="flex items-center gap-2">
                          <Zap className="size-3 shrink-0" style={{ color: isActive ? "var(--charm-cyan)" : "var(--charm-muted)" }} />
                          <div className="font-jetbrains text-xs">
                            <span style={{ color: isActive ? "var(--charm-cyan)" : "var(--charm-text)" }}>{m.run_id}</span>
                            <span className="ml-2" style={{ color: "var(--charm-muted)" }}>
                              {m.dataset ?? "?"} · val {m.val_acc != null ? `${(m.val_acc * 100).toFixed(1)}%` : "?"}
                            </span>
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant={isActive ? "outline" : "default"}
                          disabled={modelBusy || isActive}
                          onClick={() => void activateModel(m.run_id)}
                          className="font-jetbrains"
                        >
                          {modelBusy && isActive ? <Loader2 className="size-3 animate-spin" /> : isActive ? "active" : "activate"}
                        </Button>
                      </div>
                    );
                  })
                )}
              </CardContent>
            </Card>

            {/* Training dataset */}
            <Card className="mt-3" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
              <CardHeader className="px-5 pt-5 pb-2">
                <div className="flex items-center gap-2">
                  <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
                    Training Dataset
                  </h2>
                  <Help text="The dataset where validated board scans are saved automatically. Used to train new CNN models in the CNN Wizard." />
                </div>
              </CardHeader>
              <CardContent className="p-5 space-y-4">
                <div>
                  <label className="font-jetbrains text-xs" style={{ color: "var(--charm-text)" }}>
                    Dataset name
                  </label>
                  <div className="mt-1 flex gap-2">
                    <input
                      type="text"
                      value={datasetDraft}
                      disabled={busy}
                      onChange={(e) => setDatasetDraft(e.target.value)}
                      className="flex-1 rounded border px-2 py-1 font-jetbrains text-xs"
                      style={{
                        borderColor: "var(--charm-border)",
                        background: "transparent",
                        color: "var(--charm-text)",
                      }}
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || datasetDraft.trim() === cfg.dataset_name}
                      onClick={() => { void patch({ dataset_name: datasetDraft.trim() }); }}
                    >
                      save
                    </Button>
                  </div>
                  <p className="mt-1 font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                    Saves to <code>python_code/labeled_datasets/&lt;name&gt;/</code>. Reusing the same name across
                    games grows a single training set.
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Dataset stats */}
            {stats && (
              <Card className="mt-3" style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
                <CardHeader className="px-5 pt-5 pb-2 flex-row items-center justify-between">
                  <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
                    Dataset: {stats.dataset}
                  </h2>
                  <Button size="sm" variant="outline" onClick={refresh} disabled={busy}>
                    refresh
                  </Button>
                </CardHeader>
                <CardContent className="p-5 space-y-3">
                  {!stats.exists ? (
                    <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                      No captures yet. The dataset is created the first time a scan validates while auto-save is on.
                    </p>
                  ) : (
                    <>
                      <div className="grid grid-cols-4 gap-2">
                        {[
                          { label: "captures", value: stats.captures },
                          { label: "empty cells", value: stats.bulk_empty },
                          { label: "white cells", value: stats.bulk_white },
                          { label: "black cells", value: stats.bulk_black },
                        ].map(({ label, value }) => (
                          <div key={label} className="rounded-md border border-border px-3 py-2 text-center">
                            <p className="font-jetbrains text-[10px] uppercase" style={{ color: "var(--charm-muted)" }}>
                              {label}
                            </p>
                            <p className="mt-1 font-jetbrains text-lg" style={{ color: "var(--charm-cyan)" }}>
                              {value}
                            </p>
                          </div>
                        ))}
                      </div>

                      <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                        Path: <code style={{ color: "var(--charm-text)" }}>{stats.path}</code>
                      </p>

                      <div>
                        <p className="font-jetbrains text-xs mb-1" style={{ color: "var(--charm-muted)" }}>
                          Last 10 captures
                        </p>
                        <div className="space-y-1">
                          {stats.last.length === 0 && (
                            <p className="font-jetbrains text-[11px]" style={{ color: "var(--charm-muted)" }}>—</p>
                          )}
                          {stats.last.slice().reverse().map((c) => (
                            <div
                              key={c.capture_id}
                              className="rounded border border-border px-2 py-1 font-jetbrains text-[11px] flex items-center justify-between gap-2"
                            >
                              <span style={{ color: "var(--charm-muted)" }}>
                                {new Date(c.ts * 1000).toLocaleString()}
                              </span>
                              <span style={{ color: "var(--charm-cyan)" }}>{c.mode_used}</span>
                              <span style={{ color: "var(--charm-text)" }}>{c.move_uci ?? "init"}</span>
                              <span style={{ color: "var(--charm-muted)" }}>
                                e:{c.counts.empty} w:{c.counts.white} b:{c.counts.black}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            )}
          </section>
        </>
      )}
    </div>
  );
}
