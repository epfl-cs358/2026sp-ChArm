from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Optional

import cv2
import numpy as np


@dataclass(frozen=True)
class BoardDetectionParams:
    canny_low: int = 50
    canny_high: int = 150
    dilation_iterations: int = 1
    min_area: float = 5000.0
    max_side_ratio: float = 1.35
    min_area_ratio: float = 0.08
    max_area_ratio: float = 0.80
    min_color_ratio: float = 0.12
    padding_ratio: float = 0.015
    hough_refine: bool = False
    hough_canny_low: int = 30
    hough_canny_high: int = 100
    hough_threshold: int = 40
    hough_min_line_ratio: float = 0.33
    hough_max_line_gap: int = 18
    hough_max_line_distance: float = 35.0
    hough_min_area_keep: float = 0.97
    hough_max_area_grow: float = 1.08
    hough_max_corner_shift_ratio: float = 0.08


def build_black_mask(image: np.ndarray) -> np.ndarray:
    """
    Detect dark/black regions corresponding to the outer border.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Black / dark gray range
    lower_black = np.array([0, 0, 0], dtype=np.uint8)
    upper_black = np.array([180, 255, 80], dtype=np.uint8)

    mask = cv2.inRange(hsv, lower_black, upper_black)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    return mask


def build_color_mask(image: np.ndarray) -> np.ndarray:
    """
    Auxiliary mask for the pink and green chessboard squares.
    Used only to validate candidate board regions.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Green
    lower_green = np.array([35, 20, 80], dtype=np.uint8)
    upper_green = np.array([95, 140, 255], dtype=np.uint8)

    # Pink
    lower_pink = np.array([140, 20, 80], dtype=np.uint8)
    upper_pink = np.array([179, 170, 255], dtype=np.uint8)

    mask_green = cv2.inRange(hsv, lower_green, upper_green)
    mask_pink = cv2.inRange(hsv, lower_pink, upper_pink)

    mask = cv2.bitwise_or(mask_green, mask_pink)

    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    return mask


def contour_to_quad(contour: np.ndarray) -> np.ndarray:
    """
    Convert a contour to a 4-point quadrilateral.
    Prefer approxPolyDP; fall back to minAreaRect.
    """
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)

    if len(approx) == 4:
        return approx.reshape(4, 2).astype(np.float32)

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    return np.array(box, dtype=np.float32)


def quad_bounds(corners: np.ndarray, image_shape: tuple[int, ...]) -> tuple[int, int, int, int]:
    """
    Compute a clipped bounding rectangle for a 4-point quadrilateral.
    """
    h, w = image_shape[:2]

    xs = corners[:, 0]
    ys = corners[:, 1]

    x1 = max(0, int(np.floor(xs.min())))
    y1 = max(0, int(np.floor(ys.min())))
    x2 = min(w, int(np.ceil(xs.max())))
    y2 = min(h, int(np.ceil(ys.max())))

    return x1, y1, x2, y2


def quad_area_ratio(corners: np.ndarray, image_shape: tuple[int, ...]) -> float:
    h, w = image_shape[:2]
    image_area = float(max(1, h * w))
    return float(abs(cv2.contourArea(corners.astype(np.float32)))) / image_area


def quad_side_ratio(corners: np.ndarray) -> float:
    sides = [
        float(np.linalg.norm(corners[(idx + 1) % 4] - corners[idx]))
        for idx in range(4)
    ]
    return max(sides) / max(1.0, min(sides))


def quad_has_image_margin(
    corners: np.ndarray,
    image_shape: tuple[int, ...],
    margin_px: int = 8,
) -> bool:
    h, w = image_shape[:2]
    return bool(
        np.all(corners[:, 0] > margin_px)
        and np.all(corners[:, 0] < w - margin_px)
        and np.all(corners[:, 1] > margin_px)
        and np.all(corners[:, 1] < h - margin_px)
    )


def expand_quad(
    corners: np.ndarray,
    image_shape: tuple[int, ...],
    padding_ratio: float,
) -> np.ndarray:
    ordered = order_points(corners).astype(np.float32)
    center = np.mean(ordered, axis=0)
    expanded = center + (ordered - center) * (1.0 + padding_ratio)

    h, w = image_shape[:2]
    expanded[:, 0] = np.clip(expanded[:, 0], 0, w - 1)
    expanded[:, 1] = np.clip(expanded[:, 1], 0, h - 1)
    return order_points(expanded)


def candidate_has_board_colors(
    image: np.ndarray,
    corners: np.ndarray,
    min_color_ratio: float = 0.12,
) -> bool:
    """
    Validate that a candidate board region contains enough pink/green area.
    This helps reject unrelated black objects.
    """
    x1, y1, x2, y2 = quad_bounds(corners, image.shape)

    if x2 <= x1 or y2 <= y1:
        return False

    roi = image[y1:y2, x1:x2]
    color_mask = build_color_mask(roi)

    color_ratio = float(np.count_nonzero(color_mask)) / float(color_mask.size)
    return color_ratio >= min_color_ratio


def _line_from_segment(segment: np.ndarray) -> dict:
    x1, y1, x2, y2 = map(float, segment)
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx))
    if angle < -90:
        angle += 180
    if angle > 90:
        angle -= 180

    a = y1 - y2
    b = x2 - x1
    c = x1 * y2 - x2 * y1
    norm = math.hypot(a, b)
    if norm == 0:
        norm = 1.0

    return {
        "angle": angle,
        "length": length,
        "abc": (a / norm, b / norm, c / norm),
    }


def _intersect_lines(line_a: dict, line_b: dict) -> Optional[np.ndarray]:
    a1, b1, c1 = line_a["abc"]
    a2, b2, c2 = line_b["abc"]
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-6:
        return None
    x = (b1 * c2 - b2 * c1) / det
    y = (c1 * a2 - c2 * a1) / det
    return np.array([x, y], dtype=np.float32)


def _line_y_at(line: dict, x: float) -> float:
    a, b, c = line["abc"]
    if abs(b) < 1e-6:
        return float("inf")
    return float(-(a * x + c) / b)


def _line_x_at(line: dict, y: float) -> float:
    a, b, c = line["abc"]
    if abs(a) < 1e-6:
        return float("inf")
    return float(-(b * y + c) / a)


def find_board_frame_from_hough(
    image: np.ndarray,
    params: BoardDetectionParams,
) -> Optional[np.ndarray]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    black_mask = cv2.inRange(
        hsv,
        np.array([0, 0, 0], dtype=np.uint8),
        np.array([180, 255, 100], dtype=np.uint8),
    )
    edges = cv2.Canny(black_mask, params.hough_canny_low, params.hough_canny_high)
    h, w = image.shape[:2]
    min_line_length = int(min(h, w) * params.hough_min_line_ratio)
    raw_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=params.hough_threshold,
        minLineLength=min_line_length,
        maxLineGap=params.hough_max_line_gap,
    )

    if raw_lines is None:
        return None

    lines = [_line_from_segment(line[0]) for line in raw_lines]
    horizontal = [line for line in lines if abs(line["angle"]) <= 18]
    vertical = [line for line in lines if abs(abs(line["angle"]) - 90) <= 10]

    best_quad: Optional[np.ndarray] = None
    best_score = -1.0
    center_x = w / 2.0
    center_y = h / 2.0

    for line_top_a, line_top_b in itertools.combinations(horizontal, 2):
        if abs(line_top_a["angle"] - line_top_b["angle"]) > 4:
            continue
        top, bottom = sorted(
            [line_top_a, line_top_b],
            key=lambda line: _line_y_at(line, center_x),
        )

        for line_left_a, line_left_b in itertools.combinations(vertical, 2):
            if abs(abs(line_left_a["angle"]) - abs(line_left_b["angle"])) > 4:
                continue
            left, right = sorted(
                [line_left_a, line_left_b],
                key=lambda line: _line_x_at(line, center_y),
            )

            points = [
                _intersect_lines(top, left),
                _intersect_lines(top, right),
                _intersect_lines(bottom, right),
                _intersect_lines(bottom, left),
            ]
            if any(point is None for point in points):
                continue

            quad = np.array(points, dtype=np.float32)
            if not quad_has_image_margin(quad, image.shape, margin_px=4):
                continue

            area_ratio = quad_area_ratio(quad, image.shape)
            if not (params.min_area_ratio <= area_ratio <= params.max_area_ratio):
                continue

            side_ratio = quad_side_ratio(quad)
            if side_ratio > params.max_side_ratio:
                continue

            if not candidate_has_board_colors(image, quad, params.min_color_ratio):
                continue

            line_support = (
                top["length"] + bottom["length"] + left["length"] + right["length"]
            ) / float(max(1, h + w))
            score = area_ratio + 0.12 * line_support - 0.08 * abs(1.0 - side_ratio)
            if score > best_score:
                best_score = score
                best_quad = quad

    return best_quad


def find_largest_quadrilateral(
    image: np.ndarray,
    params: BoardDetectionParams | None = None,
) -> Optional[np.ndarray]:
    """
    Main detection (Restored to e2e-game-session logic):
    1. Detect dark/black border candidates
    2. Find large contours
    3. Convert to quadrilateral
    4. Validate candidate using internal pink/green content
    """
    if params is None:
        params = BoardDetectionParams()

    hough_quad = find_board_frame_from_hough(image, params)
    if hough_quad is not None:
        return expand_quad(hough_quad, image.shape, params.padding_ratio)

    black_mask = build_black_mask(image)

    contours, _ = cv2.findContours(black_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Sort by area descending so we test the strongest candidate first
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < params.min_area:
            continue

        quad = order_points(contour_to_quad(contour))
        area_ratio = quad_area_ratio(quad, image.shape)
        if not (params.min_area_ratio <= area_ratio <= params.max_area_ratio):
            continue
        if quad_side_ratio(quad) > params.max_side_ratio:
            continue
        if not quad_has_image_margin(quad, image.shape, margin_px=4):
            continue

        if candidate_has_board_colors(image, quad, min_color_ratio=params.min_color_ratio):
            return expand_quad(quad, image.shape, params.padding_ratio)

    return None


def draw_detected_corners(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    debug_image = image.copy()

    for idx, (x, y) in enumerate(corners.astype(int)):
        cv2.circle(debug_image, (x, y), 10, (0, 0, 255), -1)
        cv2.putText(
            debug_image,
            str(idx),
            (x + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 0, 0),
            2,
            cv2.LINE_AA,
        )

    pts = corners.astype(int).reshape((-1, 1, 2))
    cv2.polylines(debug_image, [pts], isClosed=True, color=(0, 255, 0), thickness=3)

    return debug_image


def order_points(pts: np.ndarray) -> np.ndarray:
    """
    Sorts 4 points into: Top-Left, Top-Right, Bottom-Right, Bottom-Left.
    """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect


def warp_board_preview(
    image: np.ndarray,
    corners: np.ndarray,
    output_size: int = 800,
) -> np.ndarray:
    src = order_points(corners)
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


def draw_board_detection_step(
    image: np.ndarray,
    corners: Optional[np.ndarray],
    output_size: int = 800,
) -> np.ndarray:
    if corners is None:
        return image.copy()

    detected = draw_detected_corners(image, corners)
    warped = warp_board_preview(image, corners, output_size=output_size)
    preview_h = image.shape[0]
    preview_w = int(warped.shape[1] * preview_h / warped.shape[0])
    warped_preview = cv2.resize(warped, (preview_w, preview_h), interpolation=cv2.INTER_AREA)
    return cv2.hconcat([detected, warped_preview])


def draw_black_mask_debug(image: np.ndarray) -> np.ndarray:
    mask = build_black_mask(image)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


def draw_color_mask_debug(image: np.ndarray) -> np.ndarray:
    mask = build_color_mask(image)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
