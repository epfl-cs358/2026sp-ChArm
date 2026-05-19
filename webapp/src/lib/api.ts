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

  tuneCv: (payload: {
    annotations: { row: number; col: number; label: "empty" | "white" | "black" }[];
    params: PipelineParams;
    image_path?: string;
  }) =>
    post<{
      status: string;
      path: string;
      tuning: {
        occupancy_threshold: number;
        occupancy_delta_threshold?: number;
        white_threshold: number;
        black_threshold: number;
        white_delta_threshold?: number;
        black_delta_threshold?: number;
        saved_at: number;
        samples: Record<
          string,
          {
            row: number;
            col: number;
            occupancy_score: number;
            brightness_score: number;
            dark_score?: number;
            occupancy_delta?: number;
            bright_delta?: number;
            dark_delta?: number;
          }[]
        >;
      };
    }>("/api/pipeline/tune", payload),

  getCvTuning: () =>
    get<{
      exists: boolean;
      tuning: {
        occupancy_threshold: number;
        occupancy_delta_threshold?: number;
        white_threshold: number;
        black_threshold: number;
        white_delta_threshold?: number;
        black_delta_threshold?: number;
        saved_at?: number;
      } | null;
    }>("/api/pipeline/tuning"),

  clearCvTuning: () =>
    fetch(`${API}/api/pipeline/tuning`, { method: "DELETE" }).then((r) => r.json()),

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

  getRawImage: () => get<{ image: string; path: string }>("/api/image/raw"),

  readImage: (path: string) => post<{ image: string; path: string }>("/api/image/read", { path }),

  captureFromCamera: (url?: string) => post<{ status: string; image: string; path: string }>("/api/capture", { url }),

  getDefaults: () => get<PipelineParams>("/api/params/defaults"),

  getSavedParams: () =>
    get<{
      exists: boolean;
      path: string;
      data?: {
        params: PipelineParams;
        score?: Record<string, unknown>;
        labels?: string[][];
        source_image?: string;
        saved_at?: number;
      };
    }>("/api/params/saved"),

  saveParams: (payload: {
    params: PipelineParams;
    score?: unknown;
    labels?: string[][];
    source_image?: string;
  }) => put<{ status: string; path: string }>("/api/params/saved", payload),

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
  }) =>
    post<{ saved_frames: number } & LabelDatasetResponse>(
      `/api/labeling/datasets/${encodeURIComponent(name)}/capture-square`,
      payload,
    ),

  labelingArm: (name: string, payload: {
    color: "white" | "black";
    square: string;
    action: "pickup_source" | "place_target" | "return_to_source" | "home";
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
};

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
