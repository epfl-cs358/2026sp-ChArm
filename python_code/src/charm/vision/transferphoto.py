import cv2
import numpy as np
import os
import urllib.request
import urllib.error
from pathlib import Path

# Change this IP if ESP32-CAM prints a new IP in Serial Monitor.
DEFAULT_ESP32_URL = "http://172.21.73.228/capture"
ESP32_URL_ENV = "CHARM_ESP32_URL"

# Saves to: 2026sp-ChArm/python_code/latest_raw.jpg
ROOT = Path(__file__).resolve().parents[3]
RAW_PATH = ROOT / "latest_raw.jpg"


def fetch_raw_image(url: str | None = None, output_path: str | Path | None = None) -> str:
    """Fetch one JPEG image from ESP32-CAM, save it locally, and return the saved path."""
    esp32_url = url or os.environ.get(ESP32_URL_ENV, DEFAULT_ESP32_URL)
    save_path = Path(output_path) if output_path is not None else RAW_PATH
    print(f"Fetching image from ESP32-CAM: {esp32_url}")

    try:
        response = urllib.request.urlopen(esp32_url, timeout=10)
        data = response.read()

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ESP32-CAM returned HTTP {e.code}: {body}")

    except Exception as e:
        raise RuntimeError(
            f"Failed to connect to ESP32-CAM at {esp32_url}: {e}. "
            f"Set {ESP32_URL_ENV}=http://<camera-ip>/capture if the camera IP changed."
        )

    img_np = np.array(bytearray(data), dtype=np.uint8)
    img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

    if img is None:
        raise RuntimeError("Failed to decode image from ESP32-CAM.")

    save_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(save_path), img)

    if not ok:
        raise RuntimeError(f"Failed to save image to: {save_path}")

    print(f"Image saved to: {save_path}")
    return str(save_path)


if __name__ == "__main__":
    fetch_raw_image()
