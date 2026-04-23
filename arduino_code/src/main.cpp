#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/stepperXYZ.h"
#include "hardware/src/scaraJoint.h"
#include "hardware/src/leadScrew.h"
#include "hardware/src/scaraArm.h"
#include "hardware/src/config.h"
#include "hardware/src/gripper.h"
#include "hardware/src/limitSwitch.h"
 
// StepperXYZ no longer takes microstep — it's passed to ScaraJoint/LeadScrew directly.
StepperXYZ xStepper(X_STEP_IN1, X_DIR_IN1);
StepperXYZ yStepper(Y_STEP_IN1, Y_DIR_IN1);
StepperXYZ zStepper(Z_STEP_IN1, Z_DIR_IN1);
 
/*
LimitSwitch j1(X_LIMIT_PIN, true);
LimitSwitch j2(Y_LIMIT_PIN, true);
LimitSwitch zBottom(Z_LIMIT_BOTTOM_PIN, true);
*/
 
/*
ScaraJoint joint1(xStepper, j1Min, j1Max, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J1);
ScaraJoint joint2(yStepper, j2Min, j1Min, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2);
LeadScrew leadScrew(zStepper, zBottom, Z_MM_PER_REV, STEPS_PER_REV, MICROSTEPS, GRIPPER_LENGTH);
*/
 
// MICROSTEPS is now passed explicitly so stepsPerDegree() is always correct.
ScaraJoint joint1(xStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J1);
ScaraJoint joint2(yStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2);
 
LeadScrew leadScrew(zStepper, Z_MM_PER_REV, GRIPPER_LENGTH);
 
ScaraArm arm(joint1, joint2, LINK1_LENGTH, LINK2_LENGTH);
 
Gripper gripper(GRIPPER_PIN, OPEN_ANGLE, CLOSED_ANGLE);
 
/*
void homeAll() {
    Serial.println("Homing all axes");
 
    leadScrew.home();
    joint1.home();
    joint2.home();
 
    arm.sync();
}
*/
 
int stepCount = 0;
 
// Reads one character at a time so loop() never blocks during a long move.
static String cmdBuffer = "";
 
static void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
 
  if (cmd.length() == 1) {
 
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
    }
 
    Serial.print("Position: ");
    Serial.print(stepCount);
    Serial.println(" steps");
 
  } else if (cmd.length() == 2) {
 
    if (cmd == "OG") {
      gripper.open();
    } else if (cmd == "CG") {
      gripper.close();
    } else if (cmd == "GS") {
      Serial.println(gripper.isOpen() ? "Gripper: open" : "Gripper: closed");
    }
 
  } else {
 
    if (cmd == "home") {
      //homeAll();
 
    } else if (cmd.startsWith("angleX ")) {
      float a = cmd.substring(7).toFloat();
      Serial.println(a);
      joint1.moveTo(a);
 
    } else if (cmd.startsWith("angleY ")) {
      float a = cmd.substring(7).toFloat();
      joint2.moveTo(a);
 
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
 
      // Move Z first — bring arm to height before rotating
      leadScrew.moveTo_mm(z);
      arm.moveXY(x, y);
 
    } else if (cmd == "pos") {
      Serial.print("Joint1: "); Serial.print(joint1.angle()); Serial.println("°");
      Serial.print("Joint2: "); Serial.print(joint2.angle()); Serial.println("°");
      Serial.print("Position: ("); 
      Serial.print(arm.x()); Serial.print(", ");
      Serial.print(arm.y()); Serial.print(", ");
      Serial.print(leadScrew.position_mm()); Serial.println(")");
      return; // already printed, skip duplicate below
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
 
  //j1Min.begin();  
  //j1Max.begin();
 
  //j2Min.begin();  
  //j2Max.begin();
 
  //zBottom.begin();
 
  //gripper.begin();
 
  xStepper.begin();
  yStepper.begin();
  zStepper.begin();
 
  Serial.begin(9600);
 
  //homeAll();
 
  Serial.println("f/b = single step X | w/s = single step Y | u/d = single step Z");
  Serial.println("home | moveXY x y | moveZ z | moveXYZ x y z | pos");
  Serial.println("OG = open gripper | CG = close gripper | GS = gripper status");
}
 
void loop() {
  // Read one character at a time — never blocks, works during long moves.
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      handleCommand(cmdBuffer);
      cmdBuffer = "";
    } else {
      cmdBuffer += c;
    }
  }
}
 