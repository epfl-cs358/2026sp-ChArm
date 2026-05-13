from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass(frozen=True)
class BoardDetectionParams:
    canny_low: int = 50
    canny_high: int = 150
    dilation_iterations: int = 1
    min_area: float = 5000.0
    max_side_ratio: float = 1.18
    min_area_ratio: float = 0.08
    max_area_ratio: float = 0.80
    min_color_ratio: float = 0.12
    padding_ratio: float = 0.006
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


def side_lengths(corners: np.ndarray) -> np.ndarray:
    return np.array(
        [
            np.linalg.norm(corners[(idx + 1) % 4] - corners[idx])
            for idx in range(4)
        ],
        dtype=np.float32,
    )


def expand_quad(
    corners: np.ndarray,
    image_shape: tuple[int, ...],
    padding_ratio: float = 0.006,
) -> np.ndarray:
    """
    Add a small outward margin to avoid cutting into the physical board.

    Auto-detected edges often land on the inside of the black border by a few
    pixels. Expanding from the quad center is intentionally conservative: the
    following warp can tolerate a thin outside margin much better than it can
    tolerate a clipped square.
    """
    ordered = order_points(corners).astype(np.float32)
    center = np.mean(ordered, axis=0)
    expanded = center + (ordered - center) * (1.0 + padding_ratio)

    h, w = image_shape[:2]
    expanded[:, 0] = np.clip(expanded[:, 0], 0, w - 1)
    expanded[:, 1] = np.clip(expanded[:, 1], 0, h - 1)
    return order_points(expanded)


def corners_are_inside_image(
    corners: np.ndarray,
    image_shape: tuple[int, ...],
    tolerance: float = 3.0,
) -> bool:
    h, w = image_shape[:2]
    xs = corners[:, 0]
    ys = corners[:, 1]
    return bool(
        xs.min() >= -tolerance
        and ys.min() >= -tolerance
        and xs.max() <= (w - 1) + tolerance
        and ys.max() <= (h - 1) + tolerance
    )


def candidate_score(image: np.ndarray, corners: np.ndarray) -> Optional[float]:
    return candidate_score_with_params(image, corners, BoardDetectionParams())


def candidate_score_with_params(
    image: np.ndarray,
    corners: np.ndarray,
    params: BoardDetectionParams,
) -> Optional[float]:
    """
    Score a detected quadrilateral as a chessboard candidate.

    The detector should follow the physical board edges. Large contours caused
    by the orange arm, shadows, or image borders are usually less square or run
    outside the image, so they are rejected before ranking by area.
    """
    ordered = order_points(corners)
    lengths = side_lengths(ordered)
    shortest_side = float(lengths.min())

    if shortest_side < 60.0:
        return None

    side_ratio = float(lengths.max() / shortest_side)
    if side_ratio > params.max_side_ratio:
        return None

    if not corners_are_inside_image(ordered, image.shape):
        return None

    image_area = float(image.shape[0] * image.shape[1])
    quad_area = float(cv2.contourArea(ordered))
    area_ratio = quad_area / image_area
    if area_ratio < params.min_area_ratio or area_ratio > params.max_area_ratio:
        return None

    if not candidate_has_board_colors(image, ordered, min_color_ratio=params.min_color_ratio):
        return None

    return quad_area / side_ratio


def line_from_points(p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    x1, y1 = p1
    x2, y2 = p2
    a = y1 - y2
    b = x2 - x1
    c = x1 * y2 - x2 * y1
    norm = float(np.sqrt(a * a + b * b))
    if norm == 0:
        raise ValueError("Cannot build a line from identical points.")
    return np.array([a / norm, b / norm, c / norm], dtype=np.float32)


def line_distance(line: np.ndarray, point: np.ndarray) -> float:
    return float(abs(line[0] * point[0] + line[1] * point[1] + line[2]))


def line_intersection(line_a: np.ndarray, line_b: np.ndarray) -> Optional[np.ndarray]:
    a1, b1, c1 = line_a
    a2, b2, c2 = line_b
    det = a1 * b2 - a2 * b1
    if abs(float(det)) < 1e-6:
        return None
    return np.array(
        [
            (b1 * c2 - b2 * c1) / det,
            (c1 * a2 - c2 * a1) / det,
        ],
        dtype=np.float32,
    )


def refine_quad_with_hough_lines(
    image: np.ndarray,
    corners: np.ndarray,
    params: BoardDetectionParams | None = None,
) -> np.ndarray:
    """
    Refine a plausible board quadrilateral by snapping each side to long Hough
    line segments. This fixes partial contours when pieces or the robot arm
    interrupt the black outer border.
    """
    params = params or BoardDetectionParams()
    if not params.hough_refine:
        return order_points(corners)

    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, params.hough_canny_low, params.hough_canny_high)
    raw_lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=params.hough_threshold,
        minLineLength=int(min(h, w) * params.hough_min_line_ratio),
        maxLineGap=params.hough_max_line_gap,
    )
    if raw_lines is None:
        return corners

    horizontal: list[tuple[np.ndarray, float]] = []
    vertical: list[tuple[np.ndarray, float]] = []

    for x1, y1, x2, y2 in raw_lines[:, 0, :]:
        p1 = np.array([float(x1), float(y1)], dtype=np.float32)
        p2 = np.array([float(x2), float(y2)], dtype=np.float32)
        length = float(np.linalg.norm(p2 - p1))
        angle = float(np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0])))
        if angle < -90:
            angle += 180
        if angle > 90:
            angle -= 180

        line = line_from_points(p1, p2)
        if abs(angle) <= 20:
            horizontal.append((line, length))
        elif abs(angle) >= 70:
            vertical.append((line, length))

    def choose_side_line(
        p1: np.ndarray,
        p2: np.ndarray,
        candidates: list[tuple[np.ndarray, float]],
    ) -> Optional[np.ndarray]:
        if not candidates:
            return None

        side_length = float(np.linalg.norm(p2 - p1))
        best_line: Optional[np.ndarray] = None
        best_score = float("inf")
        for line, length in candidates:
            score = (line_distance(line, p1) + line_distance(line, p2)) / 2
            score += max(0.0, side_length - length) * 0.03
            if score < best_score:
                best_score = score
                best_line = line

        if best_score > params.hough_max_line_distance:
            return None
        return best_line

    ordered = order_points(corners)
    top = choose_side_line(ordered[0], ordered[1], horizontal)
    right = choose_side_line(ordered[1], ordered[2], vertical)
    bottom = choose_side_line(ordered[3], ordered[2], horizontal)
    left = choose_side_line(ordered[0], ordered[3], vertical)

    if top is None or right is None or bottom is None or left is None:
        return ordered

    intersections = [
        line_intersection(top, left),
        line_intersection(top, right),
        line_intersection(bottom, right),
        line_intersection(bottom, left),
    ]
    if any(point is None for point in intersections):
        return ordered

    refined = order_points(np.array(intersections, dtype=np.float32))
    if candidate_score_with_params(image, refined, params) is None:
        return ordered

    original_area = float(cv2.contourArea(ordered))
    refined_area = float(cv2.contourArea(refined))
    if (
        refined_area < original_area * params.hough_min_area_keep
        or refined_area > original_area * params.hough_max_area_grow
    ):
        return ordered

    max_corner_shift = float(np.max(np.linalg.norm(refined - ordered, axis=1)))
    max_expected_shift = float(np.min(side_lengths(ordered)) * params.hough_max_corner_shift_ratio)
    if max_corner_shift > max_expected_shift:
        return ordered

    return refined


def find_largest_quadrilateral(
    image: np.ndarray,
    params: BoardDetectionParams | None = None,
) -> Optional[np.ndarray]:
    """
    Main detection using edge detection:
    1. Grayscale & Blur
    2. Canny Edge Detection & Dilation
    3. Score plausible board-edge quadrilaterals
    4. Return the best candidate ordered as TL, TR, BR, BL
    """
    params = params or BoardDetectionParams()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, params.canny_low, params.canny_high)

    if params.dilation_iterations > 0:
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=params.dilation_iterations)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    best_quad: Optional[np.ndarray] = None
    best_score = 0.0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < params.min_area:
            continue

        quad = contour_to_quad(contour)
        score = candidate_score_with_params(image, quad, params)
        if score is None or score <= best_score:
            continue

        best_score = score
        best_quad = order_points(quad)

    if best_quad is None:
        return None

    refined = refine_quad_with_hough_lines(image, best_quad, params)
    return expand_quad(refined, image.shape, params.padding_ratio)


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


def draw_black_mask_debug(image: np.ndarray) -> np.ndarray:
    mask = build_black_mask(image)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


def draw_color_mask_debug(image: np.ndarray) -> np.ndarray:
    mask = build_color_mask(image)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
