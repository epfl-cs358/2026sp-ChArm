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
  onPointMove,
  rawImage,
}: {
  points: PointMap;
  activeCorner: Corner | null;
  imgWidth: number;
  imgHeight: number;
  displayWidth: number;
  displayHeight: number;
  onClick: (x: number, y: number) => void;
  onPointMove: (corner: Corner, x: number, y: number) => void;
  rawImage: string | null;
}) {
  const [draggedCorner, setDraggedCorner] = useState<Corner | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number, y: number, imgX: number, imgY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const scaleX = displayWidth / imgWidth;
  const scaleY = displayHeight / imgHeight;

  const getCoords = (clientX: number, clientY: number) => {
    if (!svgRef.current) return { x: 0, y: 0, imgX: 0, imgY: 0 };
    const rect = svgRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const imgX = x / scaleX;
    const imgY = y / scaleY;
    return { x, y, imgX: Math.round(imgX), imgY: Math.round(imgY) };
  };

  const handleMouseDown = (e: React.MouseEvent, corner: Corner) => {
    e.stopPropagation();
    setDraggedCorner(corner);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const coords = getCoords(e.clientX, e.clientY);
    setHoverPos(coords);
    if (draggedCorner) {
      onPointMove(draggedCorner, coords.imgX, coords.imgY);
    }
  };

  const handleMouseUp = () => {
    setDraggedCorner(null);
  };

  const handleSvgClick = (e: React.MouseEvent) => {
    if (draggedCorner) return;
    const { imgX, imgY } = getCoords(e.clientX, e.clientY);
    onClick(imgX, imgY);
  };

  // Responsive magnifier position
  const magnifierSize = 160;
  const magnifierOffset = 20;
  let magnifierTop = 0;
  let magnifierLeft = 0;

  if (hoverPos) {
    // Default to top
    magnifierTop = hoverPos.y - magnifierSize - magnifierOffset;
    magnifierLeft = hoverPos.x - magnifierSize / 2;

    // Flip to bottom if overflow top
    if (magnifierTop < 10) {
      magnifierTop = hoverPos.y + magnifierOffset;
    }

    // Boundary checks for horizontal
    if (magnifierLeft < 10) magnifierLeft = 10;
    if (magnifierLeft + magnifierSize > displayWidth - 10) {
      magnifierLeft = displayWidth - magnifierSize - 10;
    }
    
    // Boundary check for bottom
    if (magnifierTop + magnifierSize > displayHeight - 10) {
      magnifierTop = displayHeight - magnifierSize - 10;
    }
  }

  return (
    <div 
      className="absolute inset-0 select-none"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoverPos(null)}
      onMouseUp={handleMouseUp}
    >
      <svg
        ref={svgRef}
        className="w-full h-full cursor-crosshair"
        onClick={handleSvgClick}
      >
        {/* draw quad outline */}
        {CORNERS.every((c) => points[c.key]) && (
          <polygon
            points={CORNERS.map(({ key }) => {
              const [x, y] = points[key]!;
              return `${x * scaleX},${y * scaleY}`;
            }).join(" ")}
            fill="rgba(0,212,255,0.08)"
            stroke="rgba(0,212,255,0.6)"
            strokeWidth={2}
            strokeDasharray="4 2"
          />
        )}
        {CORNERS.map(({ key, label, color }) => {
          const pt = points[key];
          if (!pt) return null;
          const [cx, cy] = [pt[0] * scaleX, pt[1] * scaleY];
          const isActive = draggedCorner === key || activeCorner === key;
          
          return (
            <g 
              key={key} 
              onMouseDown={(e) => handleMouseDown(e, key)}
              className="cursor-move"
            >
              <circle 
                cx={cx} cy={cy} r={isActive ? 12 : 8} 
                fill={`${color}${isActive ? "66" : "33"}`} 
                stroke={color} 
                strokeWidth={isActive ? 3 : 2} 
              />
              <text 
                x={cx + 14} y={cy + 4} 
                fill={color} 
                fontSize={12} 
                fontWeight="bold"
                fontFamily="monospace"
                className="drop-shadow-md"
              >
                {label}
              </text>
            </g>
          );
        })}
        {activeCorner && !draggedCorner && (
          <text x={12} y={24} fill="#00d4ff" fontSize={12} fontWeight="bold" fontFamily="monospace" className="drop-shadow-md">
            Click to set {activeCorner.replace("_", " ")}
          </text>
        )}
      </svg>

      {/* Magnifier */}
      {hoverPos && rawImage && (
        <div 
          className="pointer-events-none absolute border-2 border-cyan-DEFAULT rounded-full overflow-hidden shadow-2xl z-50 bg-black"
          style={{
            width: magnifierSize,
            height: magnifierSize,
            left: magnifierLeft,
            top: magnifierTop,
          }}
        >
          <div 
            style={{
              width: imgWidth,
              height: imgHeight,
              backgroundImage: `url(${imageSrc(rawImage)})`,
              backgroundSize: `${imgWidth * 4}px ${imgHeight * 4}px`, // 4x zoom
              backgroundPosition: `${-hoverPos.imgX * 4 + magnifierSize/2}px ${-hoverPos.imgY * 4 + magnifierSize/2}px`,
              backgroundRepeat: "no-repeat",
            }}
          />
          {/* Crosshair in magnifier */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none drop-shadow-[0_1px_1px_rgba(0,0,0,1)]">
            <div className="w-6 h-[2px] bg-[#00ff00] absolute" />
            <div className="h-6 w-[2px] bg-[#00ff00] absolute" />
          </div>
          <div className="absolute bottom-1 w-full text-center">
            <span className="bg-black/60 text-cyan-DEFAULT text-[10px] px-1 font-mono rounded">
              {hoverPos.imgX}, {hoverPos.imgY}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ManualCalibration({ imagePath: initialImagePath }: { imagePath?: string | null }) {
  const [calibration, setCalibration] = useState<CalibrationData>({ board: null, inner: null });
  const [rawImage, setRawImage] = useState<string | null>(null);
  const [currentImagePath, setCurrentImagePath] = useState<string | null>(initialImagePath ?? null);
  const [availableImages, setAvailableImages] = useState<{ name: string, path: string }[]>([]);
  const [firstWarpImage, setFirstWarpImage] = useState<string | null>(null);
  const [warpPreview, setWarpPreview] = useState<string | null>(null);
  const [stage, setStage] = useState<"board" | "inner">("board");
  const [activeCorner, setActiveCorner] = useState<Corner | null>("top_left");
  const [boardPoints, setBoardPoints] = useState<PointMap>({});
  const [innerPoints, setInnerPoints] = useState<PointMap>({});
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [imgNaturalSize, setImgNaturalSize] = useState({ w: 1, h: 1 });
  const [displaySize, setDisplaySize] = useState({ w: 1, h: 1 });
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadImages = useCallback(async () => {
    try {
      const { images } = await api.listImages();
      setAvailableImages(images);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadImages();
    });
  }, [loadImages]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const cal = await api.getCalibration();
        setCalibration(cal);
        
        let imgPath = currentImagePath;
        if (!imgPath) {
          try {
            const defaultRaw = await api.getRawImage();
            imgPath = defaultRaw.path;
            setCurrentImagePath(imgPath);
          } catch {
            // No images available yet
            setLoading(false);
            return;
          }
        }
        
        const raw = await api.readImage(imgPath);
        setRawImage(raw.image);
        setFirstWarpImage(null);
        setWarpPreview(null);
        
        if (cal.board) setBoardPoints(cal.board as PointMap);
        if (cal.inner) setInnerPoints(cal.inner as PointMap);
      } catch (e) {
        console.error("Failed to load calibration or image:", e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [currentImagePath]);

  const displayImage = stage === "inner" && firstWarpImage ? firstWarpImage : rawImage;
  const displayAlt = stage === "inner" && firstWarpImage ? "first warp" : "raw";

  const handleImageLoad = () => {
    if (imgRef.current) {
      setImgNaturalSize({ w: imgRef.current.naturalWidth, h: imgRef.current.naturalHeight });
      setDisplaySize({ w: imgRef.current.offsetWidth, h: imgRef.current.offsetHeight });
    }
  };

  const refreshWarpPreview = useCallback(async (applyInnerWarp: boolean) => {
    const result = await api.runPipeline({
      ...DEFAULT_PARAMS,
      auto_detect_board: false,
      apply_inner_warp: applyInnerWarp,
      image_path: currentImagePath ?? undefined,
    });
    setFirstWarpImage(result.first_warp);
    setWarpPreview(result.refined_warp);
  }, [currentImagePath]);

  const savePipelineSnapshotFromCalibration = useCallback(async (applyInnerWarp: boolean) => {
    const result = await api.runPipeline({
      ...DEFAULT_PARAMS,
      auto_detect_board: false,
      apply_inner_warp: applyInnerWarp,
      image_path: currentImagePath ?? undefined,
    });
    setFirstWarpImage(result.first_warp);
    setWarpPreview(result.refined_warp);

    return api.savePipelineSnapshot({
      params: {
        ...DEFAULT_PARAMS,
        auto_detect_board: false,
        apply_inner_warp: applyInnerWarp,
        image_path: currentImagePath ?? undefined,
      },
      images: {
        original: result.original,
        board_edges_debug: result.board_edges_debug,
        first_warp: result.first_warp,
        refined_warp: result.refined_warp,
        preprocessed: result.preprocessed,
        grid_debug: result.grid_debug,
        occupancy_debug: result.occupancy_debug,
        piece_color_debug: result.piece_color_debug,
      },
      result: {
        board_detection_mode: result.board_detection_mode,
        warp_error: result.warp_error,
        occupancy_matrix: result.occupancy_matrix,
        white_bitmap: result.white_bitmap,
        black_bitmap: result.black_bitmap,
        brightness_scores: result.brightness_scores,
        color_labels: result.color_labels,
        stats: result.stats,
        timings: result.timings,
      },
      labels: undefined,
      source_image: result.image_path ?? currentImagePath ?? undefined,
      name: `manual_calibration_${new Date().toISOString().replace(/[^0-9T]/g, "_")}`,
    });
  }, [currentImagePath]);

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

  const handlePointMove = useCallback((corner: Corner, x: number, y: number) => {
    if (stage === "board") {
      setBoardPoints((p) => ({ ...p, [corner]: [x, y] }));
    } else {
      setInnerPoints((p) => ({ ...p, [corner]: [x, y] }));
    }
  }, [stage]);

  const isComplete = (pts: PointMap) => CORNERS.every((c) => pts[c.key]);

  const useSavedCalibration = useCallback(() => {
    const savedPoints = stage === "board" ? calibration.board : calibration.inner;
    if (!savedPoints) {
      setSaveStatus(`No saved ${stage === "board" ? "board" : "inner"} calibration found.`);
      return;
    }

    if (stage === "board") {
      setBoardPoints(savedPoints as PointMap);
    } else {
      setInnerPoints(savedPoints as PointMap);
    }
    setActiveCorner(null);
    setSaveStatus(`Loaded saved ${stage === "board" ? "board" : "inner"} calibration.`);
  }, [calibration.board, calibration.inner, stage]);

  const handleStageChange = useCallback(async (nextStage: "board" | "inner") => {
    setStage(nextStage);
    setActiveCorner(isComplete(nextStage === "board" ? boardPoints : innerPoints) ? null : "top_left");

    if (nextStage === "inner" && !firstWarpImage) {
      setLoading(true);
      try {
        await refreshWarpPreview(false);
      } catch {
        setSaveStatus("Save board corners first to generate the inner-warp view.");
      } finally {
        setLoading(false);
      }
    }
  }, [boardPoints, firstWarpImage, innerPoints, refreshWarpPreview]);

  const save = async () => {
    setSaving(true);
    setSaveStatus(null);
    try {
      if (isComplete(boardPoints)) {
        const board = boardPoints as NonNullable<CalibrationData["board"]>;
        const result = await api.calibrateBoardCorners({
          top_left: board.top_left,
          top_right: board.top_right,
          bottom_right: board.bottom_right,
          bottom_left: board.bottom_left,
          image_path: currentImagePath ?? undefined,
          warp_size: DEFAULT_PARAMS.warp_size,
        });
        setCalibration((current) => ({ ...current, board: result.board }));
        setFirstWarpImage(result.first_warp);
        setWarpPreview(result.first_warp);
      }

      if (isComplete(innerPoints)) {
        await api.updateCalibration({ inner: innerPoints as CalibrationData["inner"] });
        setCalibration((current) => ({ ...current, inner: innerPoints as CalibrationData["inner"] }));
      }
      if (rawImage && isComplete(boardPoints)) {
        const snapshot = await savePipelineSnapshotFromCalibration(isComplete(innerPoints));
        setSaveStatus(`Saved JSON: ${snapshot.summary_path}`);
      } else {
        setSaveStatus("Saved ✓");
        setTimeout(() => setSaveStatus(null), 3000);
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
      const r = await api.captureFromCamera();
      setRawImage(r.image);
      setCurrentImagePath(r.path);
      setFirstWarpImage(null);
      setWarpPreview(null);
      loadImages();
    } catch (error) {
      setCaptureError(error instanceof Error ? error.message : "Capture failed");
    }
    setLoading(false);
  };

  const activePoints = stage === "board" ? boardPoints : innerPoints;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-mono font-semibold text-text-bright">Manual Chessboard Calibration</h1>
          <p className="text-text-muted text-sm mt-1">Select the four corners of the board for perspective correction. Drag points for precision.</p>
        </div>
        
        <div className="flex items-center gap-2">
          <label className="text-xs font-mono text-text-muted uppercase">Image Source:</label>
          <select 
            className="bg-background-soft border border-border rounded px-2 py-1 text-xs font-mono text-text outline-none focus:border-cyan-DEFAULT/50"
            value={currentImagePath || ""}
            onChange={(e) => setCurrentImagePath(e.target.value)}
          >
            {availableImages.map(img => (
              <option key={img.path} value={img.path}>{img.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
        <div className="space-y-4">
          {/* Stage toggle */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex rounded-md overflow-hidden border border-border">
              {(["board", "inner"] as const).map((s) => (
                <button
                  key={s}
	                  onClick={() => { void handleStageChange(s); }}
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
                    activeCorner === key ? "bg-white/5 opacity-100" : "opacity-40 hover:opacity-70"
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

            <button
              onClick={useSavedCalibration}
              disabled={stage === "board" ? !calibration.board : !calibration.inner}
              className="px-3 py-2 text-xs font-mono rounded-md border border-border text-text-muted hover:text-text hover:border-border-bright disabled:opacity-40 disabled:hover:text-text-muted disabled:hover:border-border"
            >
              Use saved calibration
            </button>

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
          <div className="card overflow-hidden border-border-bright shadow-lg" ref={containerRef}>
            {displayImage ? (
              <div className="relative inline-block w-full bg-black/20">
                <img
                  ref={imgRef}
                  src={imageSrc(displayImage)}
                  alt={displayAlt}
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
	                    onPointMove={handlePointMove}
	                    rawImage={displayImage}
		                  />
	                </div>
	              </div>
            ) : (
              <div className="h-96 flex flex-col items-center justify-center text-text-muted font-mono text-sm gap-4">
                <div className="flex flex-col items-center gap-2 opacity-50">
                  <span className="text-5xl">📸</span>
                  <span>Camera calibration needed</span>
                </div>
                <div className="flex flex-col gap-3 w-full max-w-xs">
                  <button
                    onClick={captureCamera}
                    disabled={loading}
                    className="btn-cyan w-full py-3 rounded-md text-sm font-mono font-bold"
                  >
                    {loading ? "Capturing..." : "Capture from camera"}
                  </button>
                  
                  <div className="relative">
                    <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-border"></div></div>
                    <div className="relative flex justify-center text-xs uppercase"><span className="bg-background px-2 text-text-muted">Or</span></div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] uppercase font-bold text-text-muted">Use from folder:</label>
                    <div className="flex flex-wrap gap-2 justify-center">
                      {availableImages.length > 0 ? (
                        availableImages.slice(0, 4).map(img => (
                          <button
                            key={img.path}
                            onClick={() => setCurrentImagePath(img.path)}
                            className="px-2 py-1 text-[10px] font-mono border border-border rounded hover:bg-white/5 hover:border-cyan-DEFAULT/50 transition-colors"
                          >
                            {img.name}
                          </button>
                        ))
                      ) : (
                        <span className="text-[10px] text-text-muted">No images found in folder</span>
                      )}
                    </div>
                  </div>
                </div>
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

          {/* Save button */}
          <div className="space-y-2">
            <button
              onClick={save}
              disabled={saving || (!isComplete(boardPoints) && !isComplete(innerPoints))}
              className="btn-cyan w-full py-4 rounded-md text-sm font-mono font-bold tracking-wider uppercase shadow-cyan"
            >
              {saving ? "Saving..." : "Save Calibration + Snapshot"}
            </button>
            {saveStatus && (
              <p className={`text-xs font-mono text-center py-2 px-2 rounded break-all ${saveStatus.startsWith("Error") ? "bg-red-500/10 text-red-400" : "bg-green-500/10 text-green-400"}`}>
                {saveStatus}
              </p>
            )}
            {!isComplete(boardPoints) && (
              <p className="text-[10px] font-mono text-text-muted text-center leading-relaxed">
                Please set all 4 board corners (TL, TR, BR, BL)<br/>to enable perspective warping.
              </p>
            )}
          </div>

          {/* Warp preview */}
          {warpPreview && (
            <div className="card overflow-hidden border-cyan-DEFAULT/30">
              <p className="text-xs font-mono font-bold text-cyan-DEFAULT px-3 py-2 border-b border-border bg-cyan-DEFAULT/5">
                Warp Preview
              </p>
              <img
                src={imageSrc(warpPreview)}
                alt="warp preview"
                className="w-full object-contain"
              />
            </div>
          )}

          <div className="card p-4 space-y-3 text-[11px] font-mono text-text-muted bg-white/[0.02]">
            <p className="text-text-bright font-bold">Calibration Guide:</p>
            <ul className="space-y-2 list-disc pl-4">
              <li>Click points in order: <span className="text-cyan-DEFAULT">TL</span> → <span className="text-green-DEFAULT">TR</span> → <span className="text-orange-DEFAULT">BR</span> → <span className="text-red-DEFAULT">BL</span></li>
              <li><span className="text-text-bright">Board Corners:</span> Click the exact outer edges of the 8x8 chessboard.</li>
              <li><span className="text-text-bright">Drag:</span> Click and drag any point to refine its position with the magnifier.</li>
              <li><span className="text-text-bright">Inner Warp:</span> Optional. Set these points on the first warped board, not on the raw image.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
