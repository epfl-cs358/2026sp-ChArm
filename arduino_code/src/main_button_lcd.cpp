#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/stepperXYZ.h"
#include "hardware/src/scaraJoint.h"
#include "hardware/src/leadScrew.h"
#include "hardware/src/scaraArm.h"
#include "hardware/src/config.h"
#include "hardware/src/gripper.h"
#include "hardware/src/limitSwitch.h"
#include "hardware/src/buttonInput.h"
#include "hardware/src/uiState.h"
#include "hardware/src/lcdDisplay.h"
#include "hardware/src/uiController.h"

StepperXYZ xStepper(X_STEP_IN1, X_DIR_IN1);
StepperXYZ yStepper(Y_STEP_IN1, Y_DIR_IN1);
StepperXYZ zStepper(Z_STEP_IN1, Z_DIR_IN1);

LimitSwitch j1Lim(X_LIMIT_PIN);
LimitSwitch j2Lim(Y_LIMIT_PIN);
LimitSwitch zLim(Z_LIMIT_BOTTOM_PIN);

ScaraJoint joint1(xStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J1, j1Lim, false);
ScaraJoint joint2(yStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2, j2Lim, true);
Gripper gripper(GRIPPER_PIN, OPEN_ANGLE, CLOSED_ANGLE);
LeadScrew leadScrew(zStepper, STEPS_PER_MM, Z_MAX_MM, zLim);
ScaraArm arm(joint1, joint2, leadScrew, gripper, LINK1_LENGTH, LINK2_LENGTH);

UIState uiState;

ButtonInput buttonInput(CLK_PIN, DT_PIN, SW_PIN);
LCDDisplay lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIController uiController(buttonInput, uiState, lcd, Serial1);
static unsigned long buttonEventCount = 0;

static const char* eventName(InputEvent event) {
  switch (event) {
    case INPUT_NEXT: return  "NEXT";
    case INPUT_PREV: return "PREV";
    case INPUT_SELECT: return "SELECT";
    default: return "NONE";
  }
}

static void runButtonTest() {
  InputEvent event = buttonInput.readEvent();
  if (event != INPUT_NONE) {
    buttonEventCount++;
    Serial.print("Button event ");
    Serial.print(buttonEventCount);
    Serial.print(": ");
    Serial.println(eventName(event));
  }
}

void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  digitalWrite(ENABLE_PIN, LOW);

  Serial.begin(9600);

  buttonInput.begin();

  Serial.println("Button test ready");
}

void loop() {
  runButtonTest();
}
