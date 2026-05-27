#ifndef UI_CONTROLLER_ESP32_H
#define UI_CONTROLLER_ESP32_H

#include <Arduino.h>
#include <WiFi.h>
#include "../src/hardware/src/buttonInput.h"
#include "../src/hardware/src/uiState.h"
#include "../src/hardware/src/lcdDisplay.h"

// Callback signature: called when calibration is triggered from the UI.
// Python side is responsible for forwarding "CALIBRATION" to the Mega.
typedef void (*HostCommandCallback)(const String&);

class UIControllerESP32 {
public:
    UIControllerESP32(ButtonInput& buttonInput, UIState& uiState, LCDDisplay& lcd);

    void begin();

    // Call every loop(). Reads buttons, processes TCP lines, updates LCD.
    void loop(WiFiClient& client);

    // Send a newline-terminated message to Python over TCP.
    void sendMessage(WiFiClient& client, const String& msg);

private:
    ButtonInput& buttonInput;
    UIState&     uiState;
    LCDDisplay&  lcd;

    String   rxBuffer;
    bool     waitingForBoard;
    bool     pendingLcdUpdate;
    UIMode   lastMode;

    static const unsigned long BOARD_TIMEOUT_MS = 10000;
    unsigned long boardRequestTs;

    void processLine(WiFiClient& client, const String& line);
    void handleButtons(WiFiClient& client);
};

#endif
