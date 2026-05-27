"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, CvRouterConfig, ValidatedDatasetStats } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

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
                <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
                  Pipeline Router
                </h2>
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
                    <span>Attempts per pipeline</span>
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
              <CardContent className="p-5 space-y-3">
                <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
                  The <strong style={{ color: "var(--charm-text)" }}>occupancy threshold</strong> and warp calibration
                  are adjusted live on the{" "}
                  <Link
                    href="/lab"
                    className="underline"
                    style={{ color: "var(--charm-cyan)" }}
                  >
                    Vision Pipeline page
                  </Link>
                  .
                </p>

                <label className="flex items-center gap-2 font-jetbrains text-xs" style={{ color: "var(--charm-text)" }}>
                  <input
                    type="checkbox"
                    checked={cfg.auto_save_validated}
                    disabled={busy}
                    onChange={(e) => { void patch({ auto_save_validated: e.target.checked }); }}
                  />
                  Auto-save validated frames to dataset
                </label>
                <p className="font-jetbrains text-[10px]" style={{ color: "var(--charm-muted)" }}>
                  When the vision pipeline produces a high-confidence board read, it saves the frame to the CNN
                  training dataset below. Disable this if you want to curate captures manually.
                </p>
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

            <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
              <CardHeader className="px-5 pt-5 pb-2">
                <div className="flex items-center justify-between">
                  <h2 className="font-jetbrains text-sm font-semibold" style={{ color: "var(--charm-text)" }}>
                    Training Dataset
                  </h2>
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
                    {cfg.cnn_active ? "model loaded" : "no active model"}
                  </span>
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
