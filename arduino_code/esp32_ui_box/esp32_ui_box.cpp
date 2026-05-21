// esp32_ui_box.ino
// Glue: WiFi connection + TCP server. All UI logic lives in uiController_esp32.

#include <Arduino.h>
#include <WiFi.h>
#include "../src/hardware/src/pins.h"
#include "../src/hardware/src/buttonInput.h"
#include "../src/hardware/src/uiState.h"
#include "../src/hardware/src/lcdDisplay.h"
#include "uiController_esp32.h"

#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// WiFi / TCP
#define TCP_PORT 8765
#define WIFI_CONNECT_TIMEOUT_MS 12000
#define FALLBACK_AP_SSID "ChArm-UI"
#define FALLBACK_AP_PASSWORD "charm1234"

struct WiFiCredential {
    const char* ssid;
    const char* password;
};

static const WiFiCredential WIFI_CREDENTIALS[] = {
    {"SPOT-iot", "InculteNageurFeuille3373"},
};

WiFiServer tcpServer(TCP_PORT);
WiFiClient client;

// Hardware objects: same classes as on the Mega, different pins.
ButtonInput buttonInput(CLK_PIN, DT_PIN, SW_PIN);
UIState uiState;
LCDDisplay lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIControllerESP32 uiController(buttonInput, uiState, lcd);

static void showStep(const String& line1, const String& line2, unsigned long holdMs = 350) {
    lcd.update(line1, line2);
    Serial.print("[BOOT] ");
    Serial.print(line1);
    Serial.print(" | ");
    Serial.println(line2);
    delay(holdMs);
}

static bool connectToCredential(const WiFiCredential& credential, int index, int total) {
    WiFi.disconnect(true);
    delay(200);

    showStep("WiFi try", String(index) + "/" + String(total) + " " + credential.ssid, 600);
    Serial.print("Connecting to ");
    Serial.println(credential.ssid);

    WiFi.begin(credential.ssid, credential.password);

    static const char spinner[] = {'|', '/', '-', '\\'};
    unsigned long start = millis();
    int frame = 0;

    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
        int elapsed = (int)((millis() - start) / 1000);
        lcd.update("WiFi connecting", String(spinner[frame++ % 4]) + " " + String(elapsed) + "s");
        Serial.print(".");
        delay(350);
    }

    Serial.println();
    return WiFi.status() == WL_CONNECTED;
}

static bool connectWiFi() {
    showStep("BOOT UI v4", "CPU 80 MHz", 700);
    showStep("LCD/UI", "initialized", 500);

    showStep("WiFi mode", "STA setup", 350);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    showStep("WiFi config", "no sleep", 350);

    showStep("WiFi scan", "starting", 350);
    int networkCount = WiFi.scanNetworks();
    showStep("WiFi scan", String(networkCount) + " network(s)", 700);

    const int totalCredentials = sizeof(WIFI_CREDENTIALS) / sizeof(WIFI_CREDENTIALS[0]);
    for (int i = 0; i < totalCredentials; i++) {
        if (connectToCredential(WIFI_CREDENTIALS[i], i + 1, totalCredentials)) {
            Serial.print("IP: ");
            Serial.println(WiFi.localIP());
            showStep("WiFi OK", WiFi.localIP().toString(), 1500);
            return true;
        }

        showStep("WiFi failed", String("status ") + String((int)WiFi.status()), 900);
    }

    return false;
}

static void startFallbackAP() {
    showStep("Starting AP", FALLBACK_AP_SSID, 700);
    WiFi.mode(WIFI_AP);

    if (WiFi.softAP(FALLBACK_AP_SSID, FALLBACK_AP_PASSWORD)) {
        showStep("AP ChArm-UI", WiFi.softAPIP().toString(), 1500);
        Serial.print("Fallback AP IP: ");
        Serial.println(WiFi.softAPIP());
    } else {
        showStep("AP failed", "Reset ESP32", 2000);
        Serial.println("Fallback AP failed");
    }
}

void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
    Serial.begin(9600);
    delay(300);

    lcd.begin();
    showStep("LCD TEST", "ChArm ESP32", 2500);
    uiController.begin();
    if (!connectWiFi()) {
        showStep("WiFi failed", "fallback AP", 900);
        startFallbackAP();
    }

    tcpServer.begin();
    Serial.print("TCP server on port ");
    Serial.println(TCP_PORT);
    showStep("TCP server", String("port ") + String(TCP_PORT), 700);
    lcd.update("Waiting Python", WiFi.localIP().toString());
}

void loop() {
    // Accept new Python connection when none is active.
    if (!client || !client.connected()) {
        WiFiClient incoming = tcpServer.available();
        if (incoming) {
            client = incoming;
            Serial.println("Python connected");
            lcd.update("Python OK", "Starting UI");
            delay(500);
            uiController.begin();
        } else {
            delay(20);
            return;
        }
    }

    uiController.loop(client);
}
