"""ArUco-based board calibration.

The user places 4 ArUco markers on 4 known chessboard squares (typically the
corner squares: a1, h1, h8, a8) and captures one image. We detect every
marker, pair its centroid with the centroid of its assigned board square, and
fit the homography from board-square space → image-pixel space. Applying that
homography to the four *outer* board corners gives us the same four-point
calibration the manual workflow produces — so everything downstream
(warp_from_calibration, inner-warp refinement, the labeling wizard) Just Works.

Once the user removes the markers, the saved calibration is unaffected — the
markers were a measurement device, not a runtime dependency.

Coordinate system
-----------------
We use board-square units: each chess square is one unit. The outer board
spans (0, 0) at the top-left of square a8 in image space, to (8, 8) at the
bottom-right of square h1. Square (col, row) has its center at
``(col + 0.5, row + 0.5)``.

Note: ``row 0 == rank 8 == top of the image``, matching the convention used
elsewhere in the pipeline (extract_8x8_cells, exemplar classifier, etc.).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from charm.vision.four_point_calibration import FourPointCalibration


# Default layout: 4 markers, IDs 0–3, on the four corner squares of the board.
# Top-of-image = rank 8, so a8 is row 0 col 0, h8 is row 0 col 7, etc.
DEFAULT_LAYOUT: dict[int, str] = {
    0: "a8",  # top-left
    1: "h8",  # top-right
    2: "h1",  # bottom-right
    3: "a1",  # bottom-left
}


def _square_center_board_units(square: str) -> tuple[float, float]:
    """Return (x, y) of the square's center in board-unit coords.

    (0, 0) is the top-left of the playing area, (8, 8) the bottom-right.
    """
    sq = square.lower()
    if len(sq) != 2 or sq[0] not in "abcdefgh" or sq[1] not in "12345678":
        raise ValueError(f"Invalid square: {square}")
    col = ord(sq[0]) - ord("a")  # a=0, h=7
    rank = int(sq[1])             # 1..8
    row = 8 - rank                # rank8 -> row0 (top); rank1 -> row7 (bottom)
    return (col + 0.5, row + 0.5)


@dataclass
class ArucoDetection:
    marker_id: int
    corners_px: list[tuple[float, float]]  # 4 corners in image pixels, CCW order
    center_px: tuple[float, float]

    def to_json(self) -> dict:
        return {
            "id": self.marker_id,
            "corners": self.corners_px,
            "center": self.center_px,
        }


def detect_aruco_markers(
    image: np.ndarray,
    dictionary_id: int = cv2.aruco.DICT_4X4_50,
) -> list[ArucoDetection]:
    """Detect ArUco markers using the modern OpenCV 4.7+ ArucoDetector API."""
    if image is None or image.size == 0:
        return []
    aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_id)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    corners_list, ids, _rejected = detector.detectMarkers(image)
    if ids is None or len(ids) == 0:
        return []
    out: list[ArucoDetection] = []
    for marker_id, corners in zip(ids.flatten().tolist(), corners_list):
        pts = corners.reshape(-1, 2).astype(float)
        center = pts.mean(axis=0)
        out.append(
            ArucoDetection(
                marker_id=int(marker_id),
                corners_px=[(float(x), float(y)) for x, y in pts],
                center_px=(float(center[0]), float(center[1])),
            )
        )
    return out


@dataclass
class ArucoCalibrationResult:
    calibration: FourPointCalibration
    detections: list[ArucoDetection]
    used_ids: list[int]
    missing_ids: list[int]
    homography: np.ndarray  # 3x3, board-units -> pixels
    timestamp: float


def compute_board_corners_from_markers(
    detections: list[ArucoDetection],
    marker_layout: Optional[dict[int, str]] = None,
) -> ArucoCalibrationResult:
    """Fit homography from board-unit coords to pixel coords using the markers'
    centers, then map the outer board corners through it.

    Raises ValueError if fewer than 4 markers from the layout are detected
    (we need at least 4 correspondences to fit a planar homography).
    """
    if marker_layout is None:
        marker_layout = DEFAULT_LAYOUT

    det_by_id = {d.marker_id: d for d in detections}
    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []  # (board, pixel)
    used_ids: list[int] = []
    missing_ids: list[int] = []
    for mid, sq in marker_layout.items():
        det = det_by_id.get(mid)
        if det is None:
            missing_ids.append(mid)
            continue
        board_xy = _square_center_board_units(sq)
        pairs.append((board_xy, det.center_px))
        used_ids.append(mid)

    if len(pairs) < 4:
        raise ValueError(
            f"Need at least 4 ArUco markers from the layout to compute a "
            f"homography; found {len(pairs)}. Missing IDs: {missing_ids}"
        )

    src = np.array([p[0] for p in pairs], dtype=np.float32)  # board units
    dst = np.array([p[1] for p in pairs], dtype=np.float32)  # pixels
    homography, _mask = cv2.findHomography(src, dst, method=0)
    if homography is None:
        raise ValueError("findHomography failed — markers may be collinear or coincident")

    # Map the four outer board corners (in board units) through H.
    board_corners = np.array(
        [
            [0.0, 0.0],  # top-left
            [8.0, 0.0],  # top-right
            [8.0, 8.0],  # bottom-right
            [0.0, 8.0],  # bottom-left
        ],
        dtype=np.float32,
    ).reshape(-1, 1, 2)
    img_corners = cv2.perspectiveTransform(board_corners, homography).reshape(-1, 2)

    cal = FourPointCalibration(
        top_left=(int(round(img_corners[0][0])), int(round(img_corners[0][1]))),
        top_right=(int(round(img_corners[1][0])), int(round(img_corners[1][1]))),
        bottom_right=(int(round(img_corners[2][0])), int(round(img_corners[2][1]))),
        bottom_left=(int(round(img_corners[3][0])), int(round(img_corners[3][1]))),
    )

    return ArucoCalibrationResult(
        calibration=cal,
        detections=detections,
        used_ids=used_ids,
        missing_ids=missing_ids,
        homography=homography,
        timestamp=time.time(),
    )


def draw_aruco_overlay(
    image: np.ndarray,
    result: ArucoCalibrationResult,
) -> np.ndarray:
    """Render detected markers + the projected board outline on top of `image`."""
    out = image.copy()

    # Draw each detected marker.
    for det in result.detections:
        pts = np.array(det.corners_px, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], True, (0, 255, 255), 2)
        cx, cy = map(int, det.center_px)
        cv2.circle(out, (cx, cy), 4, (0, 255, 255), -1)
        cv2.putText(
            out,
            f"id={det.marker_id}",
            (cx + 6, cy - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

    # Draw the projected board outline.
    cal = result.calibration
    quad = np.array(
        [cal.top_left, cal.top_right, cal.bottom_right, cal.bottom_left],
        dtype=np.int32,
    ).reshape(-1, 1, 2)
    cv2.polylines(out, [quad], True, (0, 255, 0), 3)

    for label, pt in [
        ("TL", cal.top_left), ("TR", cal.top_right),
        ("BR", cal.bottom_right), ("BL", cal.bottom_left),
    ]:
        cv2.circle(out, pt, 6, (0, 255, 0), -1)
        cv2.putText(
            out, label, (pt[0] + 8, pt[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6, (0, 255, 0), 2, cv2.LINE_AA,
        )

    return out
