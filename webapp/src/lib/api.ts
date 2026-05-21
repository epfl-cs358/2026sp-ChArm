import {
  ClassifierStatus,
  ClassifierTrainResult,
  PipelineParams,
  PipelineResult,
  PipelineSnapshotSaveResult,
  CalibrationData,
  GameSessionResult,
  RobotCalibrationWrite,
  RobotCommandResult,
  RobotStatus,
  GameStepResult,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Request failed");
  return res.json();
}

export const api = {
  health: () => get<{ status: string; timestamp: number }>("/health"),

  runPipeline: (params: PipelineParams) =>
    post<PipelineResult>("/api/pipeline/run", params),

  captureEmptyReference: (payload?: { params?: PipelineParams; image_path?: string; capture?: boolean }) =>
    post<{ status: string; path: string; image: string; source_image?: string; saved_at?: number }>(
      "/api/empty-reference/capture",
      payload ?? {},
    ),

  getEmptyReference: () =>
    get<{ exists: boolean; image: string | null; path?: string; saved_at?: number | null }>("/api/empty-reference"),

  clearEmptyReference: () =>
    fetch(`${API}/api/empty-reference`, { method: "DELETE" }).then((r) => r.json()),

  uploadAndRun: async (file: File, params: PipelineParams): Promise<PipelineResult> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("params_json", JSON.stringify(params));
    const res = await fetch(`${API}/api/pipeline/upload`, { method: "POST", body: fd });
    if (!res.ok) throw new Error("Upload failed");
    return res.json();
  },

  processGameStep: (payload: {
    moves: string[];
    params: PipelineParams;
    capture?: boolean;
    max_mismatches?: number;
  }) => post<GameStepResult>("/api/game/step", payload),

  startGameSession: (payload: {
    player_color?: "white" | "black";
    difficulty?: 0 | 1 | 2;
    skill_level?: number;
    params?: PipelineParams;
    capture?: boolean;
    max_mismatches?: number;
    engine_path?: string;
    think_time?: number;
    port?: string;
    baud?: number;
    execute_robot?: boolean;
  }) => post<GameSessionResult>("/api/game/session/start", payload),

  processGameSessionTurn: (payload: {
    params?: PipelineParams;
    capture?: boolean;
    max_mismatches?: number;
    difficulty?: 0 | 1 | 2;
    skill_level?: number;
    engine_path?: string;
    think_time?: number;
    port?: string;
    baud?: number;
    execute_robot?: boolean;
  }) => post<GameSessionResult>("/api/game/session/player-done", payload),

  resetGameSession: () => post<GameSessionResult>("/api/game/session/reset", {}),

  getGameSession: () => get<GameSessionResult>("/api/game/session"),

  getCalibration: () => get<CalibrationData>("/api/calibration"),

  updateCalibration: (data: Partial<CalibrationData>) =>
    put<{ status: string }>("/api/calibration", data),

  calibrateBoardCorners: (payload: {
    top_left: [number, number];
    top_right: [number, number];
    bottom_right: [number, number];
    bottom_left: [number, number];
    image_path?: string;
    warp_size?: number;
  }) =>
    post<{
      status: string;
      path: string;
      image_path: string;
      board: NonNullable<CalibrationData["board"]>;
      first_warp: string;
      debug: string;
    }>("/api/calibration/board-corners", payload),

  getRawImage: () => get<{ image: string; path: string; timestamp: number }>("/api/image/raw"),

  readImage: (path: string) =>
    post<{ image: string; path: string; timestamp: number }>("/api/image/read", { path }),

  captureFromCamera: (url?: string) => post<{ status: string; image: string; path: string }>("/api/capture", { url }),

  getDefaults: () => get<PipelineParams>("/api/params/defaults"),

  savePipelineSnapshot: (payload: {
    params: PipelineParams;
    images: Record<string, string | undefined>;
    result?: Record<string, unknown>;
    labels?: string[][];
    source_image?: string;
    name?: string;
  }) => post<PipelineSnapshotSaveResult>("/api/pipeline/snapshot", payload),

  getClassifierStatus: () => get<ClassifierStatus>("/api/classifier/status"),

  retrainClassifier: () => post<ClassifierTrainResult>("/api/classifier/retrain", {}),

  getAnnotations: () =>
    get<{
      count: number;
      n_white: number;
      n_black: number;
      n_scenes: number;
      annotations: { image_id: string; scene_id: string; saved_at?: number }[];
    }>("/api/annotations"),

  listImages: () =>
    get<{ images: { name: string; path: string }[] }>("/api/images/list"),

  getRobotStatus: () => get<RobotStatus>("/api/robot/status"),

  updateRobotCalibration: (data: RobotCalibrationWrite) =>
    put<{ status: string } & RobotStatus["robot_calibration"]>("/api/robot/calibration", data),

  sendRobotCommand: (payload: {
    command: "pos" | "arm-calibrate" | "board-info" | "board-calibrate" | "board-cal-key" | "board-cal-clear" | "capture-corner" | "move-square" | "move" | "raw" | "goto" | "jog";
    port?: string;
    baud?: number;
    square?: string;
    corner?: "a1" | "h1" | "h8";
    uci?: string;
    raw?: string;
    x?: number;
    y?: number;
    z?: number;
    piece_type?: string;
    down?: boolean;
    capture?: boolean;
    castling?: boolean;
    promotion?: boolean;
  }) => post<RobotCommandResult>("/api/robot/command", payload),

  getRobotPosition: (port?: string, baud = 9600) => {
    const params = new URLSearchParams();
    if (port) params.set("port", port);
    params.set("baud", String(baud));
    return get<RobotCommandResult>(`/api/robot/position?${params.toString()}`);
  },

  readRobotEeprom: (port?: string, baud = 9600) => {
    const params = new URLSearchParams();
    if (port) params.set("port", port);
    params.set("baud", String(baud));
    return get<RobotCommandResult>(`/api/robot/eeprom?${params.toString()}`);
  },

  disconnectRobot: () => post<{ status: string }>("/api/robot/disconnect", {}),

  // ---- Labeled-data wizard ----
  listLabelDatasets: () =>
    get<{
      datasets: LabelDatasetMeta[];
      squares: string[];
    }>("/api/labeling/datasets"),

  getLabelDataset: (name: string) =>
    get<LabelDatasetResponse>(`/api/labeling/datasets/${encodeURIComponent(name)}`),

  createLabelDataset: (payload: { name: string; settings?: Partial<LabelSettings> }) =>
    post<LabelDatasetResponse>("/api/labeling/datasets", payload),

  deleteLabelDataset: (name: string) =>
    fetch(`${API}/api/labeling/datasets/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }).then((r) => r.json()),

  rescanLabelDataset: (name: string) =>
    post<{ metadata: LabelDatasetMeta }>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/rescan`,
      {},
    ),

  rescanAllLabelDatasets: () =>
    post<{ rescanned: LabelDatasetMeta[] }>(
      "/api/labeling/datasets/rescan-all",
      {},
    ),

  updateLabelSettings: (name: string, settings: LabelSettings) =>
    put<LabelDatasetResponse>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/settings`,
      { settings },
    ),

  getLabelThumb: (name: string, color: "empty" | "white" | "black", square: string) => {
    const params = new URLSearchParams({ color, square: square || "a1" });
    return get<{ exists: boolean; image: string | null }>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/thumb?${params.toString()}`,
    );
  },

  captureLabelEmpty: (name: string, payload: {
    params: PipelineParams;
    capture?: boolean;
    frames?: number;
    mode?: "overwrite" | "append";
  }) =>
    post<{ saved_frames: number } & LabelDatasetResponse>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/capture-empty`,
      payload,
    ),

  captureLabelSquare: (name: string, payload: {
    color: "white" | "black";
    square: string;
    params: PipelineParams;
    capture?: boolean;
    frames?: number;
    skip_arm_home_check?: boolean;
    mode?: "overwrite" | "append";
  }) =>
    post<{ saved_frames: number } & LabelDatasetResponse>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/capture-square`,
      payload,
    ),

  captureLabelBulk: (name: string, payload: {
    labels: Record<string, "empty" | "white" | "black">;
    params: PipelineParams;
    capture?: boolean;
    frames?: number;
    settle_ms?: number;
  }) =>
    post<{ cells_written: { empty: number; white: number; black: number } } & LabelDatasetResponse>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/capture-bulk`,
      payload,
    ),

  labelingArm: (name: string, payload: {
    color: "white" | "black";
    square: string;
    action: "pickup_source" | "place_target" | "return_to_source" | "home" | "move_piece" | "pick_and_place";
    from_square?: string;
    port?: string;
    baud?: number;
  }) =>
    post<{ status: string; action: string; commands: string[]; responses: string[] }>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/arm`,
      payload,
    ),

  computeDatasetStats: (name: string) =>
    post<{
      metadata: LabelDatasetMeta;
      accuracy: LabelAccuracyReport;
      exemplar_config_path: string;
    }>(`/api/labeling/datasets/${encodeURIComponent(name)}/compute-stats`, {}),

  getDatasetAccuracy: (name: string) =>
    get<{ exists: boolean; accuracy: LabelAccuracyReport | null }>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/accuracy`,
    ),

  getActiveClassifier: () =>
    get<{ active: boolean; name: string | null; has_config?: boolean; config_path?: string }>(
      "/api/labeling/active",
    ),

  setActiveClassifier: (name: string | null) =>
    put<{ active: boolean; name: string | null; config_path?: string }>(
      "/api/labeling/active",
      { name },
    ),

  clearActiveClassifier: () =>
    fetch(`${API}/api/labeling/active`, { method: "DELETE" }).then((r) => r.json()),

  arucoDetect: (payload: {
    image_path?: string;
    capture?: boolean;
    warp_size?: number;
    dictionary?: string;
    layout?: Record<string, string>;
    save?: boolean;
  }) =>
    post<ArucoDetectResult>("/api/calibration/aruco-detect", payload),

  getArucoMarker: (marker_id: number, size = 600, dictionary = "DICT_4X4_50") => {
    const params = new URLSearchParams({
      marker_id: String(marker_id),
      size: String(size),
      dictionary,
    });
    return get<{ marker_id: number; dictionary: string; size_px: number; image: string }>(
      `/api/calibration/aruco-marker?${params.toString()}`,
    );
  },

  // ---- CNN wizard (calibration preflight + dataset build + training + inference) ----
  getCalibrationStatus: () => get<CalibrationStatus>("/api/calibration/status"),

  cnnListSourceDatasets: () =>
    get<{ datasets: CnnSourceDatasetMeta[] }>("/api/cnn/source-datasets"),

  cnnBuildDataset: (payload: { source: string; output: string; val_split?: number }) =>
    post<{ build_id: string }>("/api/cnn/build-dataset", payload),

  cnnBuildStatus: (build_id: string) =>
    get<CnnBuildStatus>(`/api/cnn/build-status/${encodeURIComponent(build_id)}`),

  cnnDatasetPreview: (output_name: string, per_class = 9) => {
    const qs = new URLSearchParams({ per_class: String(per_class) });
    return get<{ preview: Record<string, string[]> }>(
      `/api/cnn/dataset-preview/${encodeURIComponent(output_name)}?${qs.toString()}`,
    );
  },

  cnnTrain: (payload: { dataset: string; epochs?: number; batch_size?: number }) =>
    post<{ job_id: string; run_id: string }>("/api/cnn/train", payload),

  cnnTrainStatus: (job_id: string) =>
    get<CnnTrainStatus>(`/api/cnn/train-status/${encodeURIComponent(job_id)}`),

  cnnTrainArtifacts: (run_id: string) =>
    get<CnnTrainArtifacts>(`/api/cnn/train-artifacts/${encodeURIComponent(run_id)}`),

  cnnListModels: () => get<{ models: CnnModelMeta[] }>("/api/cnn/models"),

  cnnActivateModel: (run_id: string) =>
    post<{ run_id: string; active: boolean }>("/api/cnn/activate-model", { run_id }),

  cnnActiveModel: () => get<CnnActiveModel>("/api/cnn/active-model"),

  // CV router: which pipeline runs first, and how many retries each.
  getCvConfig: () => get<CvRouterConfig>("/api/cv-config"),
  setCvConfig: (patch: Partial<CvRouterConfig>) =>
    post<CvRouterConfig>("/api/cv-config", patch),
  validatedDatasetStats: () =>
    get<ValidatedDatasetStats>("/api/validated-dataset/stats"),

  cnnScan: (payload: { capture?: boolean; compare_classical?: boolean }) =>
    post<CnnScanResult>("/api/cnn/scan", payload),

  cnnScanCell: (row: number, col: number) =>
    get<CnnScanCellResult>(`/api/cnn/scan-cell/${row}/${col}`),

  cnnFeedback: (payload: {
    run_id: string;
    row: number;
    col: number;
    true_label: "empty" | "white" | "black";
    crop_b64?: string;
  }) =>
    post<{
      queued: boolean;
      appended_to_source?: boolean;
      source_dataset?: string;
      square?: string;
      true_label?: string;
      cells_written?: { empty: number; white: number; black: number };
      queue_path?: string;
      reason?: string;
    }>("/api/cnn/feedback", payload),
};

// --- CNN-related response types ---

export interface CalibrationStatus {
  board_calibration_present: boolean;
  inner_warp_present: boolean;
  camera_reachable: boolean;
  board_calibration_age_seconds: number | null;
}

export interface CnnSourceDatasetMeta {
  name: string;
  empty_frames: number;
  white_squares: number;
  white_frames: number;
  black_squares: number;
  black_frames: number;
  bulk_empty_cells?: number;
  bulk_white_cells?: number;
  bulk_black_cells?: number;
  total_frames: number;
}

export interface CnnBuildStatus {
  frames_done: number;
  frames_total: number;
  current_file: string;
  cells_written_by_class: Record<string, number>;
  finished: boolean;
  error: string | null;
  report: { output_dir: string; counts_train: Record<string, number>; counts_val: Record<string, number> } | null;
  started_at: number;
}

export interface CnnTrainStatus {
  run_id: string;
  dataset: string;
  epoch: number;
  total_epochs: number;
  train_loss: number | null;
  train_acc: number | null;
  val_loss: number | null;
  val_acc: number | null;
  finished: boolean;
  error: string | null;
  started_at: number;
}

export interface CnnTrainArtifacts {
  run_id: string;
  training_curves_png: string | null;
  confusion_matrix_png: string | null;
  metrics: {
    train_acc?: number;
    val_acc?: number;
    class_names?: string[];
    per_class?: Record<string, { precision: number; recall: number; f1: number; support: number }>;
    confusion_matrix?: number[][];
  } | null;
}

export interface CnnModelMeta {
  run_id: string;
  finished_at: number;
  val_acc: number | null;
  dataset: string | null;
}

export interface CnnActiveModel {
  run_id: string | null;
  val_acc: number | null;
  dataset: string | null;
  loaded: boolean;
}

export type CvPrimary = "vision" | "cnn";

export interface CvRouterConfig {
  primary: CvPrimary;
  attempts_each: number;
  auto_save_validated: boolean;
  dataset_name: string;
  cnn_active: boolean;
}

export interface ValidatedDatasetCapture {
  ts: number;
  iso: string;
  capture_id: string;
  mode_used: string;
  session_id: string | null;
  move_uci: string | null;
  counts: { empty: number; white: number; black: number };
}

export interface ValidatedDatasetStats {
  dataset: string;
  exists: boolean;
  captures: number;
  last: ValidatedDatasetCapture[];
  bulk_empty: number;
  bulk_white: number;
  bulk_black: number;
  path?: string;
}

export interface CnnCellPrediction {
  row: number;
  col: number;
  label: "empty" | "white" | "black";
  confidence: number;
  probs: { empty: number; white: number; black: number };
}

export interface CnnScanResult {
  white_bitmap: number[][];
  black_bitmap: number[][];
  predictions: CnnCellPrediction[];
  warped_board_b64: string;
  cnn_overlay_b64: string;
  cell_crops_b64: string[];
  inference_ms: number;
  classical_comparison: {
    white_bitmap?: number[][];
    black_bitmap?: number[][];
    disagreement_count?: number;
    disagreement_cells?: { row: number; col: number; cnn: string; classical: string }[];
    error?: string;
  } | null;
}

export interface CnnScanCellResult {
  row: number;
  col: number;
  crop_b64: string;
  prediction: CnnCellPrediction;
  captured_at: number;
}

export interface ArucoDetection {
  id: number;
  corners: [number, number][];
  center: [number, number];
}

export interface ArucoDetectResult {
  status: "ok" | "incomplete";
  image_path: string;
  saved?: boolean;
  saved_path?: string | null;
  board?: {
    top_left: [number, number];
    top_right: [number, number];
    bottom_right: [number, number];
    bottom_left: [number, number];
  };
  detections: ArucoDetection[];
  used_ids?: number[];
  missing_ids?: number[];
  detected_ids?: number[];
  expected_ids?: number[];
  first_warp?: string;
  overlay?: string;
  layout?: Record<string, string>;
  error?: string;
}

export interface LabelSettings {
  frames_per_square: number;
  settle_ms: number;
  source_square: string;
  piece_type: string;
  lighting_note: string;
}

export interface LabelDatasetMeta {
  name: string;
  created_at: number;
  updated_at: number;
  settings: LabelSettings;
  empty_frames: number;
  white: Record<string, number>;
  black: Record<string, number>;
  bulk_empty?: Record<string, number>;
  bulk_white?: Record<string, number>;
  bulk_black?: Record<string, number>;
  has_exemplar_config: boolean;
  has_accuracy: boolean;
}

export interface LabelDatasetResponse {
  metadata: LabelDatasetMeta;
  paths: {
    dir: string;
    exemplar_config: string | null;
    accuracy: string | null;
  };
}

export interface LabelAccuracyReport {
  squares: Record<
    string,
    {
      row: number;
      col: number;
      total: number;
      correct: number;
      accuracy: number;
      confusion: Record<string, Record<string, number>>;
    }
  >;
  overall: { total: number; correct: number; accuracy: number };
}
