export interface PipelineParams {
  auto_detect_board: boolean;
  apply_inner_warp: boolean;
  board_canny_low: number;
  board_canny_high: number;
  board_dilation_iterations: number;
  board_min_area: number;
  board_max_side_ratio: number;
  board_min_area_ratio: number;
  board_max_area_ratio: number;
  board_min_color_ratio: number;
  board_padding_ratio: number;
  board_hough_refine: boolean;
  board_hough_canny_low: number;
  board_hough_canny_high: number;
  board_hough_threshold: number;
  board_hough_min_line_ratio: number;
  board_hough_max_line_gap: number;
  board_hough_max_line_distance: number;
  board_hough_min_area_keep: number;
  board_hough_max_area_grow: number;
  board_hough_max_corner_shift_ratio: number;
  clahe_clip_limit: number;
  clahe_tile_size: number;
  saturation_boost: number;
  brightness_boost: number;
  sharpen_alpha: number;
  sharpen_beta: number;
  occupancy_threshold: number;
  canny_low: number;
  canny_high: number;
  occupancy_std_weight: number;
  white_threshold: number;
  black_threshold: number;
  knn_n_neighbors: number;
  color_mode: "threshold" | "knn";
  warp_size: number;
  image_path?: string;
}

export type ColorLabel = "white" | "black" | "unknown" | "empty";

export interface PipelineResult {
  original: string;
  board_edges_debug?: string;
  first_warp: string;
  refined_warp: string;
  preprocessed: string;
  grid_debug: string;
  occupancy_debug: string;
  piece_color_debug: string;
  occupancy_matrix: number[][];
  occupancy_scores: number[][];
  white_bitmap: number[][];
  black_bitmap: number[][];
  brightness_scores: number[][];
  color_labels: ColorLabel[][];
  timings: Record<string, number>;
  total_ms: number;
  stats: {
    occupied: number;
    white_pieces: number;
    black_pieces: number;
    unknown_pieces: number;
  };
  image_path?: string;
  timestamp: number;
  warp_error?: string;
  board_detection_mode?: "auto" | "saved" | "none";
}

export interface CalibrationData {
  board: {
    top_left: [number, number];
    top_right: [number, number];
    bottom_right: [number, number];
    bottom_left: [number, number];
  } | null;
  inner: {
    top_left: [number, number];
    top_right: [number, number];
    bottom_right: [number, number];
    bottom_left: [number, number];
  } | null;
}

export interface ClassifierStatus {
  model_trained: boolean;
  model_path: string;
  last_result: ClassifierTrainResult | null;
}

export interface ClassifierTrainResult {
  best_k: number;
  chosen_cv_mean_f1: number;
  chosen_cv_std_f1: number;
  val_f1: number | null;
  val_confusion_matrix: [[number, number], [number, number]] | null;
  n_train: number;
  n_val: number;
  n_white: number;
  n_black: number;
  n_scenes: number;
  warnings: string[];
  cv_results: { k: number; mean_f1: number; std_f1: number; cv: string }[];
  missing_images?: string[];
}

export interface RobotPoint2D {
  x: number;
  y: number;
}

export interface RobotPoint3D {
  x: number;
  y: number;
  z: number;
}

export interface RobotCalibration {
  a1: RobotPoint2D;
  file_vector: RobotPoint2D;
  rank_vector: RobotPoint2D;
  z_hover: number;
  z_down: number;
  home: RobotPoint3D;
  capture_bin: RobotPoint3D;
  piece_heights: Record<"pawn" | "knight" | "bishop" | "rook" | "queen" | "king", number>;
}

export interface RobotCalibrationWrite {
  a1: RobotPoint2D;
  h1: RobotPoint2D;
  h8: RobotPoint2D;
  z_hover: number;
  z_down: number;
  home: RobotPoint3D;
  capture_bin: RobotPoint3D;
  piece_heights: Record<"pawn" | "knight" | "bishop" | "rook" | "queen" | "king", number>;
}

export interface RobotStatus {
  serial_connected: boolean;
  active_port: string | null;
  detected_port: string | null;
  ports: { device: string; description: string; manufacturer: string | null }[];
  robot_calibration: {
    exists: boolean;
    path: string;
    calibration: RobotCalibration;
    samples: Record<string, [number, number]>;
  };
}

export interface RobotCommandResult {
  status: string;
  responses: string[];
  position?: RobotPoint3D | null;
  timestamp: number;
}

export interface GameStepResult {
  pipeline: PipelineResult;
  inference: {
    accepted: boolean;
    move_uci: string | null;
    status: "accepted_legal_move" | "unchanged_position" | "invalid_observation" | "ambiguous_observation";
    mismatch_count: number;
    matching_move_count: number;
    fen_before: string;
    fen_after: string;
  };
}

export const DEFAULT_PARAMS: PipelineParams = {
  auto_detect_board: true,
  apply_inner_warp: false,
  board_canny_low: 50,
  board_canny_high: 150,
  board_dilation_iterations: 1,
  board_min_area: 5000.0,
  board_max_side_ratio: 1.18,
  board_min_area_ratio: 0.08,
  board_max_area_ratio: 0.80,
  board_min_color_ratio: 0.12,
  board_padding_ratio: 0.006,
  board_hough_refine: false,
  board_hough_canny_low: 30,
  board_hough_canny_high: 100,
  board_hough_threshold: 40,
  board_hough_min_line_ratio: 0.33,
  board_hough_max_line_gap: 18,
  board_hough_max_line_distance: 35.0,
  board_hough_min_area_keep: 0.97,
  board_hough_max_area_grow: 1.08,
  board_hough_max_corner_shift_ratio: 0.08,
  clahe_clip_limit: 2.5,
  clahe_tile_size: 8,
  saturation_boost: 1.2,
  brightness_boost: 1.05,
  sharpen_alpha: 1.35,
  sharpen_beta: -0.35,
  occupancy_threshold: 25.0,
  canny_low: 15,
  canny_high: 50,
  occupancy_std_weight: 0.4,
  white_threshold: 125.0,
  black_threshold: 110.0,
  knn_n_neighbors: 5,
  color_mode: "threshold",
  warp_size: 800,
};
