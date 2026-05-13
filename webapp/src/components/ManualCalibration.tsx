"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { api } from "@/lib/api";
import { imageSrc } from "@/lib/image";
import { CalibrationData, DEFAULT_PARAMS } from "@/lib/types";

type Corner = "top_left" | "top_right" | "bottom_right" | "bottom_left";
type Point = [number, number];
type PointMap = Partial<Record<Corner, Point>>;

const CORNERS: { key: Corner; label: string; color: string }[] = [
  { key: "top_left", label: "TL", color: "#00d4ff" },
  { key: "top_right", label: "TR", color: "#22c55e" },
  { key: "bottom_right", label: "BR", color: "#f59e0b" },
  { key: "bottom_left", label: "BL", color: "#ef4444" },
];

function PointOverlay({
  points,
  activeCorner,
  imgWidth,
  imgHeight,
  displayWidth,
  displayHeight,
  onClick,
}: {
  points: PointMap;
  activeCorner: Corner | null;
  imgWidth: number;
  imgHeight: number;
  displayWidth: number;
  displayHeight: number;
  onClick: (x: number, y: number) => void;
}) {
  const scaleX = displayWidth / imgWidth;
  const scaleY = displayHeight / imgHeight;

  return (
    <svg
      className="absolute inset-0 cursor-crosshair"
      width={displayWidth}
      height={displayHeight}
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const px = (e.clientX - rect.left) / scaleX;
        const py = (e.clientY - rect.top) / scaleY;
        onClick(Math.round(px), Math.round(py));
      }}
    >
      {/* draw quad outline */}
      {CORNERS.every((c) => points[c.key]) && (
        <polygon
          points={CORNERS.map(({ key }) => {
            const [x, y] = points[key]!;
            return `${x * scaleX},${y * scaleY}`;
          }).join(" ")}
          fill="rgba(0,212,255,0.08)"
          stroke="rgba(0,212,255,0.4)"
          strokeWidth={1.5}
          strokeDasharray="4 2"
        />
      )}
      {CORNERS.map(({ key, label, color }) => {
        const pt = points[key];
        if (!pt) return null;
        const [cx, cy] = [pt[0] * scaleX, pt[1] * scaleY];
        return (
          <g key={key}>
            <circle cx={cx} cy={cy} r={8} fill={`${color}33`} stroke={color} strokeWidth={2} />
            <text x={cx + 12} y={cy + 4} fill={color} fontSize={11} fontFamily="monospace">
              {label} [{pt[0]},{pt[1]}]
            </text>
          </g>
        );
      })}
      {activeCorner && (
        <text x={8} y={20} fill="#00d4ff" fontSize={11} fontFamily="monospace">
          Click to set {activeCorner.replace("_", " ")}
        </text>
      )}
    </svg>
  );
}

export default function ManualCalibration() {
  const [calibration, setCalibration] = useState<CalibrationData>({ board: null, inner: null });
  const [rawImage, setRawImage] = useState<string | null>(null);
  const [warpPreview, setWarpPreview] = useState<string | null>(null);
  const [stage, setStage] = useState<"board" | "inner">("board");
  const [activeCorner, setActiveCorner] = useState<Corner | null>("top_left");
  const [boardPoints, setBoardPoints] = useState<PointMap>({});
  const [innerPoints, setInnerPoints] = useState<PointMap>({});
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cameraUrl, setCameraUrl] = useState("http://172.21.73.228/capture");
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [imgNaturalSize, setImgNaturalSize] = useState({ w: 1, h: 1 });
  const [displaySize, setDisplaySize] = useState({ w: 1, h: 1 });
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [cal, raw] = await Promise.all([api.getCalibration(), api.getRawImage()]);
        setCalibration(cal);
        setRawImage(raw.image);
        if (cal.board) setBoardPoints(cal.board as PointMap);
        if (cal.inner) setInnerPoints(cal.inner as PointMap);
      } catch {
        try {
          const raw = await api.getRawImage();
          setRawImage(raw.image);
        } catch { /* no raw image available */ }
      }
    };
    load();
  }, []);

  const handleImageLoad = () => {
    if (imgRef.current) {
      setImgNaturalSize({ w: imgRef.current.naturalWidth, h: imgRef.current.naturalHeight });
      setDisplaySize({ w: imgRef.current.offsetWidth, h: imgRef.current.offsetHeight });
    }
  };

  const handleClick = useCallback((x: number, y: number) => {
    if (!activeCorner) return;
    const nextCorner: Record<Corner, Corner | null> = {
      top_left: "top_right",
      top_right: "bottom_right",
      bottom_right: "bottom_left",
      bottom_left: null,
    };
    if (stage === "board") {
      setBoardPoints((p) => ({ ...p, [activeCorner]: [x, y] }));
    } else {
      setInnerPoints((p) => ({ ...p, [activeCorner]: [x, y] }));
    }
    setActiveCorner(nextCorner[activeCorner]);
  }, [activeCorner, stage]);

  const isComplete = (pts: PointMap) => CORNERS.every((c) => pts[c.key]);

  const save = async () => {
    setSaving(true);
    setSaveStatus(null);
    try {
      const update: Partial<CalibrationData> = {};
      if (isComplete(boardPoints)) {
        update.board = boardPoints as CalibrationData["board"];
      }
      if (isComplete(innerPoints)) {
        update.inner = innerPoints as CalibrationData["inner"];
      }
      await api.updateCalibration(update);
      setSaveStatus("Saved ✓");
      setTimeout(() => setSaveStatus(null), 3000);

      // Run warp preview
      if (rawImage && isComplete(boardPoints)) {
        setLoading(true);
        try {
          const result = await api.runPipeline({ ...DEFAULT_PARAMS });
          setWarpPreview(result.refined_warp);
        } catch { /* no preview */ }
        setLoading(false);
      }
    } catch (e: unknown) {
      setSaveStatus(`Error: ${e instanceof Error ? e.message : "failed"}`);
    } finally {
      setSaving(false);
    }
  };

  const captureCamera = async () => {
    setLoading(true);
    setCaptureError(null);
    try {
      const r = await api.captureFromCamera(cameraUrl.trim() || undefined);
      setRawImage(r.image);
    } catch (error) {
      setCaptureError(error instanceof Error ? error.message : "Capture failed");
    }
    setLoading(false);
  };

  const activePoints = stage === "board" ? boardPoints : innerPoints;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-mono font-semibold text-text-bright">Do manual calibration on the 4 corners</h1>
        <p className="text-text-muted text-sm mt-1">Click the four board corners on the image to set perspective calibration.</p>
      </div>

      <div className="grid grid-cols-[1fr_320px] gap-6">
        <div className="space-y-4">
          {/* Stage toggle */}
          <div className="flex items-center gap-3">
            <div className="flex rounded-md overflow-hidden border border-border">
              {(["board", "inner"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => { setStage(s); setActiveCorner("top_left"); }}
                  className={`px-4 py-2 text-sm font-mono transition-colors ${
                    stage === s
                      ? "bg-cyan-glow text-cyan-DEFAULT"
                      : "text-text-muted hover:text-text"
                  }`}
                >
                  {s === "board" ? "Board Corners" : "Inner Warp"}{" "}
                  {isComplete(s === "board" ? boardPoints : innerPoints) && (
                    <span className="text-green-DEFAULT ml-1">✓</span>
                  )}
                </button>
              ))}
            </div>

            <div className="flex rounded-md overflow-hidden border border-border">
              {CORNERS.map(({ key, label, color }) => (
                <button
                  key={key}
                  onClick={() => setActiveCorner(key)}
                  className={`px-3 py-2 text-xs font-mono transition-all ${
                    activeCorner === key ? "opacity-100" : "opacity-40 hover:opacity-70"
                  }`}
                  style={{ color, borderLeft: "1px solid #1a2540" }}
                >
                  {activePoints[key] ? "●" : "○"} {label}
                </button>
              ))}
            </div>

            <button
              onClick={() => {
                if (stage === "board") setBoardPoints({});
                else setInnerPoints({});
                setActiveCorner("top_left");
              }}
              className="px-3 py-2 text-xs font-mono rounded-md border border-border text-text-muted hover:text-text hover:border-border-bright"
            >
              Clear
            </button>

            <input
              value={cameraUrl}
              onChange={(event) => setCameraUrl(event.target.value)}
              className="min-w-64 rounded-md border border-border bg-transparent px-3 py-2 text-xs font-mono"
              placeholder="http://<camera-ip>/capture"
            />
            <button
              onClick={captureCamera}
              disabled={loading}
              className="btn-cyan px-3 py-2 rounded-md text-xs font-mono disabled:opacity-50"
            >
              {loading ? "Capturing..." : "Capture"}
            </button>
          </div>
          {captureError && <p className="text-xs text-red-400 font-mono">{captureError}</p>}

          {/* Image with overlay */}
          <div className="card overflow-hidden" ref={containerRef}>
            {rawImage ? (
              <div className="relative inline-block w-full">
                <img
                  ref={imgRef}
                  src={imageSrc(rawImage)}
                  alt="raw"
                  className="w-full object-contain"
                  onLoad={handleImageLoad}
                  style={{ display: "block", userSelect: "none" }}
                />
                <div
                  className="absolute inset-0"
                  style={{ width: displaySize.w, height: displaySize.h }}
                >
                  <PointOverlay
                    points={activePoints}
                    activeCorner={activeCorner}
                    imgWidth={imgNaturalSize.w}
                    imgHeight={imgNaturalSize.h}
                    displayWidth={displaySize.w}
                    displayHeight={displaySize.h}
                    onClick={handleClick}
                  />
                </div>
              </div>
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-text-muted font-mono text-sm gap-2">
                <span className="text-3xl opacity-30">Camera</span>
                <span>No image — capture from camera or run pipeline first</span>
                <input
                  value={cameraUrl}
                  onChange={(event) => setCameraUrl(event.target.value)}
                  className="w-full max-w-sm rounded-md border border-border bg-transparent px-3 py-2 text-xs font-mono"
                  placeholder="http://<camera-ip>/capture"
                />
                <button
                  onClick={captureCamera}
                  disabled={loading}
                  className="btn-cyan px-4 py-2 rounded-md text-sm font-mono mt-2"
                >
                  {loading ? "Capturing..." : "Capture from camera"}
                </button>
                {captureError && (
                  <span className="max-w-sm text-center text-xs text-red-400">{captureError}</span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          {/* Current calibration values */}
          <div className="card p-4">
            <h2 className="text-xs font-mono font-semibold text-text-muted uppercase tracking-widest mb-3">
              {stage === "board" ? "Board Corners" : "Inner Warp"}
            </h2>
            {CORNERS.map(({ key, label, color }) => {
              const pt = activePoints[key];
              return (
                <div key={key} className="flex items-center justify-between py-1.5 border-b border-border last:border-0">
                  <span className="text-xs font-mono" style={{ color }}>{label}</span>
                  <span className="text-xs font-mono text-text">
                    {pt ? `[${pt[0]}, ${pt[1]}]` : <span className="text-text-muted">—</span>}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Existing calibration from JSON */}
          {(calibration.board || calibration.inner) && (
            <div className="card p-4">
              <h2 className="text-xs font-mono font-semibold text-text-muted uppercase tracking-widest mb-3">
                Saved in JSON
              </h2>
              {calibration.board && (
                <div className="mb-2">
                  <p className="text-xs text-cyan-DEFAULT font-mono mb-1">board_calibration.json</p>
                  {CORNERS.map(({ key, label }) => (
                    <div key={key} className="flex justify-between text-xs font-mono py-0.5">
                      <span className="text-text-muted">{label}</span>
                      <span className="text-text">
                        {calibration.board![key] ? `[${calibration.board![key].join(", ")}]` : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Save button */}
          <div className="space-y-2">
            <button
              onClick={save}
              disabled={saving || (!isComplete(boardPoints) && !isComplete(innerPoints))}
              className="btn-cyan w-full py-3 rounded-md text-sm font-mono font-semibold"
            >
              {saving ? "Saving..." : "Save Calibration"}
            </button>
            {saveStatus && (
              <p className={`text-xs font-mono text-center ${saveStatus.startsWith("Error") ? "text-red-DEFAULT" : "text-green-DEFAULT"}`}>
                {saveStatus}
              </p>
            )}
            {!isComplete(boardPoints) && (
              <p className="text-xs font-mono text-text-muted text-center">
                Set all 4 board corners to save
              </p>
            )}
          </div>

          {/* Warp preview */}
          {warpPreview && (
            <div className="card overflow-hidden">
              <p className="text-xs font-mono text-text-muted px-3 py-2 border-b border-border">
                Warp Preview
              </p>
              <img
                src={imageSrc(warpPreview)}
                alt="warp preview"
                className="w-full object-contain"
              />
            </div>
          )}

          <div className="text-xs font-mono text-text-muted">
            <p className="mb-1 text-text-muted/70">Click order: TL → TR → BR → BL</p>
            <p className="text-text-muted/70">Board corners = outer edges of board</p>
            <p className="text-text-muted/70">Inner warp = first square corners (post-warp)</p>
          </div>
        </div>
      </div>
    </div>
  );
}
