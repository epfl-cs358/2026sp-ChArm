#include "gripper.h"

Gripper::Gripper(uint8_t servoPin, int openAngle, int closedAngle) {
    this->servoPin = servoPin;
    this->openAngle = openAngle;
    this->closedAngle = closedAngle;
    this->is_Open = false;
}

void Gripper::begin() {
    servo.attach(servoPin);
    close();
}

void Gripper::open() {
    servo.write(openAngle);
    is_Open = true;
    delay(500);
    Serial.println("Gripper: open");
}

void Gripper::close() {
    servo.write(closedAngle);
    is_Open = false;
    delay(500);
    Serial.println("Gripper: closed");
}