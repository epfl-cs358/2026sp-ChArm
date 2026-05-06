#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/stepperXYZ.h"
#include "hardware/src/scaraJoint.h"
#include "hardware/src/leadScrew.h"
#include "hardware/src/scaraArm.h"
#include "hardware/src/config.h"
#include "hardware/src/gripper.h"
#include "hardware/src/limitSwitch.h"
#include "hardware/src/limitAxis.h"
#include "hardware/src/buttonInput.h"
#include "hardware/src/uiState.h"
#include "hardware/src/lcdDisplay.h"
#include "hardware/src/uiController.h"

StepperXYZ xStepper(X_STEP_IN1, X_DIR_IN1);
StepperXYZ yStepper(Y_STEP_IN1, Y_DIR_IN1);
StepperXYZ zStepper(Z_STEP_IN1, Z_DIR_IN1);

LimitSwitch j1Lim(X_LIMIT_PIN, true);
LimitSwitch j2Lim(Y_LIMIT_PIN, true);
LimitSwitch zLim(Z_LIMIT_BOTTOM_PIN, true);
 
ScaraJoint joint1(xStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J1);
ScaraJoint joint2(yStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2);
 
LeadScrew leadScrew(zStepper, STEPS_PER_MM, GRIPPER_LENGTH, Z_MAX_MM);
 
ScaraArm arm(joint1, joint2, LINK1_LENGTH, LINK2_LENGTH);
 
Gripper gripper(GRIPPER_PIN, OPEN_ANGLE, CLOSED_ANGLE);


UIState uiState;
ButtonInput buttonInput(CLK_PIN, DT_PIN, SW_PIN);
LCDDisplay lcd(RS_PIN, E_PIN, D4_PIN, D5_PIN, D6_PIN, D7_PIN);
UIController uiController(buttonInput, uiState, lcd, Serial1);


void calibrate() {
    Serial.println("Calibrating");
 
    // Z: drive to bottom switch, set zero, max is constant
    Serial.println("Z: finding bottom");
    findLimit(zStepper, zLim, false, 50);
    backOff(zStepper, zLim, true, 200);
    leadScrew.setZero();
    leadScrew.moveTo_mm(30);  // lift to clear the box during rest of calibration
    Serial.println("Z: done");

    // J1: one switch, zero is 90deg away from limit (straight = 0 in IK)
    Serial.println("J1: finding limit");
    findLimit(xStepper, j1Lim, false, 50);
    backOff(xStepper, j1Lim, true, 50);
    joint1.setZero();
    joint1.setMaxAngle(270.0f);  // temp max to allow 90deg move
    joint1.moveTo(137.0f);        // 90deg away from limit = IK zero
    joint1.setZero();
    joint1.setMinAngle(-137.0f);  // limit switch is 90deg in this direction
    joint1.setMaxAngle(133.0f);
    Serial.println("J1: done");

    // J2: two switches, zero is center of range (straight = 0 in IK)
    Serial.println("J2: finding min");
    findLimit(yStepper, j2Lim, false, 100);
    backOff(yStepper, j2Lim, true, 200);
    joint2.setZero();
    joint2.setMaxAngle(360.0f);  // temp max to allow full range move
    Serial.println("J2: finding max");
    long steps = findLimit(yStepper, j2Lim, true, 100);
    long stepsB = backOff(yStepper, j2Lim, false, 50);

    float maxAngleDeg = (steps - stepsB) / joint2.stepsPerDegree();
    joint2.setMaxAngle(maxAngleDeg);
    joint2.setAngle(maxAngleDeg);
    Serial.print("J2: steps = "); Serial.println(steps);
    Serial.print("J2: max = "); Serial.print(maxAngleDeg); Serial.println(" deg");

    // move to center of range, declare as IK zero
    float halfRange = maxAngleDeg / 2.0f;
    joint2.moveTo(halfRange);
    joint2.setZero();
    joint2.setMinAngle(-halfRange);
    joint2.setMaxAngle(halfRange);
    Serial.print("J2: center = "); Serial.print(halfRange); Serial.println(" deg");
    

    arm.sync();
    Serial.println("Calibration done");
}

int stepCount = 0;
static String cmdBuffer = "";

// Cartesian jog mode: w/a/s/d move XY, u/j move Z. Toggle with `controllerMode`.
// 'd' is taken by +X in this mode, so Z-down uses 'j' (under 'u' on QWERTY).
// Steps are small so terminal key-repeat feels continuous instead of queueing.
static bool controllerMode = false;
static const float JOG_XY_MM = 3.0f;
static const float JOG_Z_MM  = 1.5f;

static bool isJogKey(char c) {
  return c == 'w' || c == 'a' || c == 's' || c == 'd'
      || c == 'u' || c == 'j'
      || c == 'c' || c == 'v';
}

static void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.length() == 1) {

    if (controllerMode) {
      // Re-sync arm.x()/y() from actual joint angles so a previously clamped
      // move can't accumulate drift in the requested target.
      arm.sync();

      bool moved = true;
      if      (cmd == "w") arm.moveXY(arm.x(), arm.y() + JOG_XY_MM);
      else if (cmd == "s") arm.moveXY(arm.x(), arm.y() - JOG_XY_MM);
      else if (cmd == "a") arm.moveXY(arm.x() - JOG_XY_MM, arm.y());
      else if (cmd == "d") arm.moveXY(arm.x() + JOG_XY_MM, arm.y());
      else if (cmd == "u") leadScrew.moveBy_mm(JOG_Z_MM);
      else if (cmd == "j") leadScrew.moveBy_mm(-JOG_Z_MM);
      else if (cmd == "c") gripper.close();
      else if (cmd == "v") gripper.open();
      else moved = false;

      if (moved) {
        arm.sync();
        Serial.print("Position: (");
        Serial.print(arm.x()); Serial.print(", ");
        Serial.print(arm.y()); Serial.print(", ");
        Serial.print(leadScrew.position_mm()); Serial.println(")");
      }
      return;
    }

    if (cmd == "f") {
      xStepper.setDirection(true);
      xStepper.step();
      arm.sync();
      stepCount++;
    } else if (cmd == "b") {
      xStepper.setDirection(false);
      xStepper.step();
      arm.sync();
      stepCount--;
    } else if (cmd == "w") {
      yStepper.setDirection(true);
      yStepper.step();
      arm.sync();
      stepCount++;
    } else if (cmd == "s") {
      yStepper.setDirection(false);
      yStepper.step();
      arm.sync();
      stepCount--;
    } else if (cmd == "u") {
      zStepper.setDirection(true);
      zStepper.step();
      stepCount++;
    } else if (cmd == "d") {
      zStepper.setDirection(false);
      zStepper.step();
      stepCount--;
    } else if (cmd == "c") {
      gripper.close();
      return;
    } else if (cmd == "v") {
      gripper.open();
      return;
    }

    Serial.print("Position: ");
    Serial.print(stepCount);
    Serial.println(" steps");

  } else {
    if (cmd == "OG") {
      gripper.open();
    } else if (cmd == "CG") {
      gripper.close();
    } else if (cmd == "GS") {
      Serial.println(gripper.isOpen() ? "Gripper: open" : "Gripper: closed");
    } else if (cmd == "GA ") {
      float angle = cmd.substring(3).toFloat();
      gripper.goToAngle(angle);
 
    } else if (cmd.startsWith("angleX ")) {
      float a = cmd.substring(7).toFloat();
      Serial.println(a);
      joint1.moveTo(a);
      arm.sync();
      
 
    } else if (cmd.startsWith("angleY ")) {
      float a = cmd.substring(7).toFloat();
      joint2.moveTo(a);
      arm.sync();
 
    } else if (cmd.startsWith("moveXY ")) {
      String vals = cmd.substring(7);
      int space   = vals.indexOf(' ');
      float x     = vals.substring(0, space).toFloat();
      float y     = vals.substring(space + 1).toFloat();
      Serial.print("Moving to X: "); Serial.print(x);
      Serial.print(", Y: "); Serial.println(y);
      arm.moveXY(x, y);
 
    } else if (cmd.startsWith("moveZ ")) {
      float mm = cmd.substring(6).toFloat();
      Serial.print("Moving Z to: "); Serial.print(mm); Serial.println(" mm");
      leadScrew.moveTo_mm(mm);
 
    } else if (cmd.startsWith("moveXYZ ")) {
      String vals  = cmd.substring(8);
      int space1   = vals.indexOf(' ');
      int space2   = vals.indexOf(' ', space1 + 1);
      float x = vals.substring(0, space1).toFloat();
      float y = vals.substring(space1 + 1, space2).toFloat();
      float z = vals.substring(space2 + 1).toFloat();
      Serial.print("Moving to X: "); Serial.print(x);
      Serial.print(", Y: "); Serial.print(y);
      Serial.print(", Z: "); Serial.println(z);
      leadScrew.moveTo_mm(z);
      arm.moveXY(x, y);

    } else if (cmd == "calibrate") {
      calibrate();

    } else if (cmd == "controllerMode" || cmd == "cm") {
      controllerMode = !controllerMode;
      Serial.print("Controller mode ");
      Serial.println(controllerMode ? "ON (w/a/s/d=XY, u/j=Z)" : "OFF");
      return;

    } else if (cmd == "pos") {
      Serial.print("Joint1: "); Serial.print(joint1.angle()); Serial.println("°");
      Serial.print("Joint2: "); Serial.print(joint2.angle()); Serial.println("°");
      Serial.print("Position: (");
      Serial.print(arm.x()); Serial.print(", ");
      Serial.print(arm.y()); Serial.print(", ");
      Serial.print(leadScrew.position_mm()); Serial.println(")");
      return;
    }
 
    Serial.print("Position: (");
    Serial.print(arm.x()); Serial.print(", ");
    Serial.print(arm.y()); Serial.print(", ");
    Serial.print(leadScrew.position_mm()); Serial.println(")");
    
  }
}
 
void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  digitalWrite(ENABLE_PIN, LOW);

  j1Lim.begin();
  j2Lim.begin();
  zLim.begin();
 
  xStepper.begin();
  yStepper.begin();
  zStepper.begin();
  Serial.begin(9600);
  gripper.begin();
  //Serial1.begin(115200);

  //uiController.begin();
 
  Serial.println("f/b = single step X | w/s = single step Y | u/d = single step Z");
  Serial.println("home | moveXY x y | moveZ z | moveXYZ x y z | pos");
  Serial.println("OG/CG = open/close gripper | v/c = open/close gripper | GS = gripper status");
  Serial.println("cm = toggle controller mode (w/a/s/d=XY, u/j=Z, v/c=gripper)");
}
 
void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;

    // In controller mode, jog keys dispatch immediately (no Enter needed) so
    // that holding the key auto-repeats into continuous motion. Multi-char
    // commands like `cm` still work because their letters aren't jog keys.
    if (controllerMode && isJogKey(c)) {
      handleCommand(String(c));
      continue;
    }

    if (c == '\n') {
      handleCommand(cmdBuffer);
      cmdBuffer = "";
    } else {
      cmdBuffer += c;
    }
  }

  //uiController.loop();
}