from __future__ import annotations

from typing import Optional

import cv2
import numpy as np


def preprocess_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    return edges


def find_largest_quadrilateral(image: np.ndarray) -> Optional[np.ndarray]:
    """
    Return board corners as a (4, 2) array if a large quadrilateral is found.
    Otherwise return None.
    """
    edges = preprocess_image(image)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    largest_quad = None
    largest_area = 0.0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 5000:
            continue

        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

        if len(approx) == 4 and area > largest_area:
            largest_area = area
            largest_quad = approx

    if largest_quad is None:
        return None

    return largest_quad.reshape(4, 2).astype(np.float32)


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