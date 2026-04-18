#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/stepperXYZ.h"
#include "hardware/src/scaraJoint.h"
#include "hardware/src/leadScrew.h"
#include "hardware/src/scaraArm.h"
#include "hardware/src/config.h"

StepperXYZ xStepper(X_STEP_IN1, X_DIR_IN1, MICROSTEPS);
StepperXYZ yStepper(Y_STEP_IN1, Y_DIR_IN1, MICROSTEPS);
StepperXYZ zStepper(Z_STEP_IN1, Z_DIR_IN1, MICROSTEPS);

ScaraJoint joint1(xStepper, X_LIMIT_MIN_PIN, X_LIMIT_MAX_PIN, STEPS_PER_REV, GEAR_RATIO_J1);
ScaraJoint joint2(yStepper, Y_LIMIT_MIN_PIN, Y_LIMIT_MAX_PIN, STEPS_PER_REV, GEAR_RATIO_J2);

LeadScrew leadScrew(zStepper, Z_LIMIT_BOTTOM_PIN);

ScaraArm arm(joint1, joint2, LINK1_LENGTH, LINK2_LENGTH);

void homeAll() {
    Serial.println("Homing all axes");

    leadScrew.home();
    joint1.home();
    joint2.home();

    arm.sync();
}

int stepCount = 0;

void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  digitalWrite(ENABLE_PIN, LOW);

  xStepper.begin();
  yStepper.begin();
  zStepper.begin();

  homeAll();

  Serial.begin(9600);
  Serial.println("f = 1 forward step in X | b = 1 backward step in X");
  Serial.println("w = 1 forward step in Y | s = 1 backward step in Y");
  Serial.println("u = 1 forward step in Y | d = 1 backward step in Y");
  Serial.println("home = home all axes");
  Serial.println("moveXY = move end effector to X Y (mm)");
  Serial.println("moveZ = move Z to z (mm)");
  Serial.println("moveXYZ = move to (X, Y, Z) (mm)");
  Serial.println("pos = print all positions");
}
 
void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');;
    cmd.trim();

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

      if (cmd == "home") {
        homeAll();
      
      } else if (cmd.startsWith("moveXY ")) {
        String vals = cmd.substring(7);
        int space   = vals.indexOf(' ');
        float x     = vals.substring(0, space).toFloat();
        float y     = vals.substring(space + 1).toFloat();
        Serial.print("Moving to X: "); Serial.print(x);
        Serial.print(", Y: ");          Serial.println(y);
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
        Serial.print(", Y: ");          Serial.print(y);
        Serial.print(", Z: ");          Serial.println(z);

        // Move Z first — bring arm to height before rotating
        leadScrew.moveTo_mm(z);
        arm.moveXY(x, y);
    
      } else if (cmd == "pos") {
        Serial.print("Joint1: "); Serial.print(joint1.angle()); Serial.println("°");
        Serial.print("Joint2: "); Serial.print(joint2.angle()); Serial.println("°");
        Serial.print("Position: ("); 
        Serial.print(arm.x()); Serial.print(", ");
        Serial.print(arm.y()); Serial.print(", ");
        Serial.print(leadScrew.position_mm()); Serial.print(")");
      }

      Serial.print("Position: ("); 
      Serial.print(arm.x()); Serial.print(", ");
      Serial.print(arm.y()); Serial.print(", ");
      Serial.print(leadScrew.position_mm()); Serial.print(")");
    } 
  }
}
