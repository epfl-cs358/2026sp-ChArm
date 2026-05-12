from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import cv2
import numpy as np


@dataclass
class FourPointCalibration:
    top_left: tuple[int, int]
    top_right: tuple[int, int]
    bottom_right: tuple[int, int]
    bottom_left: tuple[int, int]

    def as_array(self) -> np.ndarray:
        return np.array(
            [
                self.top_left,
                self.top_right,
                self.bottom_right,
                self.bottom_left,
            ],
            dtype=np.float32,
        )


@dataclass
class InnerWarpCalibration:
    top_left: tuple[int, int]
    top_right: tuple[int, int]
    bottom_right: tuple[int, int]
    bottom_left: tuple[int, int]

    def as_array(self) -> np.ndarray:
        return np.array(
            [
                self.top_left,
                self.top_right,
                self.bottom_right,
                self.bottom_left,
            ],
            dtype=np.float32,
        )


def draw_calibration_points(
    image: np.ndarray,
    calibration: FourPointCalibration,
) -> np.ndarray:
    debug_image = image.copy()

    points = [
        ("TL", calibration.top_left, (0, 255, 0)),
        ("TR", calibration.top_right, (0, 255, 0)),
        ("BR", calibration.bottom_right, (0, 255, 0)),
        ("BL", calibration.bottom_left, (0, 255, 0)),
    ]

    for label, (x, y), color in points:
        cv2.circle(debug_image, (x, y), 6, color, -1)
        cv2.putText(
            debug_image,
            f"{label} ({x},{y})",
            (x + 8, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    src = calibration.as_array().astype(int)
    cv2.line(debug_image, tuple(src[0]), tuple(src[1]), (255, 0, 0), 2)
    cv2.line(debug_image, tuple(src[1]), tuple(src[2]), (255, 0, 0), 2)
    cv2.line(debug_image, tuple(src[2]), tuple(src[3]), (255, 0, 0), 2)
    cv2.line(debug_image, tuple(src[3]), tuple(src[0]), (255, 0, 0), 2)

    return debug_image


def warp_from_calibration(
    image: np.ndarray,
    calibration: FourPointCalibration,
    output_size: int = 800,
) -> np.ndarray:
    src = calibration.as_array()
    dst = np.array(
        [
            [0, 0],
            [output_size - 1, 0],
            [output_size - 1, output_size - 1],
            [0, output_size - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (output_size, output_size))


def draw_inner_warp_points(
    image: np.ndarray,
    calibration: InnerWarpCalibration,
) -> np.ndarray:
    debug_image = image.copy()

    points = [
        ("TL", calibration.top_left, (0, 255, 255)),
        ("TR", calibration.top_right, (0, 255, 255)),
        ("BR", calibration.bottom_right, (0, 255, 255)),
        ("BL", calibration.bottom_left, (0, 255, 255)),
    ]

    for label, (x, y), color in points:
        cv2.circle(debug_image, (x, y), 6, color, -1)
        cv2.putText(
            debug_image,
            f"{label} ({x},{y})",
            (x + 8, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    src = calibration.as_array().astype(int)
    cv2.line(debug_image, tuple(src[0]), tuple(src[1]), (0, 255, 255), 2)
    cv2.line(debug_image, tuple(src[1]), tuple(src[2]), (0, 255, 255), 2)
    cv2.line(debug_image, tuple(src[2]), tuple(src[3]), (0, 255, 255), 2)
    cv2.line(debug_image, tuple(src[3]), tuple(src[0]), (0, 255, 255), 2)

    return debug_image


def refine_board_with_inner_corners(
    warped_board: np.ndarray,
    calibration: InnerWarpCalibration,
    output_size: int = 800,
) -> np.ndarray:
    src = calibration.as_array()
    dst = np.array(
        [
            [0, 0],
            [output_size - 1, 0],
            [output_size - 1, output_size - 1],
            [0, output_size - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(warped_board, matrix, (output_size, output_size))


def crop_and_refit_board(
    warped_board: np.ndarray,
    left: int = 0,
    top: int = 0,
    right: int = 0,
    bottom: int = 0,
    output_size: int = 800,
) -> np.ndarray:
    h, w = warped_board.shape[:2]

    x1 = max(0, left)
    y1 = max(0, top)
    x2 = min(w, w - right)
    y2 = min(h, h - bottom)

    if x2 <= x1 or y2 <= y1:
        raise ValueError("Invalid crop margins after warp.")

    cropped = warped_board[y1:y2, x1:x2]
    return cv2.resize(cropped, (output_size, output_size), interpolation=cv2.INTER_CUBIC)


def save_four_point_calibration(
    calibration: FourPointCalibration,
    json_path: str | Path,
) -> None:
    path = Path(json_path)
    data = {
        "top_left": list(calibration.top_left),
        "top_right": list(calibration.top_right),
        "bottom_right": list(calibration.bottom_right),
        "bottom_left": list(calibration.bottom_left),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_four_point_calibration(json_path: str | Path) -> FourPointCalibration:
    path = Path(json_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return FourPointCalibration(
        top_left=tuple(data["top_left"]),
        top_right=tuple(data["top_right"]),
        bottom_right=tuple(data["bottom_right"]),
        bottom_left=tuple(data["bottom_left"]),
    )


def save_inner_warp_calibration(
    calibration: InnerWarpCalibration,
    json_path: str | Path,
) -> None:
    path = Path(json_path)
    data = {
        "top_left": list(calibration.top_left),
        "top_right": list(calibration.top_right),
        "bottom_right": list(calibration.bottom_right),
        "bottom_left": list(calibration.bottom_left),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_inner_warp_calibration(json_path: str | Path) -> InnerWarpCalibration:
    path = Path(json_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return InnerWarpCalibration(
        top_left=tuple(data["top_left"]),
        top_right=tuple(data["top_right"]),
        bottom_right=tuple(data["bottom_right"]),
        bottom_left=tuple(data["bottom_left"]),
    )