// esp32_ui_box.ino
// Glue: WiFi connection + TCP server. All UI logic lives in uiController_esp32.

#include <Arduino.h>
#include <WiFi.h>
#include "../src/hardware/src/pins.h"
#include "../src/hardware/src/buttonInput.h"
#include "../src/hardware/src/uiState.h"
#include "../src/hardware/src/lcdDisplay.h"
#include "uiController_esp32.h"

// ── WiFi / TCP ────────────────────────────────────────────────────────────────
#define WIFI_SSID "SPOT-iot"
#define WIFI_PASSWORD "VitreuseLoukoumManquante7702"
#define TCP_PORT      8765

WiFiServer  tcpServer(TCP_PORT);
WiFiClient  client;

// ── Hardware objects (same classes as on the Mega, different pins) ─────────────
ButtonInput      buttonInput(CLK_PIN, DT_PIN, SW_PIN);
UIState          uiState;
LCDDisplay       lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIControllerESP32 uiController(buttonInput, uiState, lcd);

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    uiController.begin();
    lcd.update("ChArm", "Connecting...");

    Serial.print("Connecting to "); Serial.print(WIFI_SSID); Serial.print(" ");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.println();
    Serial.print("IP: "); Serial.println(WiFi.localIP());

    // Show IP on the LCD so you can pass it to --esp32-host
    lcd.update("WiFi OK", WiFi.localIP().toString().c_str());
    delay(1500);

    tcpServer.begin();
    Serial.print("TCP server on port "); Serial.println(TCP_PORT);
    lcd.update("Waiting Python", "...");
}

// ── Loop ─────────────────────────────────────────────────────────────────────
void loop() {
    // Accept new Python connection when none is active
    if (!client || !client.connected()) {
        WiFiClient incoming = tcpServer.available();
        if (incoming) {
            client = incoming;
            Serial.println("Python connected");
            lcd.update("Python OK", "Starting...");
            delay(500);
            uiController.begin();   // reset UI state for the new session
        } else {
            return;                 // nothing to do without a client
        }
    }

    uiController.loop(client);
}
