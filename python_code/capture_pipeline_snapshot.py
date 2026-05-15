from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(REPO_ROOT))

from charm.vision.transferphoto import fetch_raw_image
from webapp_backend.api_server import PipelineParams, run_pipeline


IMAGE_KEYS = [
    "original",
    "board_edges_debug",
    "first_warp",
    "refined_warp",
    "preprocessed",
    "grid_debug",
    "occupancy_debug",
    "piece_color_debug",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture or copy one board photo, run the Python vision pipeline, and save a reproducible debug snapshot.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--camera", action="store_true", help="Capture from ESP32-CAM using transferphoto.py.")
    source.add_argument("--image", help="Use an existing image instead of capturing from the camera.")
    parser.add_argument("--url", help="Override camera URL, e.g. http://172.21.73.228/capture.")
    parser.add_argument("--name", help="Snapshot folder name. Defaults to a timestamp.")
    parser.add_argument("--out-dir", default=str(ROOT / "debug_snapshots"), help="Directory that will contain snapshots.")
    parser.add_argument("--auto-detect-board", action="store_true", help="Use automatic outer-board detection.")
    parser.add_argument("--saved-board", action="store_true", help="Use saved board_calibration.json instead of auto detection.")
    parser.add_argument("--inner-warp", action="store_true", help="Apply inner_warp_calibration.json.")
    parser.add_argument("--no-inner-warp", action="store_true", help="Disable inner warp.")
    parser.add_argument("--occupancy-threshold", type=float, help="Override occupancy threshold.")
    parser.add_argument("--white-threshold", type=float, help="Override white piece threshold.")
    parser.add_argument("--black-threshold", type=float, help="Override black piece threshold.")
    parser.add_argument("--warp-size", type=int, help="Override warp size.")
    return parser.parse_args()


def write_b64_image(path: Path, value: str) -> None:
    path.write_bytes(base64.b64decode(value))


def build_params(args: argparse.Namespace) -> PipelineParams:
    params = PipelineParams()

    if args.auto_detect_board:
        params.auto_detect_board = True
    if args.saved_board:
        params.auto_detect_board = False
    if args.inner_warp:
        params.apply_inner_warp = True
    if args.no_inner_warp:
        params.apply_inner_warp = False
    if args.occupancy_threshold is not None:
        params.occupancy_threshold = args.occupancy_threshold
    if args.white_threshold is not None:
        params.white_threshold = args.white_threshold
    if args.black_threshold is not None:
        params.black_threshold = args.black_threshold
    if args.warp_size is not None:
        params.warp_size = args.warp_size

    return params


def main() -> None:
    args = parse_args()
    snapshot_name = args.name or datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = Path(args.out_dir) / snapshot_name
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    raw_path = snapshot_dir / "raw.jpg"
    if args.camera:
        fetch_raw_image(args.url, output_path=raw_path)
    else:
        source = Path(args.image)
        if not source.exists():
            raise FileNotFoundError(f"Image not found: {source}")
        shutil.copyfile(source, raw_path)

    image = cv2.imread(str(raw_path))
    if image is None:
        raise RuntimeError(f"Failed to decode image: {raw_path}")

    params = build_params(args)
    result = run_pipeline(image, params)

    for key in IMAGE_KEYS:
        value = result.get(key)
        if value:
            write_b64_image(snapshot_dir / f"{key}.jpg", value)

    summary = {
        "snapshot_dir": str(snapshot_dir),
        "raw_path": str(raw_path),
        "params": params.model_dump() if hasattr(params, "model_dump") else params.dict(),
        "board_detection_mode": result.get("board_detection_mode"),
        "warp_error": result.get("warp_error"),
        "timings_ms": result.get("timings_ms"),
        "occupancy_matrix": result.get("occupancy_matrix"),
        "white_bitmap": result.get("white_bitmap"),
        "black_bitmap": result.get("black_bitmap"),
    }
    (snapshot_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Snapshot saved: {snapshot_dir}")
    print(f"Raw image: {raw_path}")
    print(f"Board detection: {summary['board_detection_mode']}")
    if summary["warp_error"]:
        print(f"Warp error: {summary['warp_error']}")
    print("Debug images:")
    for key in IMAGE_KEYS:
        path = snapshot_dir / f"{key}.jpg"
        if path.exists():
            print(f"- {path}")
    print(f"Summary: {snapshot_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
