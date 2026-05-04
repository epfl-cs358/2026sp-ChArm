import cv2
import numpy as np
import urllib.request

#ESP32_URL = "http://172.21.78.123/capture"
ESP32_URL = "http://172.21.73.228/capture"
RAW_PATH  = "latest_raw.jpg"

def fetch_raw_image() -> str:
    """从 ESP32-CAM 抓图，保存原图，返回路径"""
    img_resp = urllib.request.urlopen(ESP32_URL, timeout=5)
    img_np = np.array(bytearray(img_resp.read()), dtype=np.uint8)
    img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("Failed to decode image from ESP32-CAM.")
    cv2.imwrite(RAW_PATH, img)
    print(f"Image saved to: {RAW_PATH}")
    return RAW_PATH


if __name__ == "__main__":
    fetch_raw_image()