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

StepperXYZ xStepper(X_STEP_IN1, X_DIR_IN1);
StepperXYZ yStepper(Y_STEP_IN1, Y_DIR_IN1);
StepperXYZ zStepper(Z_STEP_IN1, Z_DIR_IN1);
 
LimitSwitch j1Lim(X_LIMIT_PIN, true);
LimitSwitch j2Lim(Y_LIMIT_PIN, true);
LimitSwitch zLim(Z_LIMIT_BOTTOM_PIN, true);
 
ScaraJoint joint1(xStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J1);
ScaraJoint joint2(yStepper, STEPS_PER_REV, MICROSTEPS, GEAR_RATIO_J2);
 
LeadScrew leadScrew(zStepper, Z_MAX_MM, LINK3_LENGTH, GRIPPER_LENGTH);
 
ScaraArm arm(joint1, joint2, LINK1_LENGTH, LINK2_LENGTH);
 
Gripper gripper(GRIPPER_PIN, OPEN_ANGLE, CLOSED_ANGLE);

void calibrate() {
    Serial.println("Calibrating");
 
    // Z: drive to bottom switch, set zero, max is constant
    Serial.println("Z: finding bottom");
    findLimit(zStepper, zLim, false);
    backOff(zStepper, zLim, true);
    leadScrew.setZero();
    Serial.println("Z: done");
 
    // Joint1: same pin, two switches differentiated by direction
    // false = min switch -> set zero
    // true = max switch -> record max angle
    Serial.println("J1: finding min");
    findLimit(xStepper, j1Lim, false);
    backOff(xStepper, j1Lim, true);
    joint1.setZero();
    Serial.println("J1: finding max");
    long steps = findLimit(xStepper, j1Lim, true);
    long stepsB = backOff(xStepper, j1Lim, false);
    float maxAngleDeg = (steps - stepsB) / joint1.stepsPerDegree();
    joint1.setMaxAngle(maxAngleDeg);
    Serial.print("J1: steps = "); Serial.println(steps);
    Serial.print("J1: max = "); Serial.print(maxAngleDeg); Serial.println(" deg");
 
    // Joint2: one switch, max is constant 360
    Serial.println("J2: finding limit");
    findLimit(yStepper, j2Lim, false);
    backOff(xStepper, j1Lim, true);
    joint2.setZero();
    joint2.setMaxAngle(180.0f);
    Serial.println("J2: done");
 
    arm.sync();
    Serial.println("Calibration done");
}

int stepCount = 0;
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
      leadScrew.moveTo_mm(z);
      arm.moveXY(x, y);

    } else if (cmd == "calibrate") {
      calibrate();
 
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
 
  Serial.println("f/b = single step X | w/s = single step Y | u/d = single step Z");
  Serial.println("home | moveXY x y | moveZ z | moveXYZ x y z | pos");
  Serial.println("OG = open gripper | CG = close gripper | GS = gripper status");
}
 
void loop() {
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