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
    step: 1,
  },
  {
    key: "black_threshold",
    label: "Black Thresh",
    description: "Luminosité maximum pour classer une pièce comme noire.",
    min: 60,
    max: 180,
    step: 1,
  },
];

interface Props {
  params: PipelineParams;
  onChange: (p: PipelineParams) => void;
  children?: React.ReactNode;
}

export default function ParamControls({ params, onChange, children }: Props) {
  const set = (key: keyof PipelineParams, val: number) =>
    onChange({ ...params, [key]: val });
  const setBool = (key: "auto_detect_board" | "apply_inner_warp" | "board_hough_refine", val: boolean) =>
    onChange({ ...params, [key]: val });

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
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={params.auto_detect_board}
              onChange={(e) => setBool("auto_detect_board", e.target.checked)}
              className="mt-1 h-4 w-4 accent-cyan-DEFAULT"
            />
            <span className="space-y-1">
              <span className="block text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                Auto board edges
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
          <div className="mt-4 space-y-3">
            {BOARD_DETECTION_SLIDERS.map(({ key, label: slLabel, description, min, max, step, unit }) => {
              const val = params[key] as number;
              const def = DEFAULT_PARAMS[key] as number;
              const changed = Math.abs(val - def) > 0.0001;
              return (
                <div key={key}>
                  <div className="flex items-start justify-between mb-1.5 gap-2">
                    <div className="pr-3 flex items-center gap-1.5">
                      <label className="text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                        {slLabel}
                      </label>
                      <Tooltip>
                        <TooltipTrigger
                          type="button"
                          className="inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] font-jetbrains font-semibold outline-none transition-colors hover:border-amber-DEFAULT hover:text-amber-DEFAULT"
                          style={{ borderColor: "var(--charm-border)", color: "var(--charm-muted)", background: "var(--charm-bg)" }}
                          aria-label={`Description: ${slLabel}`}
                        >
                          ?
                        </TooltipTrigger>
                        <TooltipContent side="top" align="center" sideOffset={8} className="max-w-64 border px-3 py-2 text-left text-[11px] leading-snug shadow-xl" style={{ borderColor: "var(--charm-border)", background: "var(--charm-text)", color: "var(--charm-bg)" }}>
                          {description}
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <div className="flex items-center gap-2">
                      {changed && (
                        <button onClick={() => set(key, def)} className="text-xs" style={{ color: "var(--charm-muted)" }} title="Reset to default">↺</button>
                      )}
                      <span className="text-xs font-jetbrains font-semibold" style={{ color: changed ? "var(--charm-cyan)" : "var(--charm-text)" }}>
                        {typeof val === "number" && !Number.isInteger(val) ? val.toFixed(3).replace(/0+$/, "").replace(/\.$/, "") : val}
                        {unit ? ` ${unit}` : ""}
                      </span>
                    </div>
                  </div>
                  <Slider min={min} max={max} step={step} value={[val]} onValueChange={(vals) => set(key, Array.isArray(vals) ? vals[0] : vals)} className="w-full" />
                  <div className="flex justify-between mt-0.5">
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.4 }}>{min}</span>
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.3 }}>default: {def}</span>
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.4 }}>{max}</span>
                  </div>
                </div>
              );
            })}
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
            {sliders.map(({ key, label: slLabel, description, min, max, step, unit }) => {
              const val = params[key] as number;
              const def = DEFAULT_PARAMS[key] as number;
              const changed = Math.abs(val - def) > 0.0001;
              return (
                <div key={key}>
                  <div className="flex items-start justify-between mb-1.5 gap-2">
                    <div className="pr-3 flex items-center gap-1.5">
                      <label
                        className="text-xs font-jetbrains"
                        style={{ color: "var(--charm-text)" }}
                      >
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
                    <div className="flex items-center gap-2">
                      {changed && (
                        <button
                          onClick={() => set(key, def)}
                          className="text-xs"
                          style={{ color: "var(--charm-muted)" }}
                          title="Reset to default"
                        >
                          ↺
                        </button>
                      )}
                      <span
                        className="text-xs font-jetbrains font-semibold"
                        style={{ color: changed ? "var(--charm-cyan)" : "var(--charm-text)" }}
                      >
                        {typeof val === "number" && !Number.isInteger(val)
                          ? val.toFixed(2)
                          : val}
                        {unit ? ` ${unit}` : ""}
                      </span>
                    </div>
                  </div>
                  <Slider
                    min={min}
                    max={max}
                    step={step}
                    value={[val]}
                    onValueChange={(vals) => set(key, Array.isArray(vals) ? vals[0] : vals)}
                    className="w-full"
                  />
                  <div className="flex justify-between mt-0.5">
                    <span
                      className="text-xs font-jetbrains"
                      style={{ color: "var(--charm-muted)", opacity: 0.4 }}
                    >
                      {min}
                    </span>
                    <span
                      className="text-xs font-jetbrains"
                      style={{ color: "var(--charm-muted)", opacity: 0.3 }}
                    >
                      default: {def}
                    </span>
                    <span
                      className="text-xs font-jetbrains"
                      style={{ color: "var(--charm-muted)", opacity: 0.4 }}
                    >
                      {max}
                    </span>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      ))}

      {/* Piece Color — toggleable threshold vs kNN */}
      <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
        <CardHeader className="px-3 pt-3 pb-1">
          <div className="flex items-center justify-between">
            <p
              className="text-xs font-jetbrains font-semibold uppercase tracking-widest"
              style={{ color: "var(--charm-amber)" }}
            >
              Piece Color
            </p>
            {/* mode toggle */}
            <div className="flex rounded overflow-hidden border text-[10px] font-jetbrains" style={{ borderColor: "var(--charm-border)" }}>
              {(["threshold", "knn"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => onChange({ ...params, color_mode: m })}
                  className="px-2 py-0.5 transition-colors"
                  style={{
                    background: params.color_mode === m ? "var(--charm-cyan-glow, oklch(0.25 0.08 200))" : "transparent",
                    color: params.color_mode === m ? "var(--charm-cyan)" : "var(--charm-muted)",
                  }}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-3 pb-3 space-y-3">
          {params.color_mode === "threshold" ? (
            THRESHOLD_SLIDERS.map(({ key, label: slLabel, description, min, max, step, unit }) => {
              const val = params[key] as number;
              const def = DEFAULT_PARAMS[key] as number;
              const changed = Math.abs(val - def) > 0.0001;
              return (
                <div key={key}>
                  <div className="flex items-start justify-between mb-1.5 gap-2">
                    <div className="pr-3 flex items-center gap-1.5">
                      <label className="text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>
                        {slLabel}
                      </label>
                      <Tooltip>
                        <TooltipTrigger
                          type="button"
                          className="inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] font-jetbrains font-semibold outline-none transition-colors hover:border-amber-DEFAULT hover:text-amber-DEFAULT"
                          style={{ borderColor: "var(--charm-border)", color: "var(--charm-muted)", background: "var(--charm-bg)" }}
                          aria-label={`Description: ${slLabel}`}
                        >
                          ?
                        </TooltipTrigger>
                        <TooltipContent side="top" align="center" sideOffset={8} className="max-w-64 border px-3 py-2 text-left text-[11px] leading-snug shadow-xl" style={{ borderColor: "var(--charm-border)", background: "var(--charm-text)", color: "var(--charm-bg)" }}>
                          {description}
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <div className="flex items-center gap-2">
                      {changed && (
                        <button onClick={() => set(key, def)} className="text-xs" style={{ color: "var(--charm-muted)" }} title="Reset to default">↺</button>
                      )}
                      <span className="text-xs font-jetbrains font-semibold" style={{ color: changed ? "var(--charm-cyan)" : "var(--charm-text)" }}>
                        {val}{unit ? ` ${unit}` : ""}
                      </span>
                    </div>
                  </div>
                  <Slider min={min} max={max} step={step} value={[val]} onValueChange={(vals) => set(key, Array.isArray(vals) ? vals[0] : vals)} className="w-full" />
                  <div className="flex justify-between mt-0.5">
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.4 }}>{min}</span>
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.3 }}>default: {def}</span>
                    <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)", opacity: 0.4 }}>{max}</span>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-jetbrains" style={{ color: "var(--charm-text)" }}>k neighbors</span>
                <span className="text-xs font-jetbrains font-semibold" style={{ color: "var(--charm-cyan)" }}>
                  {params.knn_n_neighbors}{" "}
                  <span style={{ color: "var(--charm-muted)", fontWeight: 400 }}>(auto)</span>
                </span>
              </div>
              <p className="text-[10px] font-jetbrains leading-snug" style={{ color: "var(--charm-muted)" }}>
                kNN entraîné sur annotations. Utiliser <em>Retrain classifier</em> dans le panneau Supervision.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extra tools / slot injected by parent */}
      {children}
    </div>
  );
}
