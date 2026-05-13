#include "enableDriver.h"

const unsigned long IDLE_TIMEOUT = 3000;

int moveDepth = 0;
unsigned long lastMoveTime = 0;

void enableDrivers() {
    digitalWrite(ENABLE_PIN, LOW);
}

void disableDrivers() {
    digitalWrite(ENABLE_PIN, HIGH);
}

void beforeMove() {
    if (moveDepth == 0) enableDrivers();
    moveDepth++;
    lastMoveTime = millis();
}

void afterMove() {
    moveDepth--;
    lastMoveTime = millis();
}

void updateDrivers() {
    if (moveDepth == 0 && millis() - lastMoveTime > IDLE_TIMEOUT) {
        disableDrivers();
    }
}

bool driversEnabled() {
    return digitalRead(ENABLE_PIN) == LOW;
}