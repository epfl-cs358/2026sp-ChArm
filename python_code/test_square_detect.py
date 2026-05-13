import cv2
import numpy as np

img = cv2.imread('../latest_raw.jpg')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Apply Gaussian blur
blur = cv2.GaussianBlur(gray, (5, 5), 0)

# Canny edge
edges = cv2.Canny(blur, 50, 150)
cv2.imwrite('debug_canny.jpg', edges)

# Dilate edges slightly to close gaps
kernel = np.ones((3, 3), np.uint8)
edges = cv2.dilate(edges, kernel, iterations=1)

cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

for c in cnts[:10]:
    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.02 * peri, True)
    if len(approx) == 4:
        print("Found a quad:", approx.reshape(4, 2))
        board_cnt = approx
        # draw
        cv2.drawContours(img, [board_cnt], -1, (0, 0, 255), 2)
        cv2.imwrite('debug_quad_detect.jpg', img)
        break
