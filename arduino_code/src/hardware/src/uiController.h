#ifndef UI_CONTROLLER_H
#define UI_CONTROLLER_H

#include <Arduino.h>
#include "uiState.h"
#include "buttonInput.h"
#include "lcdDisplay.h"

class UIController {
public:
    UIController(ButtonInput& buttonInput, UIState& uiState, LCDDisplay& lcd, Stream& serial = Serial);

    void begin(unsigned long baud = 115200);

    // Call frequently from `loop()`
    void loop();

    // Send current serialized state to host
    void sendState();

    // Send raw line to host
    void sendMessage(const String& msg);

private:
    ButtonInput& buttonInput;
    UIState& uiState;
    LCDDisplay& lcd;
    Stream& serial;
    String rxBuffer;
    bool waitingForBoard = false;
    unsigned long boardRequestTs = 0;
    const unsigned long boardTimeoutMs = 3000;
    UIMode lastMode;
    bool pendingLcdUpdate = false;

    void processLine(const String& line);
    void handleHostCommand(const String& cmd);
    String serializeState() const;
};

#endif