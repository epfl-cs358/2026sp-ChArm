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
// Camera options API
// =========================
int parseIntArg(const String &name, int defaultValue) {
  if (!server.hasArg(name)) {
    return defaultValue;
  }

  return server.arg(name).toInt();
}

void handleOptions() {
  sensor_t *s = esp_camera_sensor_get();

  if (!s) {
    server.send(500, "application/json", "{\"ok\":false,\"error\":\"sensor_unavailable\"}");
    return;
  }

  bool applied = false;

  if (server.hasArg("brightness")) {
    s->set_brightness(s, parseIntArg("brightness", 0));
    applied = true;
  }
  if (server.hasArg("contrast")) {
    s->set_contrast(s, parseIntArg("contrast", 0));
    applied = true;
  }
  if (server.hasArg("saturation")) {
    s->set_saturation(s, parseIntArg("saturation", 0));
    applied = true;
  }
  if (server.hasArg("denoise")) {
    s->set_denoise(s, parseIntArg("denoise", 0));
    applied = true;
  }
  if (server.hasArg("gainceiling")) {
    s->set_gainceiling(s, (gainceiling_t)parseIntArg("gainceiling", 0));
    applied = true;
  }
  if (server.hasArg("quality")) {
    s->set_quality(s, parseIntArg("quality", 12));
    applied = true;
  }
  if (server.hasArg("awb")) {
    s->set_whitebal(s, parseIntArg("awb", 1));
    applied = true;
  }
  if (server.hasArg("awb_gain")) {
    s->set_awb_gain(s, parseIntArg("awb_gain", 1));
    applied = true;
  }
  if (server.hasArg("wb_mode")) {
    s->set_wb_mode(s, parseIntArg("wb_mode", 0));
    applied = true;
  }
  if (server.hasArg("exposure_ctrl")) {
    s->set_exposure_ctrl(s, parseIntArg("exposure_ctrl", 1));
    applied = true;
  }
  if (server.hasArg("aec_value")) {
    s->set_aec_value(s, parseIntArg("aec_value", 300));
    applied = true;
  }
  if (server.hasArg("ae_level")) {
    s->set_ae_level(s, parseIntArg("ae_level", 0));
    applied = true;
  }
  if (server.hasArg("gain_ctrl")) {
    s->set_gain_ctrl(s, parseIntArg("gain_ctrl", 1));
    applied = true;
  }
  if (server.hasArg("agc_gain")) {
    s->set_agc_gain(s, parseIntArg("agc_gain", 0));
    applied = true;
  }
  if (server.hasArg("special_effect")) {
    s->set_special_effect(s, parseIntArg("special_effect", 0));
    applied = true;
  }
  if (server.hasArg("hmirror")) {
    s->set_hmirror(s, parseIntArg("hmirror", 0));
    applied = true;
  }
  if (server.hasArg("vflip")) {
    s->set_vflip(s, parseIntArg("vflip", 0));
    applied = true;
  }

  String response = "{\"ok\":";
  response += (applied ? "true" : "false");
  response += "}";
  server.send(200, "application/json", response);
}

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
          width: 480px;
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
        .controls {
          width: 520px;
          margin: 20px auto;
          padding: 15px 20px;
          background: #ffffff;
          border: 1px solid #ddd;
          border-radius: 8px;
          text-align: left;
        }
        .row {
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 8px 0;
        }
        .row label {
          flex: 0 0 120px;
          font-size: 14px;
          color: #333;
        }
        .row input[type="range"] {
          flex: 1;
        }
        .value {
          width: 40px;
          text-align: right;
          font-size: 13px;
          color: #555;
        }
        .toggle {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          color: #333;
          margin: 8px 0;
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

      <div class="controls">
        <div class="row">
          <label for="brightness">Brightness</label>
          <input id="brightness" type="range" min="-2" max="2" step="1" value="1" oninput="applyRange(this)">
          <span class="value" id="brightnessVal">1</span>
        </div>
        <div class="row">
          <label for="contrast">Contrast</label>
          <input id="contrast" type="range" min="-2" max="2" step="1" value="1" oninput="applyRange(this)">
          <span class="value" id="contrastVal">1</span>
        </div>
        <div class="row">
          <label for="saturation">Saturation</label>
          <input id="saturation" type="range" min="-2" max="2" step="1" value="0" oninput="applyRange(this)">
          <span class="value" id="saturationVal">0</span>
        </div>
        <div class="row">
          <label for="denoise">Denoise</label>
          <input id="denoise" type="range" min="0" max="1" step="1" value="1" oninput="applyRange(this)">
          <span class="value" id="denoiseVal">1</span>
        </div>
        <div class="row">
          <label for="quality">JPEG Quality</label>
          <input id="quality" type="range" min="10" max="63" step="1" value="12" oninput="applyRange(this)">
          <span class="value" id="qualityVal">12</span>
        </div>
        <div class="row">
          <label for="gainceiling">Gain Ceiling</label>
          <input id="gainceiling" type="range" min="0" max="6" step="1" value="2" oninput="applyRange(this)">
          <span class="value" id="gainceilingVal">2</span>
        </div>
        <div class="row">
          <label for="aec_value">AEC Value</label>
          <input id="aec_value" type="range" min="0" max="1200" step="10" value="300" oninput="applyRange(this)">
          <span class="value" id="aec_valueVal">300</span>
        </div>
        <div class="row">
          <label for="ae_level">AE Level</label>
          <input id="ae_level" type="range" min="-2" max="2" step="1" value="0" oninput="applyRange(this)">
          <span class="value" id="ae_levelVal">0</span>
        </div>
        <div class="row">
          <label for="agc_gain">AGC Gain</label>
          <input id="agc_gain" type="range" min="0" max="30" step="1" value="0" oninput="applyRange(this)">
          <span class="value" id="agc_gainVal">0</span>
        </div>
        <div class="row">
          <label for="special_effect">Effect</label>
          <input id="special_effect" type="range" min="0" max="6" step="1" value="0" oninput="applyRange(this)">
          <span class="value" id="special_effectVal">0</span>
        </div>
        <div class="toggle">
          <input id="awb" type="checkbox" checked onchange="applyToggle(this)">
          <label for="awb">Auto White Balance</label>
        </div>
        <div class="toggle">
          <input id="awb_gain" type="checkbox" checked onchange="applyToggle(this)">
          <label for="awb_gain">AWB Gain</label>
        </div>
        <div class="toggle">
          <input id="exposure_ctrl" type="checkbox" checked onchange="applyToggle(this)">
          <label for="exposure_ctrl">Auto Exposure</label>
        </div>
        <div class="toggle">
          <input id="gain_ctrl" type="checkbox" checked onchange="applyToggle(this)">
          <label for="gain_ctrl">Auto Gain</label>
        </div>
        <div class="toggle">
          <input id="hmirror" type="checkbox" onchange="applyToggle(this)">
          <label for="hmirror">Mirror</label>
        </div>
        <div class="toggle">
          <input id="vflip" type="checkbox" onchange="applyToggle(this)">
          <label for="vflip">Flip</label>
        </div>
      </div>

      <div class="info">
        <p>Endpoint: <code>/capture</code></p>
        <p>Options: <code>/options</code></p>
        <p>Status: <code>/status</code></p>
      </div>

      <script>
        function refreshImage() {
          const img = document.getElementById('photo');
          img.src = '/capture?t=' + new Date().getTime();
        }

        function applyRange(el) {
          const valueEl = document.getElementById(el.id + 'Val');
          if (valueEl) {
            valueEl.textContent = el.value;
          }
          fetch('/options?' + encodeURIComponent(el.id) + '=' + encodeURIComponent(el.value));
        }

        function applyToggle(el) {
          const value = el.checked ? 1 : 0;
          fetch('/options?' + encodeURIComponent(el.id) + '=' + value);
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

  framesize_t frameSize = FRAMESIZE_UXGA;
  config.frame_size = frameSize;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    // Fallback to a lower resolution if UXGA is not supported.
    frameSize = FRAMESIZE_SVGA;
    config.frame_size = frameSize;
    err = esp_camera_init(&config);

    if (err != ESP_OK) {
      return false;
    }
  }

  sensor_t *s = esp_camera_sensor_get();

  if (s) {
    s->set_brightness(s, 1);
    s->set_saturation(s, 0);
    s->set_contrast(s, 1);
    s->set_denoise(s, 1);
    s->set_gainceiling(s, GAINCEILING_4X);
    s->set_framesize(s, frameSize);
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
    server.on("/options", HTTP_GET, handleOptions);
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
