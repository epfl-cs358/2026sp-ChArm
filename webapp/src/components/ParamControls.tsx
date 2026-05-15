"use client";

import { PipelineParams, DEFAULT_PARAMS } from "@/lib/types";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface SliderDef {
  key: keyof PipelineParams;
  label: string;
  description: string;
  min: number;
  max: number;
  step: number;
  unit?: string;
}

const BOARD_DETECTION_SLIDERS: SliderDef[] = [
  {
    key: "board_canny_low",
    label: "Edge Canny Low",
    description: "Seuil bas Canny pour trouver le contour externe du board sur l'image raw.",
    min: 5,
    max: 150,
    step: 5,
    unit: "0-255",
  },
  {
    key: "board_canny_high",
    label: "Edge Canny High",
    description: "Seuil haut Canny pour trouver le contour externe du board sur l'image raw.",
    min: 20,
    max: 300,
    step: 5,
    unit: "0-255",
  },
  {
    key: "board_dilation_iterations",
    label: "Edge Dilation",
    description: "Nombre de dilatations 3x3 après Canny. Plus haut connecte les bords, mais peut coller des objets au board.",
    min: 0,
    max: 4,
    step: 1,
  },
  {
    key: "board_min_area",
    label: "Min Contour Area",
    description: "Aire minimale d'un contour candidat en pixels raw. Monte-le pour ignorer de petits objets.",
    min: 1000,
    max: 30000,
    step: 500,
    unit: "px²",
  },
  {
    key: "board_max_side_ratio",
    label: "Max Side Ratio",
    description: "Ratio max entre le plus grand et le plus petit côté du quad. Plus haut accepte plus de perspective.",
    min: 1.0,
    max: 1.6,
    step: 0.01,
  },
  {
    key: "board_min_area_ratio",
    label: "Min Area Ratio",
    description: "Aire minimale du board par rapport à l'image raw.",
    min: 0.02,
    max: 0.3,
    step: 0.01,
  },
  {
    key: "board_max_area_ratio",
    label: "Max Area Ratio",
    description: "Aire maximale du board par rapport à l'image raw.",
    min: 0.3,
    max: 0.95,
    step: 0.01,
  },
  {
    key: "board_min_color_ratio",
    label: "Min Color Ratio",
    description: "Proportion minimale de pixels rose/vert dans le candidat board.",
    min: 0,
    max: 0.5,
    step: 0.01,
  },
  {
    key: "board_padding_ratio",
    label: "Outer Padding",
    description: "Marge ajoutée autour du quad détecté avant le warp. Monte-le si le board est coupé.",
    min: 0,
    max: 0.08,
    step: 0.001,
  },
  {
    key: "board_hough_canny_low",
    label: "Hough Canny Low",
    description: "Seuil Canny bas utilisé uniquement pour chercher les lignes Hough de refinement.",
    min: 5,
    max: 150,
    step: 5,
    unit: "0-255",
  },
  {
    key: "board_hough_canny_high",
    label: "Hough Canny High",
    description: "Seuil Canny haut utilisé uniquement pour chercher les lignes Hough de refinement.",
    min: 20,
    max: 300,
    step: 5,
    unit: "0-255",
  },
  {
    key: "board_hough_threshold",
    label: "Hough Votes",
    description: "Nombre minimal de votes pour accepter une ligne Hough.",
    min: 10,
    max: 120,
    step: 5,
  },
  {
    key: "board_hough_min_line_ratio",
    label: "Hough Min Length",
    description: "Longueur minimale d'une ligne Hough en ratio du plus petit côté de l'image.",
    min: 0.1,
    max: 0.8,
    step: 0.01,
  },
  {
    key: "board_hough_max_line_gap",
    label: "Hough Max Gap",
    description: "Gap maximal entre segments pour fusionner une ligne Hough.",
    min: 0,
    max: 60,
    step: 1,
    unit: "px",
  },
  {
    key: "board_hough_max_line_distance",
    label: "Hough Snap Distance",
    description: "Distance max entre les coins du contour et une ligne Hough candidate.",
    min: 5,
    max: 80,
    step: 1,
    unit: "px",
  },
  {
    key: "board_hough_min_area_keep",
    label: "Hough Min Area",
    description: "Aire minimale conservée après refinement. Monte-le pour empêcher la Hough de couper le board.",
    min: 0.8,
    max: 1.05,
    step: 0.01,
  },
  {
    key: "board_hough_max_area_grow",
    label: "Hough Max Area",
    description: "Aire maximale autorisée après refinement. Baisse-le si la Hough attrape trop large.",
    min: 1.0,
    max: 1.3,
    step: 0.01,
  },
  {
    key: "board_hough_max_corner_shift_ratio",
    label: "Hough Corner Shift",
    description: "Déplacement max des coins par rapport au contour initial, en ratio du côté le plus court.",
    min: 0.01,
    max: 0.25,
    step: 0.01,
  },
];

const GROUPS: { label: string; color: string; sliders: SliderDef[] }[] = [
  {
    label: "Preprocessing",
    color: "var(--charm-cyan)",
    sliders: [
      {
        key: "clahe_clip_limit",
        label: "CLAHE Clip",
        description: "Augmente le contraste local. Trop haut peut amplifier le bruit.",
        min: 0.5,
        max: 8.0,
        step: 0.1,
      },
      {
        key: "clahe_tile_size",
        label: "CLAHE Tile",
        description: "Nombre de tuiles CLAHE par axe. Petit = contraste plus local, grand = plus global.",
        min: 4,
        max: 32,
        step: 4,
        unit: "tiles",
      },
      {
        key: "saturation_boost",
        label: "Saturation",
        description: "Renforce les couleurs du plateau pour mieux séparer les cases.",
        min: 0.5,
        max: 2.5,
        step: 0.05,
        unit: "x",
      },
      {
        key: "brightness_boost",
        label: "Brightness",
        description: "Éclaircit ou assombrit l'image avant la détection.",
        min: 0.8,
        max: 1.5,
        step: 0.01,
        unit: "x",
      },
      {
        key: "sharpen_alpha",
        label: "Sharpen α",
        description: "Force de l'image nette dans le sharpen. Plus haut = contours plus forts.",
        min: 0.5,
        max: 2.5,
        step: 0.05,
      },
      {
        key: "sharpen_beta",
        label: "Sharpen β",
        description: "Quantité de flou soustraite. Plus négatif = accentuation plus agressive.",
        min: -1.5,
        max: 0.0,
        step: 0.05,
      },
      {
        key: "warp_size",
        label: "Output Size",
        description: "Résolution carrée après correction de perspective.",
        min: 400,
        max: 1200,
        step: 100,
        unit: "px",
      },
    ],
  },
  {
    label: "Occupancy Detection",
    color: "oklch(0.72 0.19 145)",
    sliders: [
      {
        key: "occupancy_threshold",
        label: "Threshold",
        description: "Score minimum pour dire qu'une case contient une pièce. Même unité que le debug: moyenne Canny 0-255 + texture pondérée.",
        min: 0.5,
        max: 80.0,
        step: 0.5,
        unit: "score",
      },
      {
        key: "canny_low",
        label: "Canny Low",
        description: "Seuil bas OpenCV Canny sur une image 8-bit. Plus bas = détecte plus de détails faibles.",
        min: 10,
        max: 150,
        step: 5,
        unit: "0-255",
      },
      {
        key: "canny_high",
        label: "Canny High",
        description: "Seuil haut OpenCV Canny sur une image 8-bit. Plus haut = garde seulement les contours forts.",
        min: 50,
        max: 300,
        step: 10,
        unit: "0-255",
      },
      {
        key: "occupancy_std_weight",
        label: "Texture Weight",
        description: "Ajoute le score de variation locale: les pièces créent ombres et relief, les cases vides restent plus plates.",
        min: 0,
        max: 1.5,
        step: 0.05,
        unit: "x std",
      },
    ],
  },
];

const THRESHOLD_SLIDERS: SliderDef[] = [
  {
    key: "white_threshold",
    label: "White Thresh",
    description: "Luminosité minimum pour classer une pièce comme blanche.",
    min: 80,
    max: 200,
    step: 0.5,
  },
  {
    key: "black_threshold",
    label: "Black Thresh",
    description: "Luminosité maximum pour classer une pièce comme noire.",
    min: 60,
    max: 200,
    step: 0.5,
  },
];

interface Props {
  params: PipelineParams;
  onChange: (p: PipelineParams) => void;
  onOpenManualCalibration?: () => void;
  children?: React.ReactNode;
}

function formatParamValue(value: number) {
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

export default function ParamControls({ params, onChange, onOpenManualCalibration, children }: Props) {
  const set = (key: keyof PipelineParams, val: number) =>
    onChange({ ...params, [key]: val });
  const setBool = (key: "auto_detect_board" | "apply_inner_warp" | "board_hough_refine", val: boolean) =>
    onChange({ ...params, [key]: val });
  const renderNumericControl = ({ key, label: slLabel, description, min, max, step, unit }: SliderDef) => {
    const val = params[key] as number;
    const def = DEFAULT_PARAMS[key] as number;
    const changed = Math.abs(val - def) > 0.0001;
    const sliderValue = Math.min(max, Math.max(min, val));

    return (
      <div key={key}>
        <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-center gap-1.5">
            <label className="min-w-0 break-words text-xs font-jetbrains leading-snug" style={{ color: "var(--charm-text)" }}>
              {slLabel}
            </label>
            <Tooltip>
              <TooltipTrigger
                type="button"
                className="inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] font-jetbrains font-semibold outline-none transition-colors hover:border-amber-DEFAULT hover:text-amber-DEFAULT focus-visible:ring-2 focus-visible:ring-amber-DEFAULT/40"
                style={{
                  borderColor: "var(--charm-border)",
                  color: "var(--charm-muted)",
                  background: "var(--charm-bg)",
                }}
                aria-label={`Description: ${slLabel}`}
              >
                ?
              </TooltipTrigger>
              <TooltipContent
                side="top"
                align="center"
                sideOffset={8}
                className="max-w-64 border px-3 py-2 text-left text-[11px] leading-snug shadow-xl"
                style={{
                  borderColor: "var(--charm-border)",
                  background: "var(--charm-text)",
                  color: "var(--charm-bg)",
                }}
              >
                {description}
              </TooltipContent>
            </Tooltip>
          </div>
          <div className="flex w-full items-center gap-2 sm:w-auto sm:justify-end">
            {changed && (
              <button
                onClick={() => set(key, def)}
                className="shrink-0 text-xs"
                style={{ color: "var(--charm-muted)" }}
                title="Reset to default"
              >
                ↺
              </button>
            )}
            {unit && (
              <span className="shrink-0 text-[10px] font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                {unit}
              </span>
            )}
            <input
              type="number"
              min={min}
              max={max}
              step={step}
              value={formatParamValue(val)}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (Number.isFinite(next)) set(key, next);
              }}
              className="h-8 min-w-0 flex-1 rounded border bg-transparent px-1 text-right font-jetbrains text-xs font-semibold outline-none focus-visible:ring-2 focus-visible:ring-cyan-DEFAULT/40 sm:flex-none"
              style={{
                borderColor: changed ? "var(--charm-cyan)" : "var(--charm-border)",
                color: changed ? "var(--charm-cyan)" : "var(--charm-text)",
              }}
              aria-label={`${slLabel} value`}
            />
          </div>
        </div>
        <Slider
          min={min}
          max={max}
          step={step}
          value={[sliderValue]}
          onValueChange={(vals) => set(key, Array.isArray(vals) ? vals[0] : vals)}
          className="w-full"
        />
        <div className="mt-0.5 flex justify-between">
          <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.4 }}>
            {min}
          </span>
          <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.3 }}>
            default: {formatParamValue(def)}
          </span>
          <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.4 }}>
            {max}
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-4 gap-3">
      <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <CardHeader className="px-3 pt-3 pb-1">
          <p
            className="text-xs font-jetbrains font-semibold uppercase tracking-widest"
            style={{ color: "var(--charm-cyan)" }}
          >
            Board Detection
          </p>
        </CardHeader>
        <CardContent className="px-3 pb-3">
          <div className="flex flex-col gap-2">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={params.auto_detect_board}
                onChange={(e) => setBool("auto_detect_board", e.target.checked)}
                className="mt-1 h-4 w-4 accent-cyan-DEFAULT"
              />
              <span className="space-y-1">
                <span className="flex items-center gap-2">
                  <span className="block text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                    Auto board edges
                  </span>
                  {!params.auto_detect_board && onOpenManualCalibration && (
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); onOpenManualCalibration(); }}
                      className="text-[10px] font-mono border border-cyan-DEFAULT/30 text-cyan-DEFAULT px-1.5 py-0.5 rounded hover:bg-cyan-DEFAULT/10"
                    >
                      Calibrate manually
                    </button>
                  )}
                </span>
                <span className="block text-[10px] font-jetbrains leading-snug" style={{ color: "var(--charm-muted)" }}>
                  Detects the black outer border in each raw image, then falls back to saved corners if detection fails.
                </span>
              </span>
            </label>
            <label className="mt-3 flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={params.apply_inner_warp}
                onChange={(e) => setBool("apply_inner_warp", e.target.checked)}
                className="mt-1 h-4 w-4 accent-cyan-DEFAULT"
              />
              <span className="space-y-1">
                <span className="block text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                  Inner warp refinement
                </span>
                <span className="block text-[10px] font-jetbrains leading-snug" style={{ color: "var(--charm-muted)" }}>
                  Applies the saved inner-corner crop after the first warp. Keep it off when it cuts into the board.
                </span>
              </span>
            </label>
            <label className="mt-3 flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={params.board_hough_refine}
                onChange={(e) => setBool("board_hough_refine", e.target.checked)}
                className="mt-1 h-4 w-4 accent-cyan-DEFAULT"
              />
              <span className="space-y-1">
                <span className="block text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                  Hough edge refinement
                </span>
                <span className="block text-[10px] font-jetbrains leading-snug" style={{ color: "var(--charm-muted)" }}>
                  Snaps the contour to long detected lines. Turn it off if it pulls the corners inside the board.
                </span>
              </span>
            </label>
          </div>
          <div className="mt-4 space-y-3">
            {BOARD_DETECTION_SLIDERS.map(renderNumericControl)}
          </div>
        </CardContent>
      </Card>

      {GROUPS.map(({ label, color, sliders }) => (
        <Card
          key={label}
          style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
        >
          <CardHeader className="px-3 pt-3 pb-1">
            <p
              className="text-xs font-jetbrains font-semibold uppercase tracking-widest"
              style={{ color }}
            >
              {label}
            </p>
          </CardHeader>
          <CardContent className="px-3 pb-3 space-y-3">
            {sliders.map(renderNumericControl)}
          </CardContent>
        </Card>
      ))}

      {/* Piece Color */}
      <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <CardHeader className="px-3 pt-3 pb-1">
          <p
            className="text-xs font-jetbrains font-semibold uppercase tracking-widest"
            style={{ color: "var(--charm-amber)" }}
          >
            Piece Color
          </p>
        </CardHeader>
        <CardContent className="px-3 pb-3 space-y-3">
          {THRESHOLD_SLIDERS.map(renderNumericControl)}
        </CardContent>
      </Card>

      {/* Extra tools / slot injected by parent */}
      {children}
    </div>
  );
}
