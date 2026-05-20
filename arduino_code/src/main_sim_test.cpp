/*
 * main_sim_test.cpp
 *
 * Simulates the bridge (host-side) automatically so you can test button
 * navigation and LCD mode changes without needing a Python script or serial
 * input. The robot does NOT move — all arm calls are stubbed out.
 *
 * Build with: pio run -e sim_test
 *
 * What it does automatically:
 *  - CHECK_BOARD  → replies BOARD_OK after 500 ms  (game starts)
 *  - PLAYER_DONE  → replies BOT_THINKING (1 s) → BOT_MOVING (2 s)
 *                         → PLAYER_TURN_WHITE (2 s)
 *  - SET_DIFFICULTY x → acknowledges in Serial monitor
 *  - CALIBRATE_START / CALIBRATE_DONE → already handled inside UIController
 *
 * Serial monitor (115200) shows every [UI->SIM] and [SIM->UI] message and
 * every mode transition so you can verify the flow.
 */

#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/config.h"
#include "hardware/src/buttonInput.h"
#include "hardware/src/lcdDisplay.h"
#include "hardware/src/uiState.h"
#include "hardware/src/uiController.h"

// --- linker stubs (UIController.cpp has extern references to arm hardware) ---
#include "hardware/src/scaraJoint.h"
#include "hardware/src/leadScrew.h"
#include "hardware/src/scaraArm.h"
#include "hardware/src/gripper.h"
#include "hardware/src/stepperXYZ.h"
#include "hardware/src/limitSwitch.h"
#include "hardware/src/enableDriver.h"

StepperXYZ _stubXStepper(X_STEP_IN1, X_DIR_IN1);
StepperXYZ _stubYStepper(Y_STEP_IN1, Y_DIR_IN1);
StepperXYZ _stubZStepper(Z_STEP_IN1, Z_DIR_IN1);
LimitSwitch _stubJ1Lim(X_LIMIT_PIN);
LimitSwitch _stubJ2Lim(Y_LIMIT_PIN);
LimitSwitch _stubZLim(Z_LIMIT_BOTTOM_PIN);

ScaraJoint joint1(_stubXStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J1, _stubJ1Lim, false);
ScaraJoint joint2(_stubYStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2, _stubJ2Lim, true);
Gripper    gripper(GRIPPER_PIN, OPEN_ANGLE, CLOSED_ANGLE);
LeadScrew  leadScrew(_stubZStepper, STEPS_PER_MM, Z_MAX_MM, _stubZLim);
ScaraArm   arm(joint1, joint2, leadScrew, gripper, LINK1_LENGTH, LINK2_LENGTH);
// --------------------------------------------------------------------------

// ---- SimStream: fake bridge that auto-responds to UIController messages ----

enum SimBotState {
    BOT_IDLE,
    BOT_WILL_THINK,   // waiting to send BOT_THINKING
    BOT_WILL_MOVE,    // waiting to send BOT_MOVING
    BOT_WILL_RETURN   // waiting to send PLAYER_TURN_WHITE
};

static unsigned long lastSerialActivityMs = 0;
static unsigned long lastUiLoopMs = 0;
static const unsigned long LCD_RESYNC_IDLE_MS = 5000;
static const unsigned long UI_POLL_MS = 50;

class SimStream : public Stream {
public:
    SimStream() : txLine(""), rxBuf(""), rxIdx(0), botState(BOT_IDLE), nextEventAt(0), nextTurnWhite(false) {}

    // --- Stream interface ---
    int available() override { return (int)rxBuf.length() - rxIdx; }

    int read() override {
        if (rxIdx >= (int)rxBuf.length()) return -1;
        char c = rxBuf[rxIdx++];
        if (rxIdx >= (int)rxBuf.length()) { rxBuf = ""; rxIdx = 0; }
        return c;
    }

    int peek() override {
        if (rxIdx >= (int)rxBuf.length()) return -1;
        return (int)(uint8_t)rxBuf[rxIdx];
    }

    size_t write(uint8_t c) override {
        // mirror everything to real Serial so we can read it on the monitor
        Serial.write(c);
        if (c == '\n') {
            txLine.trim();
            if (txLine.length()) onMessageFromUI(txLine);
            txLine = "";
        } else if (c != '\r') {
            txLine += (char)c;
        }
        return 1;
    }

    // --- call every loop() to deliver time-delayed responses ---
    void tick() {
        if (botState == BOT_IDLE) return;
        if (millis() < nextEventAt) return;

        switch (botState) {
            case BOT_WILL_THINK:
                inject("BOT_THINKING");
                botState = BOT_WILL_MOVE;
                nextEventAt = millis() + 2000;
                break;
            case BOT_WILL_MOVE:
                inject("BOT_MOVING");
                botState = BOT_WILL_RETURN;
                nextEventAt = millis() + 2000;
                break;
            case BOT_WILL_RETURN:
                inject(nextTurnWhite ? "PLAYER_TURN_WHITE" : "PLAYER_TURN_BLACK");
                nextTurnWhite = !nextTurnWhite;
                botState = BOT_IDLE;
                break;
            default:
                break;
        }
    }

private:
    String txLine;
    String rxBuf;
    int rxIdx;
    SimBotState botState;
    unsigned long nextEventAt;
    bool nextTurnWhite;

    // queue a message to be read by UIController on the next loop()
    void inject(const char* msg) {
        Serial.print(F("[SIM->UI] "));
        Serial.println(msg);
        rxBuf += msg;
        rxBuf += '\n';
    }

    // called when UIController sends a complete line to the "host"
    void onMessageFromUI(const String& line) {
        Serial.print(F("[UI->SIM] "));
        Serial.println(line);

        if (line.equalsIgnoreCase("CHECK_BOARD")) {
            // reply after 500 ms
            // We can't delay here (blocks loop), so we use a one-shot trick:
            // start the bot-state machine at a step that injects BOARD_OK
            botState = BOT_IDLE; // reset first
            // We inline a direct delayed inject via a small helper flag
            _boardOkAt = millis() + 500;
            _pendingBoardOk = true;

        } else if (line.equalsIgnoreCase("PLAYER_DONE")) {
            // kick off the bot-turn sequence
            botState = BOT_WILL_THINK;
            nextEventAt = millis() + 1000;

        } else if (line.startsWith("SET_DIFFICULTY")) {
            // nothing to reply; just acknowledge on monitor
            Serial.println(F("[SIM] difficulty noted"));

        } else if (line.equalsIgnoreCase("CALIBRATE_START")) {
            Serial.println(F("[SIM] calibration started (stub)"));

        } else if (line.equalsIgnoreCase("CALIBRATE_DONE")) {
            Serial.println(F("[SIM] calibration done"));
        }
        // all other messages (UNKNOWN_CMD, state dumps, etc.) are just logged
    }

public:
    // separate pending flag for BOARD_OK because it doesn't fit the bot sequence
    bool _pendingBoardOk = false;
    unsigned long _boardOkAt = 0;

    void tickBoardOk() {
        if (_pendingBoardOk && millis() >= _boardOkAt) {
            _pendingBoardOk = false;
            inject("BOARD_OK");
        }
    }
};

// ---------------------------------------------------------------------------

SimStream     simStream;
ButtonInput   buttonInput(CLK_PIN, DT_PIN, SW_PIN);
LCDDisplay    lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIState       uiState;
UIController  uiController(buttonInput, uiState, lcd, simStream);

static UIMode lastMode = BOOT;

static const char* modeName(UIMode m) {
    switch (m) {
        case BOOT:           return "BOOT";
        case MENU:           return "MENU";
        case DIFFICULTY:     return "DIFFICULTY";
        case MANUAL_CONTROL: return "MANUAL_CONTROL";
        case MANUAL_ACTIVE:  return "MANUAL_ACTIVE";
        case CALIBRATION:    return "CALIBRATION";
        case GAME:           return "GAME";
        case ERROR:          return "ERROR";
        default:             return "?";
    }
}

void setup() {
    Serial.begin(115200);
    pinMode(ENABLE_PIN, OUTPUT);

    arm.begin();
    uiController.begin();

    Serial.println(F("=== SIM TEST READY ==="));
    Serial.println(F("Knob: navigate   Press: select"));
    Serial.println(F("Bridge responses are automatic."));
    Serial.println(F("Game flow: Start Game -> BOARD_OK auto -> press OK when done -> bot simulates move"));
}

void loop() {
    updateDrivers();
    simStream.tick();
    simStream.tickBoardOk();
    uiController.loop();
    lcd.tick();

    UIMode mode = uiState.getMode();
    if (mode != lastMode) {
        Serial.print(F("[MODE] "));
        Serial.print(modeName(lastMode));
        Serial.print(F(" -> "));
        Serial.println(modeName(mode));
        lastMode = mode;
    }
}
