#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/config.h"
#include "hardware/src/buttonInput.h"
#include "hardware/src/lcdDisplay.h"
#include "hardware/src/uiState.h"
#include "hardware/src/uiController.h"

// --- stubs for extern symbols declared in uiController.cpp ---
// (arm movement is commented out there, but linker still needs the symbols)
#include "hardware/src/scaraJoint.h"
#include "hardware/src/leadScrew.h"
#include "hardware/src/scaraArm.h"
#include "hardware/src/gripper.h"
#include "hardware/src/stepperXYZ.h"
#include "hardware/src/limitSwitch.h"

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
void calibrate() {}   // stub — arm not used in this test
// --------------------------------------------------------------

ButtonInput   buttonInput(CLK_PIN, DT_PIN, SW_PIN);
LCDDisplay    lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIState       uiState;

// Pass Serial so you can type Python commands in the Serial Monitor
UIController  uiController(buttonInput, uiState, lcd, Serial);

static UIMode lastPrintedMode = BOOT;

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
    pinMode(ENABLE_PIN, OUTPUT);
    digitalWrite(ENABLE_PIN, LOW);

    Serial.begin(9600);
    uiController.begin();

    Serial.println("=== UI test ready ===");
    Serial.println("Knob: navigate | Press: select");
    Serial.println("Type commands: BOARD_OK, BOARD_FAIL, BOT_THINKING,");
    Serial.println("  BOT_MOVING, PLAYER_TURN_WHITE, PLAYER_TURN_BLACK,");
    Serial.println("  ERROR_CLEAR, GET_STATE");
}

void loop() {
    uiController.loop();

    // print to Serial whenever mode changes
    UIMode mode = uiState.getMode();
    if (mode != lastPrintedMode) {
        Serial.print("[MODE] ");
        Serial.print(modeName(lastPrintedMode));
        Serial.print(" -> ");
        Serial.println(modeName(mode));
        lastPrintedMode = mode;
    }
}
