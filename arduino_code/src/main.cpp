#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/stepperXYZ.h"

StepperXYZ xStepper(X_STEP_IN1, X_DIR_IN1);
StepperXYZ yStepper(Y_STEP_IN1, Y_DIR_IN1);

int stepCount = 0;

void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  digitalWrite(ENABLE_PIN, LOW);

  xStepper.begin();
  yStepper.begin();

  Serial.begin(9600);
  Serial.println("f = forward step | b = backward step");
}

void loop() {
  if (Serial.available()) {
    char cmd = Serial.read();

    if (cmd == 'f') {
      xStepper.setDirection(true);
      xStepper.step();
      stepCount++;
    } else if (cmd == 'b') {
      xStepper.setDirection(false);
      xStepper.step();
      stepCount--;
    }

    if (cmd == 'w') {
      yStepper.setDirection(true);
      yStepper.step();
      stepCount++;
    } else if (cmd == 's') {
      yStepper.setDirection(false);
      yStepper.step();
      stepCount--;
    }

    Serial.print("Position: ");
    Serial.print(stepCount);
    Serial.println(" steps");
  }
}
