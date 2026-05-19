"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ArucoDetectResult } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ALL_SQUARES: string[] = (() => {
  const out: string[] = [];
  for (let rank = 1; rank <= 8; rank++) for (const f of "abcdefgh") out.push(`${f}${rank}`);
  return out;
})();

type Layout = Record<string, string>;

const DEFAULT_LAYOUT: Layout = { "0": "a8", "1": "h8", "2": "h1", "3": "a1" };

export default function ArucoCalibration({
  onApplied,
  embedded,
}: {
  onApplied?: (board: NonNullable<ArucoDetectResult["board"]>) => void;
  embedded?: boolean;
}) {
  const [layout, setLayout] = useState<Layout>(DEFAULT_LAYOUT);
  const [appliedLayout, setAppliedLayout] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ArucoDetectResult | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [markers, setMarkers] = useState<Record<number, string>>({});

  // Preload the 4 marker PNGs so the user can print them.
  useEffect(() => {
    let cancelled = false;
    Promise.all([0, 1, 2, 3].map((id) => api.getArucoMarker(id, 600))).then((arr) => {
      if (cancelled) return;
      const map: Record<number, string> = {};
      arr.forEach((m) => {
        map[m.marker_id] = m.image;
      });
      setMarkers(map);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLayoutChange = (id: string, sq: string) => {
    setLayout((prev) => ({ ...prev, [id]: sq.toLowerCase() }));
    setAppliedLayout(false);
  };

  const handleApplyLayout = () => {
    setError(null);
    const seen = new Set<string>();
    for (const id of Object.keys(layout)) {
      const sq = (layout[id] ?? "").toLowerCase();
      if (!ALL_SQUARES.includes(sq)) {
        setError(`Marker ID ${id}: invalid square "${layout[id]}"`);
        return;
      }
      if (seen.has(sq)) {
        setError(`Square ${sq} is assigned to two markers`);
        return;
      }
      seen.add(sq);
    }
    setAppliedLayout(true);
  };

  const detect = useCallback(
    async (save: boolean) => {
      if (!appliedLayout) {
        setError("Apply the layout first");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const r = await api.arucoDetect({
          capture: true,
          layout,
          save,
        });
        setResult(r);
        if (r.status === "incomplete") {
          setError(r.error ?? "Some markers were not detected");
        } else if (save) {
          setSavedAt(Date.now());
          if (r.board && onApplied) onApplied(r.board);
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [appliedLayout, layout, onApplied],
  );

  return (
    <div className={embedded ? "space-y-4" : "space-y-4 p-4"}>
      {!embedded && (
        <h2 className="text-base font-jetbrains font-semibold">ArUco board calibration</h2>
      )}
      <p className="text-xs text-muted-foreground font-jetbrains">
        Place 4 ArUco markers (DICT_4X4_50, IDs 0–3) on the squares below, centered.
        Print each marker at 3.75 cm wide. After Apply Calibration, you can remove the
        markers — the calibration captures only the camera↔board geometry.
      </p>

      {/* Layout chooser */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {Object.keys(DEFAULT_LAYOUT).map((id) => (
          <div key={id} className="space-y-1">
            <label className="font-jetbrains text-xs">ID {id} on square</label>
            <Input
              value={layout[id] ?? ""}
              onChange={(e) => handleLayoutChange(id, e.target.value)}
              className="font-jetbrains uppercase"
            />
          </div>
        ))}
      </div>
      <div className="flex gap-2 items-center">
        <Button
          size="sm"
          variant={appliedLayout ? "secondary" : "default"}
          onClick={handleApplyLayout}
        >
          {appliedLayout ? "Layout applied ✓" : "Apply layout"}
        </Button>
        <span className="text-xs text-muted-foreground font-jetbrains">
          Default: 0→a8, 1→h8, 2→h1, 3→a1 (board corner squares).
        </span>
      </div>

      {/* Printable markers */}
      <details className="rounded-md border p-2">
        <summary className="cursor-pointer text-xs font-jetbrains">
          Show printable markers (IDs 0–3)
        </summary>
        <div className="grid grid-cols-4 gap-3 mt-3">
          {[0, 1, 2, 3].map((id) => (
            <div key={id} className="flex flex-col items-center gap-1">
              {markers[id] && (
                <img
                  src={`data:image/png;base64,${markers[id]}`}
                  alt={`marker ${id}`}
                  className="w-full border bg-white"
                />
              )}
              <span className="text-[10px] font-jetbrains">
                ID {id} → {layout[String(id)]}
              </span>
              <a
                href={markers[id] ? `data:image/png;base64,${markers[id]}` : "#"}
                download={`aruco_${id}.png`}
                className="text-[10px] underline font-jetbrains"
              >
                download
              </a>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground font-jetbrains mt-2">
          Print at 3.75 cm wide (≈1.48 in). In your PDF viewer's print dialog disable
          "Fit to page" and use Actual Size, then crop/scale so the printed square
          measures exactly 3.75 cm with a ruler.
        </p>
      </details>

      {/* Actions */}
      <div className="flex gap-2 items-center flex-wrap">
        <Button onClick={() => detect(false)} disabled={busy || !appliedLayout}>
          {busy ? "Detecting…" : "Capture & detect"}
        </Button>
        <Button
          onClick={() => detect(true)}
          disabled={busy || !appliedLayout || result?.status !== "ok"}
          variant="default"
        >
          Apply calibration (save to board)
        </Button>
        {savedAt && (
          <span className="text-xs text-green-500 font-jetbrains">
            Saved ✓ {new Date(savedAt).toLocaleTimeString()}
          </span>
        )}
      </div>

      {error && (
        <div
          className="rounded-md border p-2 text-xs font-jetbrains"
          style={{
            borderColor: "var(--charm-red, #f87171)",
            color: "var(--charm-red, #f87171)",
            background: "color-mix(in oklab, var(--charm-red, #f87171) 8%, transparent)",
          }}
        >
          {error}
        </div>
      )}

      {/* Result preview */}
      {result && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {result.overlay && (
            <div>
              <p className="text-xs font-jetbrains mb-1">Detection overlay</p>
              <img
                src={`data:image/jpeg;base64,${result.overlay}`}
                alt="overlay"
                className="w-full rounded-md border"
              />
            </div>
          )}
          {result.first_warp && (
            <div>
              <p className="text-xs font-jetbrains mb-1">Resulting warp</p>
              <img
                src={`data:image/jpeg;base64,${result.first_warp}`}
                alt="warp"
                className="w-full rounded-md border"
              />
            </div>
          )}
          <div className="md:col-span-2 text-xs font-jetbrains space-y-1">
            <div>
              Detected:{" "}
              {(result.detections ?? []).map((d) => d.id).sort((a, b) => a - b).join(", ") || "none"}
            </div>
            {result.missing_ids && result.missing_ids.length > 0 && (
              <div className="text-amber-500">
                Missing IDs: {result.missing_ids.join(", ")}
              </div>
            )}
            {result.board && (
              <div className="font-mono">
                Corners — TL {result.board.top_left.join(",")} · TR{" "}
                {result.board.top_right.join(",")} · BR{" "}
                {result.board.bottom_right.join(",")} · BL{" "}
                {result.board.bottom_left.join(",")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
