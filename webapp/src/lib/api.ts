import {
  ClassifierStatus,
  ClassifierTrainResult,
  PipelineParams,
  PipelineResult,
  CalibrationData,
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

  getCalibration: () => get<CalibrationData>("/api/calibration"),

  updateCalibration: (data: Partial<CalibrationData>) =>
    put<{ status: string }>("/api/calibration", data),

  getRawImage: () => get<{ image: string; path: string }>("/api/image/raw"),

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

  disconnectRobot: () => post<{ status: string }>("/api/robot/disconnect", {}),
};
