import cv2
import numpy as np
import urllib.request
import urllib.error
from pathlib import Path

# Change this IP if ESP32-CAM prints a new IP in Serial Monitor.
ESP32_URL = "http://172.21.73.228/capture"

# This file is:
#   python_code/src/charm/vision/transferphoto.py
#
# parents[3] is:
#   python_code/
PYTHON_CODE_ROOT = Path(__file__).resolve().parents[3]

# Save ESP32-CAM capture here:
#   python_code/latest_raw.jpg
RAW_PATH = PYTHON_CODE_ROOT / "latest_raw.jpg"


def fetch_raw_image() -> str:
    """Fetch one JPEG image from ESP32-CAM, save it locally, and return the saved path."""
    print(f"Fetching image from ESP32-CAM: {ESP32_URL}")

    try:
        response = urllib.request.urlopen(ESP32_URL, timeout=10)
        data = response.read()

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ESP32-CAM returned HTTP {e.code}: {body}")

    except Exception as e:
        raise RuntimeError(f"Failed to connect to ESP32-CAM at {ESP32_URL}: {e}")

    img_np = np.array(bytearray(data), dtype=np.uint8)
    img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

    if img is None:
        raise RuntimeError("Failed to decode image from ESP32-CAM.")

    ok = cv2.imwrite(str(RAW_PATH), img)

    if not ok:
        raise RuntimeError(f"Failed to save image to: {RAW_PATH}")

    print(f"Image saved to: {RAW_PATH}")
    return str(RAW_PATH)


if __name__ == "__main__":
    fetch_raw_image()