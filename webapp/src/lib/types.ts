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
  occupancy_delta_threshold: number;
  canny_low: number;
  canny_high: number;
  occupancy_std_weight: number;
  white_threshold: number;
  black_threshold: number;
  white_delta_threshold: number;
  black_delta_threshold: number;
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
  cnn_overlay?: string;
  cnn_active?: boolean;
  image_path?: string;
  timestamp: number;
  warp_error?: string;
  board_detection_mode?: "auto" | "saved" | "none";
  board_validation_debug?: {
    expected_fen: string;
    mismatch_count: number;
    observed_white_bitmap: number[][];
    observed_black_bitmap: number[][];
    color_labels: ColorLabel[][];
  };
  cv_mode?: "vision" | "cnn";
  cv_router?: {
    mode_used: "vision" | "cnn" | null;
    by_mode: { vision: number; cnn: number };
    total: number;
    attempts: Array<{
      mode: "vision" | "cnn";
      index: number;
      success: boolean;
      error: string | null;
      elapsed_ms: number;
    }>;
    final_error: string | null;
  };
  validated_capture?: {
    saved: boolean;
    dataset: string;
    counts?: { empty: number; white: number; black: number };
    error?: string | null;
  } | null;
}

export interface PipelineSnapshotSaveResult {
  status: string;
  path: string;
  summary_path: string;
  refined_warp_path?: string;
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

export type PieceHeights = Record<"pawn" | "knight" | "bishop" | "rook" | "queen" | "king", number>;

export interface RobotCalibration {
  a1: RobotPoint2D;
  file_vector: RobotPoint2D;
  rank_vector: RobotPoint2D;
  z_hover: number;
  z_down: number;
  home: RobotPoint3D;
  capture_bin: RobotPoint3D;
  pick_z: PieceHeights;
  place_z: PieceHeights;
}

export interface RobotCalibrationWrite {
  a1: RobotPoint2D;
  h1: RobotPoint2D;
  h8: RobotPoint2D;
  z_hover: number;
  z_down: number;
  home: RobotPoint3D;
  capture_bin: RobotPoint3D;
  pick_z: PieceHeights;
  place_z: PieceHeights;
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

export interface RobotBoardInfo {
  points: Partial<Record<"a1" | "h1" | "h8" | "trash", RobotPoint2D>>;
  current_z: number | null;
  complete: boolean;
  calibration: RobotCalibration | null;
}

export interface RobotCommandResult {
  status: string;
  responses: string[];
  position?: RobotPoint3D | null;
  board_info?: RobotBoardInfo | null;
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

export interface GameSessionMove {
  success: boolean;
  message: string;
  move_uci: string | null;
  san?: string | null;
  mismatch_count?: number | null;
  error_code?: "unchanged" | "illegal_move" | "in_check" | "ambiguous" | null;
}

export interface GameSessionRobotCommand {
  status: string;
  responses: string[];
  position?: RobotPoint3D | null;
  board_info?: RobotBoardInfo | null;
  timestamp: number;
} 

export type PlayerMoveRating = "Excellent" | "Good" | "Inaccuracy" | "Mistake" | "Blunder";

export interface GameEvaluation {
  score: string;
  score_cp: number | null;
  mate: number | null;
  winning_color: "white" | "black" | "even";
  win_percentage: number;
  best_move_suggestion: string | null;
  best_move_uci: string | null;
  player_move_rating: PlayerMoveRating | null;
  player_cp_loss: number | null;
}

export interface GameSessionResult {
  status: string;
  player_color: "white" | "black" | null;
  robot_color: "white" | "black" | null;
  fen: string | null;
  moves: string[];
  pipeline?: PipelineResult;
  started?: GameSessionMove;
  human_move?: GameSessionMove;
  robot_move?: GameSessionMove;
  robot_command?: GameSessionRobotCommand | null;
  player_command?: GameSessionRobotCommand | null;
  evaluation?: GameEvaluation | null;
  timestamp: number;
}

export const DEFAULT_PARAMS: PipelineParams = {
  auto_detect_board: false,
  apply_inner_warp: true,
  board_canny_low: 50,
  board_canny_high: 150,
  board_dilation_iterations: 1,
  board_min_area: 5000.0,
  board_max_side_ratio: 1.35,
  board_min_area_ratio: 0.08,
  board_max_area_ratio: 0.80,
  board_min_color_ratio: 0.12,
  board_padding_ratio: 0.015,
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
  occupancy_threshold: 4.0,
  occupancy_delta_threshold: 12.0,
  canny_low: 15,
  canny_high: 50,
  occupancy_std_weight: 0.4,
  white_threshold: 80.0,
  black_threshold: 80.0,
  white_delta_threshold: 5.0,
  black_delta_threshold: -30.0,
  warp_size: 800,
};
