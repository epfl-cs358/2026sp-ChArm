#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// =========================
// WiFi
// =========================
const char* ssid = "SPOT-iot";
const char* password = "VitreuseLoukoumManquante7702";

// =========================
// AI Thinker ESP32-CAM pins
// =========================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// =========================
// Serial connection to Arduino Mega
// Based on your current wiring:
//
// ESP32-CAM GPIO3 -> Mega pin 19 / RX1
// ESP32-CAM GPIO1 -> Mega pin 18 / TX1
//
// Therefore:
// ESP32 receives from Mega TX1 on GPIO1
// ESP32 sends to Mega RX1 on GPIO3
// =========================
HardwareSerial MegaSerial(2);

#define MEGA_RX_PIN 1    // ESP32 receives data from Mega TX1 / pin 18
#define MEGA_TX_PIN 3    // ESP32 sends data to Mega RX1 / pin 19
#define MEGA_BAUD   9600

WebServer server(80);

// =========================
// Web page
// =========================
void handleRoot() {
  String html = R"rawliteral(
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>ESP32-CAM Test</title>
      <style>
        body {
          font-family: Arial, sans-serif;
          text-align: center;
          margin-top: 30px;
          background: #f5f5f5;
        }
        img {
          width: 320px;
          border: 1px solid #ccc;
          margin-top: 20px;
          background: white;
        }
        button {
          font-size: 16px;
          padding: 10px 20px;
          margin-top: 10px;
          cursor: pointer;
        }
        .info {
          margin-top: 15px;
          font-size: 14px;
          color: #555;
        }
      </style>
    </head>
    <body>
      <h1>ESP32-CAM Basic Test</h1>
      <p>Click to capture a new image.</p>

      <button onclick="refreshImage()">Capture</button>

      <div>
        <img id="photo" src="/capture?t=0" alt="camera image">
      </div>

      <div class="info">
        <p>Endpoint: <code>/capture</code></p>
        <p>Status: <code>/status</code></p>
      </div>

      <script>
        function refreshImage() {
          const img = document.getElementById('photo');
          img.src = '/capture?t=' + new Date().getTime();
        }
      </script>
    </body>
    </html>
  )rawliteral";

  server.send(200, "text/html", html);
}

// =========================
// Test capture for Mega command
// This does not send the image to Mega.
// It only checks whether the camera can capture.
// =========================
bool testCameraCapture() {
  camera_fb_t *fb = esp_camera_fb_get();

  if (!fb) {
    return false;
  }

  esp_camera_fb_return(fb);
  return true;
}

// =========================
// Capture image for browser / Python
// =========================
void handleCapture() {
  camera_fb_t *fb = esp_camera_fb_get();

  if (fb) {
    esp_camera_fb_return(fb);
    delay(100);
  }

  fb = esp_camera_fb_get();

  if (!fb) {
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  WiFiClient client = server.client();

  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
  server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
  server.sendHeader("Pragma", "no-cache");
  server.sendHeader("Expires", "0");
  server.setContentLength(fb->len);
  server.send(200);

  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);

  delay(200);
}

// =========================
// Status endpoint
// =========================
void handleStatus() {
  String status = "{";
  status += "\"wifi\":\"";
  status += (WiFi.status() == WL_CONNECTED ? "connected" : "disconnected");
  status += "\",";
  status += "\"ip\":\"";
  status += WiFi.localIP().toString();
  status += "\",";
  status += "\"mega_serial\":\"enabled\",";
  status += "\"mega_rx_pin\":";
  status += String(MEGA_RX_PIN);
  status += ",";
  status += "\"mega_tx_pin\":";
  status += String(MEGA_TX_PIN);
  status += "}";

  server.send(200, "application/json", status);
}

void handleNotFound() {
  server.send(404, "text/plain", "Not found");
}

// =========================
// Camera init
// =========================
bool initCamera() {
  camera_config_t config;

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;

  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA; // 640x480, better board/cell detail than QVGA
    config.jpeg_quality = 8;           // Lower number = less JPEG compression
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 10;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();

  if (s) {
    s->set_framesize(s, psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA);
    s->set_quality(s, 8);
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    s->set_saturation(s, 1);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 1);
    s->set_gain_ctrl(s, 1);
    s->set_gainceiling(s, (gainceiling_t)2);
    s->set_bpc(s, 1);
    s->set_wpc(s, 1);
    s->set_lenc(s, 1);
  }

  return true;
}

// =========================
// WiFi connection
// =========================
bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    return true;
  } else {
    return false;
  }
}

// =========================
// Mega command handler
// =========================
void handleMegaCommand() {
  if (!MegaSerial.available()) {
    return;
  }

  String cmd = MegaSerial.readStringUntil('\n');
  cmd.trim();

  if (cmd.length() == 0) {
    return;
  }

  if (cmd == "STATUS") {
    MegaSerial.println("ESP32_OK");
  }

  else if (cmd == "IP") {
    MegaSerial.print("IP ");
    MegaSerial.println(WiFi.localIP());
  }

  else if (cmd == "CAPTURE") {
    bool ok = testCameraCapture();

    if (ok) {
      MegaSerial.println("CAPTURE_OK");
    } else {
      MegaSerial.println("CAPTURE_FAIL");
    }
  }

  else {
    MegaSerial.println("UNKNOWN_CMD");
  }
}

// =========================
// Setup
// =========================
void setup() {
  // Do NOT use Serial.begin here, because GPIO1/GPIO3 are now used for MegaSerial.
  // GPIO1/GPIO3 are the default UART0 pins, so using Serial may conflict with Mega communication.

  MegaSerial.begin(MEGA_BAUD, SERIAL_8N1, MEGA_RX_PIN, MEGA_TX_PIN);

  delay(1000);

  MegaSerial.println("ESP32_BOOTING");

  if (!initCamera()) {
    MegaSerial.println("CAMERA_INIT_FAIL");

    while (true) {
      delay(1000);
    }
  }

  MegaSerial.println("CAMERA_INIT_OK");

  if (connectWiFi()) {
    server.on("/", HTTP_GET, handleRoot);
    server.on("/capture", HTTP_GET, handleCapture);
    server.on("/status", HTTP_GET, handleStatus);
    server.onNotFound(handleNotFound);

    server.begin();

    MegaSerial.print("WIFI_OK ");
    MegaSerial.println(WiFi.localIP());
  } else {
    MegaSerial.println("WIFI_FAIL");
  }
}

// =========================
// Loop
// =========================
void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    server.handleClient();
  }

  handleMegaCommand();
}
