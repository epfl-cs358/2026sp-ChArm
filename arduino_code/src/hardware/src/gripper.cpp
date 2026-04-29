#include "gripper.h"

Gripper::Gripper(uint8_t servoPin, int openAngle, int closedAngle) {
    this->servoPin = servoPin;
    this->openAngle = openAngle;
    this->closedAngle = closedAngle;
    this->is_Open = false;
}

void Gripper::begin() {
    servo.attach(servoPin);
    goToAngle(120);
    is_Open = true;
    Serial.println("Gripper: begin at 100 degrees");
}

void Gripper::open() {
    goToAngle(openAngle);
    is_Open = true;
    Serial.println("Gripper: open");
}

void Gripper::close() {
    goToAngle(closedAngle);
    is_Open = false;
    Serial.println("Gripper: closed");
}

void Gripper::goToAngle(float angle) {
    servo.write(angle);
    delay(500);
}