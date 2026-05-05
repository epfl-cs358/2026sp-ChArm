#include <Arduino.h>
#include "hardware/src/pins.h"
#include "hardware/src/limitSwitch.h"

LimitSwitch j1Lim(X_LIMIT_PIN, true);
LimitSwitch j2Lim(Y_LIMIT_PIN, true);
LimitSwitch zLim(Z_LIMIT_BOTTOM_PIN, true);

void setup() {
  Serial.begin(9600);
  pinMode(X_LIMIT_PIN, INPUT);
  pinMode(Y_LIMIT_PIN, INPUT);
  pinMode(Z_LIMIT_BOTTOM_PIN, INPUT);
  Serial.println("Limit switch debug ready");
}

void loop() {
  Serial.println(digitalRead(Z_LIMIT_BOTTOM_PIN));
}