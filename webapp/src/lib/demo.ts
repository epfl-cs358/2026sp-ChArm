import { DEFAULT_PARAMS, PipelineParams, PipelineResult, ColorLabel } from "./types";

const BASE_BOARD: ColorLabel[][] = [
  ["black", "black", "black", "black", "empty", "black", "black", "black"],
  ["black", "black", "empty", "empty", "black", "black", "black", "black"],
  ["empty", "empty", "black", "empty", "empty", "empty", "unknown", "empty"],
  ["empty", "empty", "empty", "white", "empty", "empty", "empty", "empty"],
  ["empty", "empty", "empty", "empty", "white", "empty", "empty", "empty"],
  ["empty", "empty", "white", "empty", "empty", "white", "empty", "empty"],
  ["white", "white", "empty", "white", "empty", "white", "white", "white"],
  ["white", "empty", "white", "white", "white", "empty", "white", "white"],
];

function demoImage(label: string, accent = "#00a7c7") {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="640" viewBox="0 0 960 640">
    <rect width="960" height="640" fill="#101827"/>
    <rect x="90" y="50" width="520" height="520" rx="10" fill="#1b2638" stroke="${accent}" stroke-width="3"/>
    ${Array.from({ length: 8 }, (_, r) =>
      Array.from({ length: 8 }, (_, c) => {
        const x = 110 + c * 60;
        const y = 70 + r * 60;
        const fill = (r + c) % 2 === 0 ? "#d7d2bd" : "#546a78";
        return `<rect x="${x}" y="${y}" width="60" height="60" fill="${fill}" opacity="0.92"/>`;
      }).join("")
    ).join("")}
    <g fill="${accent}" opacity="0.82">
      <circle cx="230" cy="190" r="18"/><circle cx="410" cy="250" r="18"/>
      <circle cx="350" cy="370" r="18"/><circle cx="530" cy="430" r="18"/>
    </g>
    <rect x="660" y="74" width="210" height="16" rx="8" fill="${accent}" opacity="0.75"/>
    <rect x="660" y="120" width="160" height="10" rx="5" fill="#a7b0bd" opacity="0.7"/>
    <rect x="660" y="146" width="190" height="10" rx="5" fill="#a7b0bd" opacity="0.45"/>
    <rect x="660" y="190" width="230" height="260" rx="10" fill="#182234" stroke="#2f3f58"/>
    <text x="690" y="336" fill="#e5edf4" font-family="monospace" font-size="34">${label}</text>
  </svg>`;

  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function cloneBoard(params: PipelineParams): ColorLabel[][] {
  const board = BASE_BOARD.map((row) => [...row]);
  if (params.occupancy_threshold < DEFAULT_PARAMS.occupancy_threshold) {
    board[2][1] = "unknown";
    board[5][7] = "white";
  }
  if (params.color_mode === "threshold" && params.white_threshold > DEFAULT_PARAMS.white_threshold + 20) {
    board[3][3] = "unknown";
  }
  return board;
}

export function createDemoPipelineResult(params: PipelineParams = DEFAULT_PARAMS): PipelineResult {
  const colorLabels = cloneBoard(params);
  const occupancyMatrix = colorLabels.map((row) => row.map((cell) => (cell === "empty" ? 0 : 1)));
  const occupancyScores = colorLabels.map((row, ri) =>
    row.map((cell, ci) => {
      const base = cell === "empty" ? 0.6 + ((ri + ci) % 4) * 0.25 : 4.2 + ((ri * 3 + ci) % 7) * 0.7;
      return Number(base.toFixed(2));
    })
  );
  const brightnessScores = colorLabels.map((row, ri) =>
    row.map((cell, ci) => {
      if (cell === "white") return 152 + ((ri + ci) % 5) * 6;
      if (cell === "black") return 72 + ((ri + ci) % 5) * 5;
      if (cell === "unknown") return 118;
      return 95 + ((ri + ci) % 6) * 4;
    })
  );
  const stats = colorLabels.flat().reduce(
    (acc, cell) => {
      if (cell !== "empty") acc.occupied += 1;
      if (cell === "white") acc.white_pieces += 1;
      if (cell === "black") acc.black_pieces += 1;
      if (cell === "unknown") acc.unknown_pieces += 1;
      return acc;
    },
    { occupied: 0, white_pieces: 0, black_pieces: 0, unknown_pieces: 0 }
  );
  const sharpenCost = Math.abs(params.sharpen_beta) * 6 + params.sharpen_alpha * 8;
  const totalMs = 122 + params.clahe_clip_limit * 5 + params.warp_size / 24 + sharpenCost;

  return {
    original: demoImage("Raw", "#f5b841"),
    board_edges_debug: demoImage(params.auto_detect_board ? "Edges" : "Saved", "#22c55e"),
    first_warp: demoImage("Warp 1", "#2dd4bf"),
    refined_warp: demoImage("Refined", "#00a7c7"),
    preprocessed: demoImage("CLAHE", "#8b5cf6"),
    grid_debug: demoImage("Grid", "#22c55e"),
    occupancy_debug: demoImage("Edges", "#38bdf8"),
    piece_color_debug: demoImage("Colors", "#f59e0b"),
    occupancy_matrix: occupancyMatrix,
    occupancy_scores: occupancyScores,
    white_bitmap: colorLabels.map((row) => row.map((cell) => (cell === "white" ? 1 : 0))),
    black_bitmap: colorLabels.map((row) => row.map((cell) => (cell === "black" ? 1 : 0))),
    brightness_scores: brightnessScores,
    color_labels: colorLabels,
    timings: {
      load_ms: 9.4,
      board_detect_ms: 28.8,
      warp_ms: 34.6,
      preprocess_ms: 21.7,
      occupancy_ms: 37.2,
      color_classification_ms: 18.5,
    },
    total_ms: totalMs,
    stats,
    image_path: "demo://synthetic-board",
    timestamp: Date.now() / 1000,
    board_detection_mode: params.auto_detect_board ? "auto" : "saved",
  };
}

export const DEMO_RAW_IMAGE = demoImage("Calibration", "#00a7c7");
