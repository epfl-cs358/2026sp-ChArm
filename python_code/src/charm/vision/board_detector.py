from __future__ import annotations

from typing import Optional

import cv2
import numpy as np


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


def find_largest_quadrilateral(image: np.ndarray) -> Optional[np.ndarray]:
    """
    Main detection:
    1. Detect dark/black border candidates
    2. Find large contours
    3. Convert to quadrilateral
    4. Validate candidate using internal pink/green content
    """
    black_mask = build_black_mask(image)

    contours, _ = cv2.findContours(black_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Sort by area descending so we test the strongest candidate first
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 5000:
            continue

        quad = contour_to_quad(contour)

        if candidate_has_board_colors(image, quad, min_color_ratio=0.12):
            return quad

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


def draw_black_mask_debug(image: np.ndarray) -> np.ndarray:
    mask = build_black_mask(image)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


def draw_color_mask_debug(image: np.ndarray) -> np.ndarray:
    mask = build_color_mask(image)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)